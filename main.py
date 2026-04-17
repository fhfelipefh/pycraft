from pathlib import Path
import math
import random

from ursina import (
    Audio,
    Entity,
    Sky,
    Ursina,
    Vec3,
    application,
    camera,
    color,
    destroy,
    invoke,
    mouse,
    raycast,
    scene,
    time,
    window,
)
from ursina.shaders import unlit_shader
from ursina.prefabs.first_person_controller import FirstPersonController

from menu import GameMenu

app = Ursina(development_mode=False, editor_ui_enabled=False, fullscreen=False, borderless=False)
BASE_DIR = Path(__file__).resolve().parent
application.asset_folder = BASE_DIR
window.fullscreen = False

for ui_name in ("exit_button", "cog_button", "fps_counter", "entity_counter", "collider_counter"):
    ui_element = getattr(window, ui_name, None)
    if ui_element is not None:
        ui_element.enabled = False

TEXTURE_PATH = Path("textures/blocks").as_posix()
UI_PATH = Path("ui").as_posix()
SKY_PATH = Path("skybox/generated").as_posix()
DAMAGE_SOUND_PATH = Path("sounds/damage.wav").as_posix()
WALK_SOUND_PATH = Path("sounds/walk-sound.wav").as_posix()
GROUND_Y = 0
RENDER_RADIUS = 16
RENDER_HEIGHT = 12
CUSTOM_RENDER_RADIUS = 48
CUSTOM_RENDER_HEIGHT = 24
PRIORITY_GROUND_RADIUS = 3
SUN_CYCLE_SECONDS = 20 * 60
CLOUD_CYCLE_SECONDS = 9 * 60


def resolve_asset_path(relative_path):
    return (BASE_DIR / relative_path).resolve()


def resolve_existing_asset_path(candidates):
    for relative_path in candidates:
        if resolve_asset_path(relative_path).exists():
            # Ursina resolves textures relative to application.asset_folder.
            # Returning relative paths avoids Panda warnings for missing absolute textures.
            return relative_path
    return None


def resolve_existing_asset_or_fallback(candidates, fallback_texture="white_cube"):
    resolved_path = resolve_existing_asset_path(candidates)
    if resolved_path is not None:
        return resolved_path
    return fallback_texture

BLOCK_TYPES = [
    {
        "name": "Grama",
        "block_texture": "grass_carried.png",
        "icon_texture": "grass_carried.png",
        "material": "grass",
    },
    {
        "name": "Tabua de Madeira",
        "block_texture": "planks_birch.png",
        "icon_texture": "planks_birch.png",
        "material": "wood",
    },
    {
        "name": "Pedra",
        "block_texture": "stone.png",
        "icon_texture": "stone.png",
        "material": "stone",
    },
    {
        "name": "Terra",
        "block_texture": "dirt.png",
        "icon_texture": "dirt.png",
        "material": "dirt",
    },
]
GROUND_BLOCK_TYPE = BLOCK_TYPES[0]

for block_type in BLOCK_TYPES:
    block_texture_path = resolve_existing_asset_path(
        [f"{TEXTURE_PATH}/{block_type['block_texture']}"]
    )
    icon_texture_path = resolve_existing_asset_path(
        [f"{TEXTURE_PATH}/{block_type.get('icon_texture', block_type['block_texture'])}"]
    )
    block_type["block_texture_path"] = block_texture_path or "white_cube"
    block_type["icon_texture_path"] = icon_texture_path or block_type["block_texture_path"]

SOUND_GROUPS = {
    "default": {
        "step": {"files": [WALK_SOUND_PATH], "volume": 0.3, "pitch": 1.0},
    },
    "wood": {
        "break": {
            "files": [
                "sounds/wood_dig1.ogg",
                "sounds/wood_dig2.ogg",
                "sounds/wood_dig3.ogg",
                "sounds/Wood_dig4.ogg",
            ],
            "volume": 1.0,
            "pitch": (0.8, 1.0),
        },
        "place": {
            "files": [
                "sounds/wood_dig1.ogg",
                "sounds/wood_dig2.ogg",
                "sounds/wood_dig3.ogg",
                "sounds/Wood_dig4.ogg",
            ],
            "volume": 1.0,
            "pitch": 0.8,
        },
        "hit": {
            "files": [
                "sounds/Wood_hit1.ogg",
                "sounds/Wood_hit2.ogg",
                "sounds/wood_hit3.ogg",
                "sounds/wood_hit5.ogg",
                "sounds/wood_hit6.ogg",
            ],
            "volume": 0.23,
            "pitch": 0.5,
        },
        "step": {"files": [WALK_SOUND_PATH], "volume": 0.3, "pitch": 1.0},
        "jump": {
            "files": [
                "sounds/wood_jump1.ogg",
                "sounds/wood_jump2.ogg",
                "sounds/wood_jump3.ogg",
                "sounds/wood_jump4.ogg",
            ],
            "volume": 0.12,
            "pitch": 1.0,
        },
        "land": {
            "files": [
                "sounds/wood_jump1.ogg",
                "sounds/wood_jump2.ogg",
                "sounds/wood_jump3.ogg",
                "sounds/wood_jump4.ogg",
            ],
            "volume": 0.18,
            "pitch": 1.0,
        },
    },
    "stone": {
        "break": {
            "files": [
                "sounds/Stone_dig1.ogg",
                "sounds/Stone_dig2.ogg",
                "sounds/Stone_dig3.ogg",
                "sounds/stone_dig4.ogg",
            ],
            "volume": 1.0,
            "pitch": (0.8, 1.0),
        },
        "place": {
            "files": [
                "sounds/Stone_dig1.ogg",
                "sounds/Stone_dig2.ogg",
                "sounds/Stone_dig3.ogg",
                "sounds/stone_dig4.ogg",
            ],
            "volume": 1.0,
            "pitch": 0.8,
        },
        "hit": {
            "files": [
                "sounds/Stone_mining1.ogg",
                "sounds/Stone_mining2.ogg",
            ],
            "volume": 0.25,
            "pitch": 0.5,
        },
        "step": {
            "files": [
                "sounds/Stone_hit1.ogg",
                "sounds/Stone_hit2.ogg",
                "sounds/Stone_hit3.ogg",
            ],
            "volume": 0.15,
            "pitch": 1.0,
        },
        "land": {
            "files": [
                "sounds/Stone_hit1.ogg",
                "sounds/Stone_hit2.ogg",
                "sounds/Stone_hit3.ogg",
            ],
            "volume": 0.5,
            "pitch": 0.75,
        },
    },
}

fullscreen_state = [False]
selected_block_index = 0
highlighted_box = [None]
step_cooldown = [0.0]
was_grounded = [True]
last_support_block = [None]
last_render_cell = [None]
sun_elapsed_time = [0.0]
cloud_offset = [0.0]
light_update_timer = [0.0]
current_light_level = [255]

active_blocks = {}
custom_blocks = {}
removed_blocks = set()


def toggle_fullscreen():
    window.fullscreen = not window.fullscreen
    fullscreen_state[0] = window.fullscreen


def get_block_texture(block_type):
    return block_type["block_texture_path"]


def get_block_icon_texture(block_type):
    return block_type["icon_texture_path"]


def get_selected_block_type():
    return BLOCK_TYPES[selected_block_index]


def to_grid_position(position):
    return tuple(int(round(value)) for value in position)


def play_sound_group(group_name, event_name):
    group = SOUND_GROUPS.get(group_name, {})
    sound_data = group.get(event_name)
    if not sound_data:
        return

    pitch = sound_data["pitch"]
    if isinstance(pitch, tuple):
        pitch = random.uniform(*pitch)

    Audio(
        random.choice(sound_data["files"]),
        autoplay=True,
        volume=sound_data["volume"],
        pitch=pitch,
    )


def play_material_sound(block_type, event_name):
    material = block_type["material"]
    if material == "wood":
        play_sound_group("wood", event_name)
    elif material == "stone":
        play_sound_group("stone", event_name)
    elif event_name == "step":
        play_sound_group("default", event_name)


def get_block_type_at(position):
    if position in removed_blocks:
        return None
    if position in custom_blocks:
        return custom_blocks[position]
    if position[1] == GROUND_Y:
        return GROUND_BLOCK_TYPE
    return None


def create_block_entity(position, block_type):
    block = Entity(
        parent=scene,
        model="cube",
        position=position,
        texture=get_block_texture(block_type),
        origin_y=0.5,
        collider="box",
        shader=unlit_shader,
        color=color.white,
    )
    block.block_type = block_type
    block.grid_position = position
    apply_lighting_to_entity(block)
    active_blocks[position] = block
    return block


def remove_block_entity(position):
    block = active_blocks.pop(position, None)
    if block is not None:
        destroy(block)


def set_block_at(position, block_type):
    removed_blocks.discard(position)

    if position[1] == GROUND_Y and block_type == GROUND_BLOCK_TYPE:
        custom_blocks.pop(position, None)
    else:
        custom_blocks[position] = block_type

    active_block = active_blocks.get(position)
    if active_block is None:
        if position in get_desired_positions(last_render_cell[0]):
            create_block_entity(position, block_type)
        return

    active_block.texture = get_block_texture(block_type)
    active_block.block_type = block_type


def remove_block_at(position):
    custom_blocks.pop(position, None)
    if position[1] == GROUND_Y:
        removed_blocks.add(position)
    remove_block_entity(position)


def get_desired_positions(render_cell):
    if render_cell is None:
        return set()

    px, py, pz = render_cell
    desired = set()

    for dx in range(-RENDER_RADIUS, RENDER_RADIUS + 1):
        for dz in range(-RENDER_RADIUS, RENDER_RADIUS + 1):
            desired.add((px + dx, GROUND_Y, pz + dz))

    for position in custom_blocks:
        if (
            abs(position[0] - px) <= CUSTOM_RENDER_RADIUS
            and abs(position[2] - pz) <= CUSTOM_RENDER_RADIUS
            and abs(position[1] - py) <= CUSTOM_RENDER_HEIGHT
        ):
            desired.add(position)

            for dx in range(-PRIORITY_GROUND_RADIUS, PRIORITY_GROUND_RADIUS + 1):
                for dz in range(-PRIORITY_GROUND_RADIUS, PRIORITY_GROUND_RADIUS + 1):
                    ground_position = (position[0] + dx, GROUND_Y, position[2] + dz)
                    if ground_position not in removed_blocks:
                        desired.add(ground_position)

    return desired


def sync_active_blocks(force=False):
    render_cell = to_grid_position(player.position)
    if not force and render_cell == last_render_cell[0]:
        return

    desired_positions = get_desired_positions(render_cell)
    current_positions = set(active_blocks)

    for position in current_positions - desired_positions:
        remove_block_entity(position)

    for position in desired_positions - current_positions:
        block_type = get_block_type_at(position)
        if block_type is not None:
            create_block_entity(position, block_type)

    last_render_cell[0] = render_cell


def get_target_block():
    hovered = mouse.hovered_entity
    if hovered is not None and hasattr(hovered, "block_type"):
        return hovered
    return None


def highlight_box(box):
    if highlighted_box[0] is box:
        return
    if highlighted_box[0] is not None:
        apply_lighting_to_entity(highlighted_box[0])
    if box is not None:
        level = min(255, current_light_level[0] + 32)
        box.color = color.rgba(level, level, level, 255)
    highlighted_box[0] = box


def update_highlight():
    highlight_box(get_target_block())


def get_supporting_block():
    hit = raycast(
        player.position + Vec3(0, 0.1, 0),
        Vec3(0, -1, 0),
        distance=2,
        ignore=(player,),
    )
    if hit.hit and hasattr(hit.entity, "block_type"):
        return hit.entity
    return None


def set_global_light_level(daylight):
    current_light_level[0] = int(145 + (110 * daylight))


def apply_lighting_to_entity(entity):
    entity.color = color.white


def refresh_active_block_lighting():
    for block in active_blocks.values():
        apply_lighting_to_entity(block)


sky_base_texture = resolve_existing_asset_or_fallback(
    [
        f"{SKY_PATH}/sky_base.png",
        f"{SKY_PATH}/sky_dome.png",
        f"{SKY_PATH}/sky_base.png",
        "skybox/Sky_Box.png",
        "skybox/skybox-minecraft-daylight/textures/sky_minecraft.png",
    ]
)

cloud_layer_texture = resolve_existing_asset_or_fallback(
    [
        f"{SKY_PATH}/sky_clouds.png",
        f"{SKY_PATH}/sky_clouds_dome.png",
    ],
    fallback_texture=sky_base_texture,
)

sky_base = Sky(texture=sky_base_texture)
cloud_layer = Sky(texture=cloud_layer_texture, color=color.rgba(255, 255, 255, 210))
cloud_layer.scale *= 0.995

sun_visual = Entity(
    parent=scene,
    model="quad",
    scale=14,
    color=color.rgb(255, 250, 235),
    unlit=True,
    double_sided=True,
)

sun_glow = Entity(
    parent=sun_visual,
    model="quad",
    scale=1.2,
    color=color.rgba(255, 235, 180, 36),
    unlit=True,
    double_sided=True,
)

player = FirstPersonController()
spawn_point = Vec3(player.x, player.y, player.z)
set_global_light_level(1.0)
sync_active_blocks(force=True)

menu = None


def on_menu_toggle(state):
    pass


menu = GameMenu(player, on_menu_toggle, toggle_fullscreen)

hotbar_bg = Entity(
    parent=camera.ui,
    model="quad",
    texture=resolve_existing_asset_path([f"{UI_PATH}/Hotbar.png"]) or "white_cube",
    position=(0, -0.45, 1),
    scale=(0.8, 0.0967),
)

hotbar_selector = Entity(
    parent=camera.ui,
    model="quad",
    texture=resolve_existing_asset_path([f"{UI_PATH}/Hotbar_selector.png"]) or "white_cube",
    position=(0, -0.45, 0.9),
    scale=(0.1055, 0.1055),
)

hotbar_icons = []
hotbar_slot_positions = []


def create_hotbar_ui():
    slot_spacing = hotbar_bg.scale_x * (40 / 364)
    start_x = hotbar_bg.x - (hotbar_bg.scale_x / 2) + (hotbar_bg.scale_x * (21.5 / 364))
    icon_scale = (slot_spacing * 0.78, hotbar_bg.scale_y * 0.72)
    icon_y = hotbar_bg.y + (hotbar_bg.scale_y * 0.015)

    for index, block_type in enumerate(BLOCK_TYPES):
        slot_x = start_x + (index * slot_spacing)
        hotbar_slot_positions.append(slot_x)
        hotbar_icons.append(
            Entity(
                parent=camera.ui,
                model="quad",
                texture=get_block_icon_texture(block_type),
                position=(slot_x, icon_y, 0.8),
                scale=icon_scale,
            )
        )


def update_hotbar_ui():
    hotbar_selector.x = hotbar_slot_positions[selected_block_index]


create_hotbar_ui()
update_hotbar_ui()

flash = Entity(
    parent=camera.ui,
    model="quad",
    color=color.rgba(255, 255, 255, 0),
    scale=(2, 2),
    z=-100,
    enabled=True,
)


def respawn_flash():
    flash.color = color.rgba(255, 255, 255, 180)
    Audio(DAMAGE_SOUND_PATH, autoplay=True)
    invoke(lambda *_: setattr(flash, "color", color.rgba(255, 255, 255, 0)), 0.25)


def input(key):
    global selected_block_index

    if key == "escape":
        if menu:
            menu.toggle_menu(not menu.menu_open)
        return

    if not menu or menu.menu_open:
        return

    if key.isdigit():
        idx = int(key) - 1
        if 0 <= idx < len(BLOCK_TYPES):
            selected_block_index = idx
            update_hotbar_ui()

    if key == "scroll up":
        selected_block_index = (selected_block_index + 1) % len(BLOCK_TYPES)
        update_hotbar_ui()
        return

    if key == "scroll down":
        selected_block_index = (selected_block_index - 1) % len(BLOCK_TYPES)
        update_hotbar_ui()
        return

    if key == "space":
        support_block = last_support_block[0]
        if player.enabled and player.grounded and support_block is not None:
            play_material_sound(support_block.block_type, "jump")
        return

    target_block = get_target_block()
    if target_block is None:
        return

    if key == "right mouse down":
        new_position = to_grid_position(target_block.position + mouse.normal)
        if get_block_type_at(new_position) is None:
            block_type = get_selected_block_type()
            set_block_at(new_position, block_type)
            play_material_sound(block_type, "place")
        return

    if key == "left mouse down":
        play_material_sound(target_block.block_type, "hit")
        play_material_sound(target_block.block_type, "break")
        remove_block_at(target_block.grid_position)
        highlight_box(None)


def update():
    sync_active_blocks()
    update_highlight()

    sun_elapsed_time[0] = (sun_elapsed_time[0] + time.dt) % SUN_CYCLE_SECONDS
    day_progress = sun_elapsed_time[0] / SUN_CYCLE_SECONDS
    sun_angle = math.pi * (0.1 + (day_progress * 0.8))
    sun_direction = Vec3(0, math.sin(sun_angle), -math.cos(sun_angle)).normalized()

    sun_visual.position = player.position + (sun_direction * 300)
    sun_visual.look_at(camera.world_position)
    cloud_offset[0] = (cloud_offset[0] + (time.dt / CLOUD_CYCLE_SECONDS)) % 1
    cloud_layer.texture_offset = (cloud_offset[0], 0)

    daylight = max(0.18, min(1.0, (sun_direction.y + 0.2) / 1.2))
    set_global_light_level(daylight)

    current_grounded = player.grounded if hasattr(player, "grounded") else player.y <= 1
    support_block = get_supporting_block()
    last_support_block[0] = support_block

    if player.y < spawn_point.y - 64:
        player.position = spawn_point
        respawn_flash()
        sync_active_blocks(force=True)
        return

    moving = False
    if hasattr(player, "input_direction"):
        moving = player.input_direction.magnitude() > 0.1

    if current_grounded and not was_grounded[0] and support_block is not None:
        play_material_sound(support_block.block_type, "land")

    if player.enabled and moving and current_grounded:
        step_cooldown[0] -= time.dt
        if step_cooldown[0] <= 0:
            if support_block is not None:
                play_material_sound(support_block.block_type, "step")
            else:
                play_sound_group("default", "step")
            step_cooldown[0] = 0.32
    else:
        step_cooldown[0] = 0.0

    light_update_timer[0] -= time.dt
    if light_update_timer[0] <= 0:
        refresh_active_block_lighting()
        if highlighted_box[0] is not None:
            highlight_box(highlighted_box[0])
        light_update_timer[0] = 0.25

    was_grounded[0] = current_grounded


app.run()
