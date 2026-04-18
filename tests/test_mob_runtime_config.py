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
