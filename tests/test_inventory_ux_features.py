from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
MAIN_PY = BASE_DIR / "main.py"


def test_inventory_uses_centered_inventory_texture_with_27_slots():
    text = MAIN_PY.read_text(encoding="utf-8")
    assert 'texture=resolve_existing_asset_path([f"{UI_PATH}/inventory.png"])' in text
    assert "INVENTORY_COLUMNS = 9" in text
    assert "INVENTORY_ROWS = 3" in text
    assert "INVENTORY_PAGE_SIZE = INVENTORY_COLUMNS * INVENTORY_ROWS" in text


def test_inventory_slot_positions_match_minecraft_layout():
    text = MAIN_PY.read_text(encoding="utf-8")
    assert "def get_inventory_grid_slot_position(slot_index):" in text
    assert "return inventory_pixel_to_local(17 + (slot_index * 18), 151)" in text
    assert "return inventory_pixel_to_local(17 + (col * 18), 93 + (row * 18))" in text


def test_inventory_supports_drag_and_drop_to_hotbar():
    text = MAIN_PY.read_text(encoding="utf-8")
    assert "def start_inventory_drag():" in text
    assert "def finish_inventory_drag():" in text
    assert 'if key == "left mouse down":' in text
    assert 'if key == "left mouse up":' in text


def test_inventory_uses_player_preview_sprite_and_larger_slot_icons():
    text = MAIN_PY.read_text(encoding="utf-8")
    assert 'texture=resolve_existing_asset_path([f"{UI_PATH}/player_preview.png"])' in text
    assert "scale=(0.9, 0.9)" in text
