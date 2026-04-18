from ursina import *
import ursina.application as appmod
import sys


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
        self.menu_bg = Entity(
            parent=camera.ui,
            model='quad',
            texture='ui/Inworld_menu_background.png',
            scale=(0.5, 0.5),
            enabled=False
        )
        self.btn_continue = Button(
            text='Continuar',
            scale=self.menu_button_scale,
            position=(0, self.menu_button_position_top),
            parent=self.menu_bg,
            on_click=lambda: (Audio('sounds/Click_stereo.ogg.mp3', autoplay=True, volume=0.35), self.toggle_menu(False))
        )
        self.btn_settings = Button(
            text='Configurações',
            scale=self.menu_button_scale,
            position=(0, 0),
            parent=self.menu_bg,
            on_click=lambda: (Audio('sounds/Click_stereo.ogg.mp3', autoplay=True, volume=0.35), self.open_settings())
        )
        self.btn_exit = Button(
            text='Sair',
            scale=self.menu_button_scale,
            position=(0, -self.menu_button_position_top),
            parent=self.menu_bg,
            on_click=lambda: (Audio('sounds/Click_stereo.ogg.mp3', autoplay=True, volume=0.35), self.quit_game())
        )
        self.settings_bg = Entity(
            parent=camera.ui,
            model='quad',
            texture='ui/Menu_list_background.png',
            scale=(0.62, 0.50),
            enabled=False
        )
        self.settings_content = Entity(
            parent=camera.ui,
            enabled=False
        )
        self.btn_fullscreen = Button(
            text='Tela Cheia',
            scale=self.settings_button_scale,
            position=(0, 0.12),
            parent=self.settings_content,
            on_click=lambda: (Audio('sounds/Click_stereo.ogg.mp3', autoplay=True, volume=0.35), self.toggle_fullscreen())
        )
        self.btn_music_toggle = Button(
            text='Musica: ON',
            scale=self.settings_button_scale,
            position=(0, 0.045),
            parent=self.settings_content,
            on_click=lambda: (Audio('sounds/Click_stereo.ogg.mp3', autoplay=True, volume=0.35), self.toggle_music())
        )
        self.btn_music_minus = Button(
            text='-',
            scale=self.settings_small_button_scale,
            position=(-0.13, -0.11),
            parent=self.settings_content,
            on_click=lambda: (Audio('sounds/Click_stereo.ogg.mp3', autoplay=True, volume=0.35), self.adjust_music_volume(-0.05))
        )
        self.txt_music_volume = Text(
            text='Volume: 25%',
            position=(0, -0.117),
            parent=self.settings_content,
            origin=(0, 0),
            scale=0.52,
        )
        self.btn_music_plus = Button(
            text='+',
            scale=self.settings_small_button_scale,
            position=(0.13, -0.11),
            parent=self.settings_content,
            on_click=lambda: (Audio('sounds/Click_stereo.ogg.mp3', autoplay=True, volume=0.35), self.adjust_music_volume(0.05))
        )
        self.btn_back = Button(
            text='Voltar',
            scale=self.settings_button_scale,
            position=(0, -0.21),
            parent=self.settings_content,
            on_click=lambda: (Audio('sounds/Click_stereo.ogg.mp3', autoplay=True, volume=0.35), self.close_settings())
        )
        self.close_settings()

    def refresh_music_controls(self):
        music_enabled = bool(self.music_get_enabled_callback())
        self.btn_music_toggle.text = f"Musica: {'ON' if music_enabled else 'OFF'}"
        volume = float(self.music_get_volume_callback())
        self.txt_music_volume.text = f"Volume: {int(round(volume * 100))}%"

    def toggle_menu(self, state):
        self.menu_open = state
        self.menu_bg.enabled = state
        self.player.enabled = not state
        mouse.locked = not state
        if state:
            self.close_settings()
        self.toggle_menu_callback(state)

    def open_settings(self):
        self.menu_bg.enabled = False
        self.settings_bg.enabled = True
        self.settings_content.enabled = True
        self.refresh_music_controls()

    def close_settings(self):
        self.menu_bg.enabled = self.menu_open
        self.settings_bg.enabled = False
        self.settings_content.enabled = False

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
