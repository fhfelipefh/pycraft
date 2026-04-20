from pathlib import Path
import sys
from zipfile import ZipFile

from ursina import Audio, Button, Entity, Text, camera, color, mouse


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def rgba255(r, g, b, a=255):
    return color.rgba(r / 255, g / 255, b / 255, a / 255)


def resolve_menu_asset_path(candidates):
    for relative_path in candidates:
        if (PROJECT_ROOT / relative_path).exists():
            return Path(relative_path).as_posix()
    return None


def ensure_menu_font_asset(zip_relative_path, member_name):
    font_relative_path = Path(zip_relative_path).with_name(member_name)
    if (PROJECT_ROOT / font_relative_path).exists():
        return font_relative_path.as_posix()

    archive_path = PROJECT_ROOT / zip_relative_path
    if not archive_path.exists():
        return None

    try:
        with ZipFile(archive_path) as archive:
            archive.extract(member_name, archive_path.parent)
    except Exception:
        return None

    if (PROJECT_ROOT / font_relative_path).exists():
        return font_relative_path.as_posix()
    return None


class GameMenu:
    def __init__(
        self,
        player,
        toggle_menu_callback,
        fullscreen_callback,
        music_toggle_callback,
        music_get_enabled_callback,
        music_get_volume_callback,
        music_set_volume_callback,
    ):
        self.menu_open = False
        self.title_open = True
        self.player = player
        self.toggle_menu_callback = toggle_menu_callback
        self.fullscreen_callback = fullscreen_callback
        self.music_toggle_callback = music_toggle_callback
        self.music_get_enabled_callback = music_get_enabled_callback
        self.music_get_volume_callback = music_get_volume_callback
        self.music_set_volume_callback = music_set_volume_callback
        self.menu_button_scale = (0.4, 0.1)
        self.menu_button_position_top = 0.13
        self.settings_button_scale = (0.2, 0.05)
        self.settings_small_button_scale = (0.07, 0.05)
        self.title_font = (
            ensure_menu_font_asset("fonts/minecraft.zip", "Minecraft.ttf")
            or resolve_menu_asset_path(
                ["assets/RPG UI pack - Demo (by Franuka)/FantasyRPGtext (size 8).ttf"]
            )
        )
        # Keep menu visuals fully opaque to avoid compositor/alpha issues
        # that can make the screen look washed-out or blank on some setups.
        self.menu_panel_texture = None
        self.header_panel_texture = None
        self.settings_panel_texture = None
        self.button_texture = None
        self.settings_owner = "menu"
        self.backdrop = Entity(
            parent=camera.ui,
            model="quad",
            color=rgba255(10, 16, 24, 255),
            scale=(2, 2),
            z=0.45,
            enabled=False,
        )
        self.backdrop.always_on_top = True

        self.title_bg = Entity(
            parent=camera.ui,
            model="quad",
            texture=self.menu_panel_texture,
            color=rgba255(28, 36, 50, 255),
            scale=(0.94, 0.8),
            z=0.35,
            enabled=True,
        )
        self.title_bg.always_on_top = True
        self.title_header = Entity(
            parent=self.title_bg,
            model="quad",
            texture=self.header_panel_texture,
            color=rgba255(63, 93, 126, 255),
            position=(0, 0.285, 0.01),
            scale=(0.8, 0.12),
        )

        title_kwargs = {}
        subtitle_kwargs = {}
        if self.title_font is not None:
            title_kwargs["font"] = self.title_font
            subtitle_kwargs["font"] = self.title_font

        self.title_text = Text(
            parent=self.title_bg,
            text="PYCRAFT",
            color=color.rgb(10, 18, 28),
            origin=(0, 0),
            position=(0, 0.285, 0.02),
            scale=3.0,
            **title_kwargs,
        )
        self.title_subtitle = Text(
            parent=self.title_bg,
            text="Explore, construa e sobreviva",
            color=color.rgb(24, 40, 58),
            origin=(0, 0),
            position=(0, 0.12, 0.02),
            scale=1.35,
            **subtitle_kwargs,
        )
        self.btn_start = self._make_button(
            parent=self.title_bg,
            text="Jogar",
            scale=self.menu_button_scale,
            position=(0, 0.01),
            on_click=lambda: (self._play_click(), self.start_game()),
        )
        self.btn_title_settings = self._make_button(
            parent=self.title_bg,
            text="Configuracoes",
            scale=self.menu_button_scale,
            position=(0, -0.11),
            on_click=lambda: (self._play_click(), self.open_settings("title")),
        )
        self.btn_title_exit = self._make_button(
            parent=self.title_bg,
            text="Sair",
            scale=self.menu_button_scale,
            position=(0, -0.23),
            on_click=lambda: (self._play_click(), self.quit_game()),
        )

        self.menu_bg = Entity(
            parent=camera.ui,
            model="quad",
            texture=self.menu_panel_texture,
            color=rgba255(28, 36, 50, 255),
            scale=(0.72, 0.58),
            z=0.35,
            enabled=False,
        )
        self.menu_bg.always_on_top = True
        self.pause_header = Entity(
            parent=self.menu_bg,
            model="quad",
            texture=self.header_panel_texture,
            color=rgba255(63, 93, 126, 255),
            position=(0, 0.205, 0.01),
            scale=(0.74, 0.11),
        )
        self.pause_title = Text(
            parent=self.menu_bg,
            text="PAUSADO",
            color=color.rgb(10, 18, 28),
            origin=(0, 0),
            position=(0, 0.205, 0.02),
            scale=2.15,
            **title_kwargs,
        )
        self.btn_continue = self._make_button(
            parent=self.menu_bg,
            text="Continuar",
            scale=self.menu_button_scale,
            position=(0, self.menu_button_position_top - 0.04),
            on_click=lambda: (self._play_click(), self.toggle_menu(False)),
        )
        self.btn_settings = self._make_button(
            parent=self.menu_bg,
            text="Configuracoes",
            scale=self.menu_button_scale,
            position=(0, -0.01),
            on_click=lambda: (self._play_click(), self.open_settings("menu")),
        )
        self.btn_exit = self._make_button(
            parent=self.menu_bg,
            text="Sair",
            scale=self.menu_button_scale,
            position=(0, -self.menu_button_position_top + 0.02),
            on_click=lambda: (self._play_click(), self.quit_game()),
        )

        self.settings_bg = Entity(
            parent=camera.ui,
            model="quad",
            texture=self.settings_panel_texture,
            color=rgba255(28, 36, 50, 255),
            scale=(0.86, 0.62),
            z=0.35,
            enabled=False,
        )
        self.settings_bg.always_on_top = True
        self.settings_header = Entity(
            parent=self.settings_bg,
            model="quad",
            texture=self.header_panel_texture,
            color=rgba255(63, 93, 126, 255),
            position=(0, 0.225, 0.01),
            scale=(0.78, 0.1),
        )
        self.settings_title = Text(
            parent=self.settings_bg,
            text="CONFIGURACOES",
            color=color.rgb(10, 18, 28),
            origin=(0, 0),
            position=(0, 0.2, 0.02),
            scale=1.8,
            **title_kwargs,
        )
        self.settings_content = Entity(parent=self.settings_bg, enabled=False)
        self.btn_fullscreen = self._make_button(
            parent=self.settings_content,
            text="Tela Cheia",
            scale=self.settings_button_scale,
            position=(0, 0.08),
            on_click=lambda: (self._play_click(), self.toggle_fullscreen()),
        )
        self.btn_music_toggle = self._make_button(
            parent=self.settings_content,
            text="Musica: ON",
            scale=self.settings_button_scale,
            position=(0, 0.0),
            on_click=lambda: (self._play_click(), self.toggle_music()),
        )
        self.btn_music_minus = self._make_button(
            parent=self.settings_content,
            text="-",
            scale=self.settings_small_button_scale,
            position=(-0.13, -0.12),
            on_click=lambda: (self._play_click(), self.adjust_music_volume(-0.05)),
        )
        self.txt_music_volume = Text(
            parent=self.settings_content,
            text="Volume: 25%",
            color=rgba255(178, 216, 255, 230),
            position=(0, -0.125, -0.02),
            origin=(0, 0),
            scale=0.78,
        )
        self.btn_music_plus = self._make_button(
            parent=self.settings_content,
            text="+",
            scale=self.settings_small_button_scale,
            position=(0.13, -0.12),
            on_click=lambda: (self._play_click(), self.adjust_music_volume(0.05)),
        )
        self.btn_back = self._make_button(
            parent=self.settings_content,
            text="Voltar",
            scale=self.settings_button_scale,
            position=(0, -0.22),
            on_click=lambda: (self._play_click(), self.close_settings()),
        )
        self.player.enabled = False
        mouse.locked = False
        self.show_title_screen(trigger_callback=False)

    def _make_button(self, parent, text, scale, position, on_click):
        if isinstance(scale, (tuple, list)):
            scale_x, scale_y = float(scale[0]), float(scale[1])
        else:
            scale_x = scale_y = float(scale)

        parent_scale_x = float(getattr(parent, "scale_x", 1) or 1)
        parent_scale_y = float(getattr(parent, "scale_y", 1) or 1)
        normal_text_scale = 0.88
        hover_text_scale = 1.0

        button = Button(
            parent=parent,
            model="quad",
            texture=self.button_texture,
            color=rgba255(140, 182, 236, 255),
            text=text,
            scale=scale,
            position=position,
            z=0.02,
            highlight_color=rgba255(255, 255, 255, 245),
            pressed_color=rgba255(220, 235, 255, 255),
            text_color=color.rgb(10, 18, 28),
            on_click=on_click,
        )
        button.text_entity.scale_x = normal_text_scale / (parent_scale_x * scale_x)
        button.text_entity.scale_y = normal_text_scale / (parent_scale_y * scale_y)
        button.text_entity.color = color.rgb(10, 18, 28)
        button.always_on_top = True
        button.text_entity.always_on_top = True
        if self.title_font is not None:
            button.text_entity.font = self.title_font

        def _sync_button_text_scale():
            target_scale = hover_text_scale if button.hovered else normal_text_scale
            button.text_entity.scale_x = target_scale / (parent_scale_x * scale_x)
            button.text_entity.scale_y = target_scale / (parent_scale_y * scale_y)

        button.update = _sync_button_text_scale
        return button

    def _play_click(self):
        Audio("sounds/Click_stereo.ogg.mp3", autoplay=True, volume=0.35)

    def _sync_state(self, trigger_callback=True):
        title_or_pause_visible = self.title_open or self.menu_open
        self.backdrop.enabled = False
        self.title_bg.enabled = self.title_open and not self.settings_content.enabled
        self.menu_bg.enabled = self.menu_open and not self.settings_content.enabled
        self.settings_bg.enabled = self.settings_content.enabled
        self.player.enabled = not self.is_blocking_gameplay()
        mouse.locked = not self.is_blocking_gameplay()
        if not title_or_pause_visible and not self.settings_content.enabled:
            self.backdrop.enabled = False
        if trigger_callback:
            self.toggle_menu_callback(self.is_blocking_gameplay())

    def is_blocking_gameplay(self):
        return self.title_open or self.menu_open or self.settings_content.enabled

    def handle_escape(self):
        if self.settings_content.enabled:
            self._play_click()
            self.close_settings()
            return True
        if self.title_open:
            return False
        if self.menu_open:
            self._play_click()
        self.toggle_menu(not self.menu_open)
        return True

    def refresh_music_controls(self):
        music_enabled = bool(self.music_get_enabled_callback())
        self.btn_music_toggle.text = f"Musica: {'ON' if music_enabled else 'OFF'}"
        volume = float(self.music_get_volume_callback())
        self.txt_music_volume.text = f"Volume: {int(round(volume * 100))}%"

    def show_title_screen(self, trigger_callback=True):
        self.title_open = True
        self.menu_open = False
        self.settings_owner = "title"
        self.settings_content.enabled = False
        self._sync_state(trigger_callback=trigger_callback)

    def start_game(self):
        self.title_open = False
        self.menu_open = False
        self.settings_content.enabled = False
        self.settings_bg.enabled = False
        self._sync_state(trigger_callback=True)

    def toggle_menu(self, state):
        if self.title_open:
            return
        self.menu_open = bool(state)
        if self.menu_open:
            self.settings_content.enabled = False
        self._sync_state(trigger_callback=True)

    def open_settings(self, source=None):
        self.settings_owner = source or ("title" if self.title_open else "menu")
        self.settings_content.enabled = True
        self.refresh_music_controls()
        self._sync_state(trigger_callback=True)

    def close_settings(self):
        self.settings_content.enabled = False
        if self.settings_owner == "title":
            self.title_open = True
            self.menu_open = False
        self._sync_state(trigger_callback=True)

    def toggle_music(self):
        self.music_toggle_callback()
        self.refresh_music_controls()

    def adjust_music_volume(self, delta):
        self.music_set_volume_callback(delta)
        self.refresh_music_controls()

    def toggle_fullscreen(self):
        self.fullscreen_callback()

    def quit_game(self):
        sys.exit()
