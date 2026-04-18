"""Native acceleration wrappers for voxel calculations.

This module is mandatory for runtime performance. If the native extension is
missing, import fails with a clear installation hint.
"""

from typing import Iterable, Tuple

try:
    from _voxel_native import flat_ground_positions as _native_flat_ground_positions
    from _voxel_native import filter_custom_positions as _native_filter_custom_positions
except Exception:
    try:
        from native._voxel_native import flat_ground_positions as _native_flat_ground_positions
        from native._voxel_native import filter_custom_positions as _native_filter_custom_positions
    except Exception as exc:
        raise ImportError(
            "Modulo nativo obrigatorio nao encontrado: _voxel_native. "
            "Execute ./setup.sh para instalar dependencias e compilar o modulo C++."
        ) from exc


GridPos = Tuple[int, int, int]


def get_flat_ground_positions(px: int, pz: int, radius: int, ground_y: int) -> Iterable[GridPos]:
    return _native_flat_ground_positions(px, pz, radius, ground_y)


def get_filtered_custom_positions(
    positions: Iterable[GridPos],
    px: int,
    py: int,
    pz: int,
    radius_xy: int,
    height: int,
) -> Iterable[GridPos]:
    return _native_filter_custom_positions(list(positions), px, py, pz, radius_xy, height)
