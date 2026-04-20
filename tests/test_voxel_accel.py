from pycraft import voxel_accel


def test_flat_ground_positions_matches_expected_size_and_points():
    positions = list(voxel_accel.get_flat_ground_positions(px=10, pz=-2, radius=2, ground_y=0))
    assert len(positions) == 25
    assert (8, 0, -4) in positions
    assert (10, 0, -2) in positions
    assert (12, 0, 0) in positions


def test_native_module_is_loaded():
    assert voxel_accel._native_flat_ground_positions is not None


def test_filter_custom_positions_in_radius():
    positions = [
        (0, 0, 0),
        (5, 0, 5),
        (20, 0, 0),
        (0, 10, 0),
    ]
    filtered = list(
        voxel_accel.get_filtered_custom_positions(
            positions,
            px=0,
            py=0,
            pz=0,
            radius_xy=8,
            height=4,
        )
    )
    assert (0, 0, 0) in filtered
    assert (5, 0, 5) in filtered
    assert (20, 0, 0) not in filtered
    assert (0, 10, 0) not in filtered
