from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
MAIN_PY = BASE_DIR / "main.py"


def test_inventory_toggle_is_bound_to_e_key():
    text = MAIN_PY.read_text(encoding="utf-8")
    assert 'if key == "e":' in text
    assert "set_inventory_open(not inventory_open[0])" in text


def test_hotbar_keeps_fixed_slot_count_mapping():
    text = MAIN_PY.read_text(encoding="utf-8")
    assert "HOTBAR_SLOT_COUNT = 9" in text
    assert "hotbar_block_indices" in text
    assert "return BLOCK_TYPES[hotbar_block_indices[selected_block_index]]" in text


def test_inventory_hotbar_drag_updates_existing_hotbar():
    text = MAIN_PY.read_text(encoding="utf-8")
    assert 'texture=resolve_existing_asset_path([f"{UI_PATH}/Hotbar_selector.png"])' in text
    assert "inventory_hotbar_buttons.append(slot_button)" in text
    assert 'hotbar_block_indices[target_index] = inventory_drag_block_index[0]' in text


def test_hotbar_slots_match_hotbar_texture_layout():
    text = MAIN_PY.read_text(encoding="utf-8")
    assert "HOTBAR_SLOT_SPACING_PX = 40" in text
    assert "HOTBAR_FIRST_SLOT_CENTER_PX = 21.5" in text
    assert "slot_spacing = hotbar_bg.scale_x * (HOTBAR_SLOT_SPACING_PX / HOTBAR_TEXTURE_WIDTH)" in text
