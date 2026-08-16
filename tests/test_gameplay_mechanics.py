from pycraft.gameplay import resolve_pick_block_slot, approach_value


def test_resolve_pick_block_slot_existing():
    hotbar = [0, 1, 2, 3, 4, 0, 0, 0, 0]
    slot, updated_hotbar = resolve_pick_block_slot(hotbar, 2, current_slot=0)
    assert slot == 2
    assert updated_hotbar == [0, 1, 2, 3, 4, 0, 0, 0, 0]


def test_resolve_pick_block_slot_new():
    hotbar = [0, 1, 2, 3, 4, 0, 0, 0, 0]
    target_block_index = 5
    current_slot = 3
    slot, updated_hotbar = resolve_pick_block_slot(hotbar, target_block_index, current_slot)
    assert slot == current_slot
    assert updated_hotbar[current_slot] == target_block_index
    assert updated_hotbar == [0, 1, 2, 5, 4, 0, 0, 0, 0]


def test_approach_value_fov():
    base_fov = 80.0
    target_fov = 90.0

    # Smooth step toward target FOV
    current_fov = approach_value(base_fov, target_fov, max_delta=4.0)
    assert current_fov == 84.0

    # Over-shooting clamps at target FOV
    current_fov = approach_value(88.0, target_fov, max_delta=5.0)
    assert current_fov == 90.0
