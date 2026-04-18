from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
MAIN_PY = BASE_DIR / "main.py"
MENU_PY = BASE_DIR / "menu.py"


def test_settings_menu_uses_same_button_scale_family_as_main_menu():
    text = MENU_PY.read_text(encoding="utf-8")
    assert "self.menu_button_scale = (0.4, 0.1)" in text
    assert "self.settings_button_scale = (0.2, 0.05)" in text
    assert "self.settings_small_button_scale = (0.07, 0.05)" in text


def test_chicken_is_no_longer_forced_to_spawn_height_every_frame():
    text = MAIN_PY.read_text(encoding="utf-8")
    assert "def apply_mob_gravity(" in text
    assert "def move_entity_with_grounding(" in text
    assert "chicken.y = chicken_spawn_position.y" not in text
