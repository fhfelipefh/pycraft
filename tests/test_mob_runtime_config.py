from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
MAIN_PY = BASE_DIR / "main.py"


def test_removed_mobs_are_not_in_ambient_list():
    text = MAIN_PY.read_text(encoding="utf-8")
    assert '"bat"' not in text
    assert '"slime"' not in text
    assert '"zombie"' not in text


def test_villager_is_not_in_ambient_list_anymore():
    text = MAIN_PY.read_text(encoding="utf-8")
    assert '"villager"' not in text
    assert "npcs/david_t_pose.fbx" not in text


def test_render_distance_was_increased():
    text = MAIN_PY.read_text(encoding="utf-8")
    assert "RENDER_RADIUS = 30" in text
    assert "CUSTOM_RENDER_RADIUS = 88" in text


def test_mobs_are_paused_when_menu_is_open():
    text = MAIN_PY.read_text(encoding="utf-8")
    assert "def is_game_paused():" in text
    assert "if not is_game_paused():" in text
    assert "update_ambient_mobs()" in text
    assert "update_chicken_walking()" in text


def test_custom_crosshair_is_integrated():
    text = MAIN_PY.read_text(encoding="utf-8")
    assert "crosshair = None" in text
    assert "crosshair.enabled" in text


def test_background_music_candidates_are_configured():
    text = MAIN_PY.read_text(encoding="utf-8")
    assert 'MUSIC_DIR = Path("musics").as_posix()' in text
    assert "MUSIC_EXTENSIONS" in text
    assert "def get_music_playlist_files():" in text
    assert "background_music_playlist = get_music_playlist_files()" in text
    assert "def play_background_music_track(track_index):" in text
    assert "def update_background_music():" in text
    assert "loop=False" in text
