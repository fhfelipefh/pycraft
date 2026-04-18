from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple


Cell = Tuple[int, int, int]


@dataclass
class _InflightTask:
    cell: Cell
    future: Any


class DesiredPositionsScheduler:
    """Schedules desired-position computation without starving current cells.

    Root issue fixed here: replacing the tracked future every frame can make
    the current cell never become "ready" in fast movement scenarios.
    """

    def __init__(self, executor: Any, compute_fn: Callable[[Cell, tuple, tuple], set]):
        self._executor = executor
        self._compute_fn = compute_fn
        self._inflight: Optional[_InflightTask] = None
        self._latest_requested_cell: Optional[Cell] = None
        self._latest_custom_snapshot: tuple = tuple()
        self._latest_removed_snapshot: tuple = tuple()
        self._ready_results: Dict[Cell, set] = {}

    def request(self, cell: Optional[Cell], custom_positions: tuple, removed_positions: tuple) -> None:
        if cell is None:
            return

        self._latest_requested_cell = cell
        self._latest_custom_snapshot = tuple(custom_positions)
        self._latest_removed_snapshot = tuple(removed_positions)

        self._drain_completed()
        self._maybe_submit_latest()

    def consume(self, cell: Optional[Cell]) -> Optional[set]:
        if cell is None:
            return None

        self._drain_completed()
        self._maybe_submit_latest()
        return self._ready_results.pop(cell, None)

    def _maybe_submit_latest(self) -> None:
        if self._inflight is not None:
            return

        if self._latest_requested_cell is None:
            return

        target_cell = self._latest_requested_cell
        future = self._executor.submit(
            self._compute_fn,
            target_cell,
            self._latest_custom_snapshot,
            self._latest_removed_snapshot,
        )
        self._inflight = _InflightTask(cell=target_cell, future=future)

    def _drain_completed(self) -> None:
        if self._inflight is None:
            return

        if not self._inflight.future.done():
            return

        task = self._inflight
        self._inflight = None

        try:
            result = task.future.result()
        except Exception:
            result = set()

        self._ready_results[task.cell] = result
