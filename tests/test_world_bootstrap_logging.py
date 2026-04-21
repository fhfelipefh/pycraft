from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
MAIN_PY = BASE_DIR / "main.py"
MENU_PY = BASE_DIR / "pycraft" / "menu.py"


def test_main_logs_bootstrap_menu_runtime_and_errors():
    text = MAIN_PY.read_text(encoding="utf-8")

    assert "def log_world_bootstrap(event, **fields):" in text
    assert "def log_world_bootstrap_completion(event, **fields):" in text
    assert "def get_world_bootstrap_duration_seconds():" in text
    assert "def compute_bootstrap_percent(ready_chunks):" in text
    assert "def compute_bootstrap_focus_position(x, z):" in text
    assert "def start_world_bootstrap():" in text
    assert '"menu.hand_off_to_world"' in text
    assert 'log_world_bootstrap("runtime.init.begin")' in text
    assert '"bootstrap.progress"' in text
    assert '"loading_overlay.state"' in text
    assert 'f"Gerando mundo... {progress_percent}% ({ready_chunks}/{progress_target} chunks)"' in text
    assert 'invoke(start_world_bootstrap, delay=WORLD_BOOTSTRAP_DELAY_SECONDS)' in text
    assert 'world_bootstrap_focus_position[0] = compute_bootstrap_focus_position(player.x, player.z)' in text
    assert 'menu.show_loading_screen("Preparando geracao do mundo...", 0)' in text
    assert 'menu.show_loading_screen("Gerando mundo... 0% (0/4 chunks)", 0)' in text
    assert "menu.update_loading_progress(loading_message, progress_percent)" in text
    assert "menu.hide_loading_screen()" in text
    assert 'log_world_bootstrap_completion("bootstrap.error", error=error_key)' in text
    assert '"started_at"' in text
    assert '"finished_at"' in text
    assert '"total_duration_s"' in text
    assert "traceback.print_exc()" in text


def test_menu_logs_when_play_button_starts_world():
    text = MENU_PY.read_text(encoding="utf-8")

    assert 'print("[menu] start_game clicked", flush=True)' in text
    assert "def show_loading_screen(self, message=\"Preparando...\", progress=0.0):" in text
    assert "def update_loading_progress(self, message, progress):" in text
    assert "def hide_loading_screen(self):" in text
