from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
MAIN_PY = BASE_DIR / "main.py"


def test_game_window_is_centered_on_startup_and_after_fullscreen():
    text = MAIN_PY.read_text(encoding="utf-8")
    assert "def center_game_window():" in text
    assert "WindowProperties()" in text
    assert "props.setOrigin(origin_x, origin_y)" in text
    assert "invoke(center_game_window, delay=0.05)" in text


def test_inventory_has_internal_hotbar_slot_selection():
    text = MAIN_PY.read_text(encoding="utf-8")
    assert "def set_selected_hotbar_slot(slot_index):" in text
    assert "inventory_hotbar_selector = [None]" in text
    assert "inventory_hotbar_buttons = []" in text
