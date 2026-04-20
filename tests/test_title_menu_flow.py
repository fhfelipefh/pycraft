from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
MAIN_PY = BASE_DIR / "main.py"
MENU_PY = BASE_DIR / "menu.py"


def test_menu_starts_with_title_screen_and_play_button():
    text = MENU_PY.read_text(encoding="utf-8")
    assert "self.title_open = True" in text
    assert 'text="Jogar"' in text
    assert "def start_game(self):" in text


def test_main_blocks_gameplay_until_menu_releases_it():
    text = MAIN_PY.read_text(encoding="utf-8")
    assert "menu.is_blocking_gameplay()" in text
    assert "set_game_hud_visible(False)" in text
    assert "menu.handle_escape()" in text


def test_menu_ui_elements_are_drawn_in_front_of_panels():
    text = MENU_PY.read_text(encoding="utf-8")
    assert "parent=self.title_bg" in text
    assert "position=(0, 0.285, 0.02)" in text
    assert "button.text_entity.scale_x = normal_text_scale" in text
    assert "z=0.02" in text
