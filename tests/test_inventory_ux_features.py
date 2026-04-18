from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
MAIN_PY = BASE_DIR / "main.py"


def test_inventory_uses_existing_ui_slot_assets():
    text = MAIN_PY.read_text(encoding="utf-8")
    assert 'GUI_slot.png' in text
    assert 'Hotbar.png' in text
    assert 'Hotbar_selector.png' in text


def test_inventory_has_grouping_and_filter_helpers():
    text = MAIN_PY.read_text(encoding="utf-8")
    assert "def get_inventory_group_for_block(block_type):" in text
    assert "def set_inventory_group(group_key):" in text
    assert '("natureza", 1)' in text
    assert '("minerios", 4)' in text
    assert "tab_textures" in text


def test_inventory_has_pagination_and_search_input():
    text = MAIN_PY.read_text(encoding="utf-8")
    assert "INVENTORY_PAGE_SIZE" in text
    assert "def next_inventory_page(delta):" in text
    assert 'if key == "left arrow":' in text
    assert 'if key == "right arrow":' in text
    assert 'if key == "backspace":' in text
    assert "inventory_search_query" in text
