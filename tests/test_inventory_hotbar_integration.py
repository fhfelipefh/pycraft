from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
MAIN_PY = BASE_DIR / "main.py"


def test_inventory_toggle_is_bound_to_e_key():
    text = MAIN_PY.read_text(encoding="utf-8")
    assert 'if key == "e":' in text
    assert "set_inventory_open(not inventory_open[0])" in text


def test_hotbar_uses_fixed_slot_count_mapping():
    text = MAIN_PY.read_text(encoding="utf-8")
    assert "HOTBAR_SLOT_COUNT = 9" in text
    assert "hotbar_block_indices" in text
    assert "return BLOCK_TYPES[hotbar_block_indices[selected_block_index]]" in text


def test_inventory_assignment_updates_selected_hotbar_slot():
    text = MAIN_PY.read_text(encoding="utf-8")
    assert "def assign_inventory_block_to_selected_slot(block_index):" in text
    assert "hotbar_block_indices[selected_block_index] = block_index" in text
