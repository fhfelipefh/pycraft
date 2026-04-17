from ursina import *
import ursina.application as appmod
import sys

class GameMenu:
    def __init__(self, player, toggle_menu_callback, fullscreen_callback):
        self.menu_open = False
        self.player = player
        self.toggle_menu_callback = toggle_menu_callback
        self.fullscreen_callback = fullscreen_callback
        self.menu_bg = Entity(
            parent=camera.ui,
            scale=(0.5, 0.5),
            enabled=False
        )
        self.btn_continue = Button(
            text='Continuar',
            scale=(0.4, 0.1),
            position=(0, 0.13),
            parent=self.menu_bg,
            on_click=lambda: self.toggle_menu(False)
        )
        self.btn_settings = Button(
            text='Configurações',
            scale=(0.4, 0.1),
            position=(0, 0),
            parent=self.menu_bg,
            on_click=self.open_settings
        )
        self.btn_exit = Button(
            text='Sair',
            scale=(0.4, 0.1),
            position=(0, -0.13),
            parent=self.menu_bg,
            on_click=self.quit_game
        )
        self.settings_bg = Entity(
            parent=camera.ui,
            scale=(0.52, 0.3),
            enabled=False
        )
        self.btn_fullscreen = Button(
            text='Alternar Tela Cheia',
            scale=(0.48, 0.1),
            position=(0, 0.05),
            parent=self.settings_bg,
            on_click=self.toggle_fullscreen
        )
        self.btn_back = Button(
            text='Voltar',
            scale=(0.35, 0.1),
            position=(0, -0.08),
            parent=self.settings_bg,
            on_click=self.close_settings
        )
        self.close_settings()

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

    def close_settings(self):
        self.menu_bg.enabled = self.menu_open
        self.settings_bg.enabled = False

    def toggle_fullscreen(self):
        self.fullscreen_callback()

    def quit_game(self):
        sys.exit()
