from terrain_async_scheduler import DesiredPositionsScheduler


class FakeFuture:
    def __init__(self, fn, args):
        self._fn = fn
        self._args = args
        self._done = False
        self._result = None
        self._error = None

    def done(self):
        return self._done

    def result(self):
        if self._error is not None:
            raise self._error
        return self._result

    def complete(self):
        try:
            self._result = self._fn(*self._args)
        except Exception as exc:
            self._error = exc
        self._done = True


class FakeExecutor:
    def __init__(self):
        self.futures = []

    def submit(self, fn, *args):
        future = FakeFuture(fn, args)
        self.futures.append(future)
        return future


def test_scheduler_keeps_latest_request_without_starvation():
    executor = FakeExecutor()

    def compute(cell, custom_positions, removed_positions):
        return {cell}

    scheduler = DesiredPositionsScheduler(executor, compute)

    scheduler.request((0, 0, 0), tuple(), tuple())
    scheduler.request((1, 0, 0), tuple(), tuple())
    scheduler.request((2, 0, 0), tuple(), tuple())

    # Only one job should be in flight initially.
    assert len(executor.futures) == 1

    # Finish first task for old cell.
    executor.futures[0].complete()
    assert scheduler.consume((2, 0, 0)) is None

    # Scheduler should now have submitted a task for latest requested cell.
    assert len(executor.futures) == 2
    executor.futures[1].complete()

    latest = scheduler.consume((2, 0, 0))
    assert latest == {(2, 0, 0)}


def test_scheduler_returns_ready_result_for_exact_cell():
    executor = FakeExecutor()

    def compute(cell, custom_positions, removed_positions):
        return {cell, (99, 0, 99)}

    scheduler = DesiredPositionsScheduler(executor, compute)

    scheduler.request((5, 0, 5), tuple(), tuple())
    assert len(executor.futures) == 1

    executor.futures[0].complete()
    result = scheduler.consume((5, 0, 5))
    assert (5, 0, 5) in result
    assert (99, 0, 99) in result
