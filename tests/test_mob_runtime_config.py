from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
MAIN_PY = BASE_DIR / "main.py"


def test_removed_mobs_are_not_in_ambient_list():
    text = MAIN_PY.read_text(encoding="utf-8")
    assert '"bat"' not in text
    assert '"slime"' not in text
    assert '"zombie"' not in text


def test_villager_ground_offset_is_raised():
    text = MAIN_PY.read_text(encoding="utf-8")
    assert '"villager"' in text
    assert "ground_offset=0.0" in text


def test_render_distance_was_increased():
    text = MAIN_PY.read_text(encoding="utf-8")
    assert "RENDER_RADIUS = 28" in text
    assert "CUSTOM_RENDER_RADIUS = 84" in text


def test_mobs_are_paused_when_menu_is_open():
    text = MAIN_PY.read_text(encoding="utf-8")
    assert "def is_game_paused():" in text
    assert "if not is_game_paused():" in text
    assert "update_ambient_mobs()" in text
    assert "update_chicken_walking()" in text


def test_custom_crosshair_is_integrated():
    text = MAIN_PY.read_text(encoding="utf-8")
    assert 'texture=resolve_existing_asset_path([f"{UI_PATH}/Crosshair.png"])' in text
    assert "crosshair.enabled = not state" in text


def test_background_music_candidates_are_configured():
    text = MAIN_PY.read_text(encoding="utf-8")
    assert "BGM_CANDIDATES" in text
    assert '"sounds/Below_and_Above.ogg"' in text
    assert '"sounds/Fireflies.ogg"' in text
