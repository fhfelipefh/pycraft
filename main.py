from pathlib import Path
import math
import random

from ursina import (
    Audio,
    Entity,
    Sky,
    Ursina,
    Vec3,
    load_texture,
    application,
    camera,
    color,
    destroy,
    held_keys,
    invoke,
    mouse,
    raycast,
    scene,
    time,
    window,
)
from ursina.shaders import unlit_shader
from mob_textures import apply_texture_recursively
from mob_grounding import get_support_top_y, compute_lift_delta, compute_grounded_entity_y
from ursina.prefabs.first_person_controller import FirstPersonController

from menu import GameMenu

app = Ursina(development_mode=False, editor_ui_enabled=False, fullscreen=False, borderless=False, title="pycraft")
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
RENDER_RADIUS = 28
RENDER_HEIGHT = 12
CUSTOM_RENDER_RADIUS = 84
CUSTOM_RENDER_HEIGHT = 24
PRIORITY_GROUND_RADIUS = 3
SUN_CYCLE_SECONDS = 20 * 60
CLOUD_CYCLE_SECONDS = 9 * 60
BLOCK_INTERACTION_RANGE = 20
WALK_SPEED_MULTIPLIER = 1.0
RUN_SPEED_MULTIPLIER = 1.5


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


def _compose_rgba_if_opacity_exists(diffuse_path: str) -> str:
    """If a corresponding *_opacity.png exists, compose an RGBA copy on-the-fly.

    Returns the path to the composed file if created, otherwise the original
    diffuse_path. This is a best-effort function and silently falls back when
    Pillow is not available.
    """
    try:
        from PIL import Image  # optional dependency
    except Exception:
        return diffuse_path

    diffuse_abs = resolve_asset_path(diffuse_path)
    stem = diffuse_abs.stem
    suffix = diffuse_abs.suffix
    opacity_abs = diffuse_abs.with_name(f"{stem}_opacity{suffix}")
    if not opacity_abs.exists():
        return diffuse_path

    generated_rel = Path("textures/_generated").as_posix()
    generated_dir = resolve_asset_path(generated_rel)
    generated_dir.mkdir(parents=True, exist_ok=True)
    out_rel = f"{generated_rel}/{stem}_rgba{suffix}"
    out_abs = resolve_asset_path(out_rel)

    try:
        if not out_abs.exists() or out_abs.stat().st_mtime < max(diffuse_abs.stat().st_mtime, opacity_abs.stat().st_mtime):
            base = Image.open(diffuse_abs).convert("RGB")
            alpha_img = Image.open(opacity_abs).convert("L").resize(base.size)
            rgba = Image.merge("RGBA", (*base.split(), alpha_img))
            rgba.save(out_abs)
        return out_rel
    except Exception:
        return diffuse_path


def load_texture_or_fallback(path_like, use_opacity_map=True):
    """Load a texture and fall back to a default when missing.

    Explicitly loading and then forcing the texture on FBX submeshes avoids
    cases where models render totalmente brancos (sem textura) em alguns
    drivers/versões.
    """
    # Compose RGBA with *_opacity.png when disponível
    candidate = _compose_rgba_if_opacity_exists(path_like) if use_opacity_map else path_like
    resolved = resolve_existing_asset_or_fallback([candidate])
    try:
        tex = load_texture(resolved)
        return tex or load_texture("white_cube")
    except Exception:
        return load_texture("white_cube")


def apply_texture_recursively(entity, texture_obj):
    # Aplica a textura no entity e em todos os filhos.
    try:
        entity.texture = texture_obj
    except Exception:
        pass
    try:
        entity.setTwoSided(True)
    except Exception:
        pass
    for child in getattr(entity, "children", ()):
        apply_texture_recursively(child, texture_obj)


def get_existing_sound_files(candidates):
    return [sound_file for sound_file in candidates if resolve_asset_path(sound_file).exists()]


def get_entity_model_min_y(entity):
    try:
        tight_bounds = entity.model.get_tight_bounds()
        if tight_bounds:
            min_point, _ = tight_bounds
            return float(min_point.y)
    except Exception:
        pass
    return -0.5


def get_support_top_y_under_entity(entity, probe_height=6.0, probe_distance=24.0):
    hit = raycast(
        Vec3(entity.x, entity.y + probe_height, entity.z),
        Vec3(0, -1, 0),
        distance=probe_distance,
        ignore=(entity,),
    )
    if hit.hit and hasattr(hit.entity, "block_type"):
        return float(hit.world_point.y)
    return None


def lift_entity_out_of_blocks(entity, footprint=0.5, epsilon=0.01):
    support_top = get_support_top_y_under_entity(entity)
    if support_top is None:
        block_positions = tuple(active_blocks.keys())
        support_top = get_support_top_y(block_positions, entity.x, entity.z, footprint=footprint)
    if support_top is None:
        return False

    model_min_y = get_entity_model_min_y(entity)
    scale_y = getattr(entity, "scale_y", 1.0) or 1.0
    grounded_y = compute_grounded_entity_y(model_min_y, scale_y, support_top, epsilon=epsilon)
    if grounded_y is None:
        return False

    if abs(entity.y - grounded_y) > 1e-4:
        entity.y = grounded_y
        return True
    return False

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

    available_files = get_existing_sound_files(sound_data["files"])
    if not available_files:
        return

    pitch = sound_data["pitch"]
    if isinstance(pitch, tuple):
        pitch = random.uniform(*pitch)

    Audio(
        random.choice(available_files),
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


def can_interact_with_block(block_entity):
    if block_entity is None:
        return False

    try:
        block_position = block_entity.position
    except AssertionError:
        return False

    if block_position is None:
        return False

    return (player.position - block_position).length() <= BLOCK_INTERACTION_RANGE


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
        f"{SKY_PATH}/sky_clouds_dome.png",
        f"{SKY_PATH}/sky_clouds.png",
    ],
    fallback_texture=sky_base_texture,
)

sky_base = Sky(texture=sky_base_texture)

# Procedural cloud system: one dense pass with deterministic noise and soft fade.
def cloud_noise(grid_x, grid_z, salt=0):
    value = math.sin((grid_x * 127.1) + (grid_z * 311.7) + (salt * 74.7)) * 43758.5453
    return value - math.floor(value)


CLOUD_GRID_SIZE = 220
CLOUD_VIEW_RADIUS = 0
CLOUD_SPAWN_THRESHOLD = 1.0
CLOUD_FADE_RADIUS = CLOUD_GRID_SIZE * 4.2
CLOUD_MIN_HEIGHT = 28
CLOUD_MAX_HEIGHT = 92
CLOUD_MIN_SCALE = 260
CLOUD_MAX_SCALE = 760
CLOUD_MIN_ALPHA = 72
CLOUD_MAX_ALPHA = 240

active_clouds = {}  # Key: (grid_x, grid_z), Value: Entity
cloud_pool = []


def get_or_create_cloud():
    if cloud_pool:
        cloud = cloud_pool.pop()
        cloud.show()
        for puff in getattr(cloud, "cloud_puffs", []):
            puff.show()
        return cloud

    cloud = Entity(
        parent=scene,
        enabled=True,
    )

    cloud.cloud_puffs = []
    puff_specs = [
        (-0.18, 0.02, 0.95, 0.96, 0.96),
        (0.12, -0.03, 0.78, 1.08, 0.82),
        (0.0, 0.05, 1.12, 0.90, 1.00),
        (0.22, 0.01, 0.70, 0.80, 0.88),
    ]

    for offset_x, offset_y, scale_factor, alpha_factor, width_factor in puff_specs:
        puff = Entity(
            parent=cloud,
            model="quad",
            texture=cloud_layer_texture,
            color=color.rgba(255, 255, 255, 255),
            position=Vec3(offset_x, offset_y, 0),
            scale=(1, 1),
            double_sided=True,
            unlit=True,
        )
        puff.scale_factor = scale_factor
        puff.alpha_factor = alpha_factor
        puff.width_factor = width_factor
        cloud.cloud_puffs.append(puff)

    return cloud


def return_cloud_to_pool(cloud):
    cloud.hide()
    for puff in getattr(cloud, "cloud_puffs", []):
        puff.hide()
    cloud_pool.append(cloud)

chicken_model_path = resolve_existing_asset_or_fallback(["mobs/minecraft-chicken/source/chicken.fbx"])
chicken_tex_obj = load_texture_or_fallback("mobs/minecraft-chicken/textures/chicken.png")
chicken = Entity(
    parent=scene,
    model=chicken_model_path,
    texture=chicken_tex_obj,
    position=Vec3(4, 0.53, 4),
    scale=0.07,
    rotation_y=180,
    unlit=True,
)
apply_texture_recursively(chicken, chicken_tex_obj)
chicken.setTwoSided(True)
chicken.collider = "box"

chicken_spawn_position = Vec3(chicken.x, chicken.y, chicken.z)
chicken_walk_target = [None]
chicken_walk_speed = 0.9
chicken_walk_radius = 6.0
chicken_walk_reach_distance = 0.35
chicken_animation_time = [0.0]
chicken_body_bob = [0.0]

chicken_left_leg = Entity(
    parent=chicken,
    model="cube",
    color=color.rgb(92, 68, 34),
    scale=(0.035, 0.16, 0.035),
    position=Vec3(-0.05, -0.17, 0.03),
    origin_y=0.5,
)

chicken_right_leg = Entity(
    parent=chicken,
    model="cube",
    color=color.rgb(92, 68, 34),
    scale=(0.035, 0.16, 0.035),
    position=Vec3(0.05, -0.17, 0.03),
    origin_y=0.5,
)

chicken_left_wing = Entity(
    parent=chicken,
    model="cube",
    color=color.rgb(236, 228, 208),
    scale=(0.05, 0.025, 0.11),
    position=Vec3(-0.12, 0.03, 0.0),
    origin_x=0.5,
)

chicken_right_wing = Entity(
    parent=chicken,
    model="cube",
    color=color.rgb(236, 228, 208),
    scale=(0.05, 0.025, 0.11),
    position=Vec3(0.12, 0.03, 0.0),
    origin_x=-0.5,
)


def mob_position_is_blocked(position, player_radius=0.75):
    if position.y < GROUND_Y + 0.05:
        return True

    player_distance = Vec3(position.x - player.x, 0, position.z - player.z).length()
    if player_distance < player_radius and abs(position.y - player.y) < 1.4:
        return True

    for block in active_blocks.values():
        block_position = block.grid_position
        if abs(block_position[1] - position.y) > 1.2:
            continue

        dx = abs(block_position[0] - position.x)
        dz = abs(block_position[2] - position.z)
        if dx < 0.48 and dz < 0.48:
            return True

    return False


def chicken_position_is_blocked(position):
    return mob_position_is_blocked(position, player_radius=0.75)


def update_chicken_animation(move_amount):
    chicken_animation_time[0] += time.dt * (2.5 + (move_amount * 6.0))
    walk_cycle = chicken_animation_time[0] * (5.0 if move_amount > 0.01 else 1.6)

    leg_swing = math.sin(walk_cycle) * (28 if move_amount > 0.01 else 5)
    wing_swing = math.sin(walk_cycle * 1.7) * (18 if move_amount > 0.01 else 3)
    bob = 0.0

    chicken_left_leg.rotation_x = leg_swing
    chicken_right_leg.rotation_x = -leg_swing
    chicken_left_wing.rotation_z = wing_swing
    chicken_right_wing.rotation_z = -wing_swing

    chicken_body_bob[0] = bob
    chicken.y = chicken_spawn_position.y
    chicken.rotation_z = math.sin(chicken_animation_time[0] * 0.7) * 1.4


def get_new_chicken_walk_target():
    offset_x = random.uniform(-chicken_walk_radius, chicken_walk_radius)
    offset_z = random.uniform(-chicken_walk_radius, chicken_walk_radius)
    return Vec3(
        chicken_spawn_position.x + offset_x,
        chicken_spawn_position.y,
        chicken_spawn_position.z + offset_z,
    )


def create_ambient_mob(name, model_path, texture_path, position, scale, walk_speed, walk_radius, rotation_y=180, tint=color.white, player_radius=0.75, ground_offset=0.0, floating=False, use_opacity_map=True):
    spawn_position = Vec3(position.x, position.y + ground_offset, position.z)
    model_resolved = resolve_existing_asset_or_fallback([model_path])
    tex_obj = load_texture_or_fallback(texture_path, use_opacity_map=use_opacity_map)
    mob = Entity(
        parent=scene,
        model=model_resolved,
        texture=tex_obj,
        position=spawn_position,
        scale=scale,
        rotation_y=rotation_y,
        unlit=True,
        color=tint,
    )
    apply_texture_recursively(mob, tex_obj)
    mob.setTwoSided(True)
    mob.collider = "box"
    grounded_y = mob.y
    if not floating:
        # Garante que o mob não nasça enterrado no terreno/blocos.
        if lift_entity_out_of_blocks(mob):
            grounded_y = mob.y
    return {
        "name": name,
        "entity": mob,
        "spawn": Vec3(mob.x, grounded_y, mob.z),
        "grounded_y": grounded_y,
        "target": [None],
        "walk_speed": walk_speed,
        "walk_radius": walk_radius,
        "reach_distance": 0.35,
        "player_radius": player_radius,
        "animation_time": [0.0],
        "floating": floating,
        "ground_offset": ground_offset,
    }


def get_new_mob_walk_target(mob_state):
    offset_x = random.uniform(-mob_state["walk_radius"], mob_state["walk_radius"])
    offset_z = random.uniform(-mob_state["walk_radius"], mob_state["walk_radius"])
    spawn = mob_state["spawn"]
    return Vec3(spawn.x + offset_x, spawn.y, spawn.z + offset_z)


def update_generic_mob_walk(mob_state):
    mob = mob_state["entity"]
    target = mob_state["target"][0]
    ground_y = mob_state.get("grounded_y", mob_state["spawn"].y)

    if target is None:
        mob_state["target"][0] = get_new_mob_walk_target(mob_state)
        return

    to_target = Vec3(target.x - mob.x, 0, target.z - mob.z)
    distance_to_target = to_target.length()

    if distance_to_target <= mob_state["reach_distance"]:
        mob_state["target"][0] = get_new_mob_walk_target(mob_state)
        return

    direction = to_target.normalized()
    step_distance = mob_state["walk_speed"] * time.dt
    next_position = Vec3(
        mob.x + (direction.x * step_distance),
        ground_y,
        mob.z + (direction.z * step_distance),
    )

    if mob_position_is_blocked(next_position, player_radius=mob_state["player_radius"]):
        x_only_position = Vec3(next_position.x, ground_y, mob.z)
        z_only_position = Vec3(mob.x, ground_y, next_position.z)

        if not mob_position_is_blocked(x_only_position, player_radius=mob_state["player_radius"]):
            mob.x = x_only_position.x
        elif not mob_position_is_blocked(z_only_position, player_radius=mob_state["player_radius"]):
            mob.z = z_only_position.z
        else:
            mob_state["target"][0] = get_new_mob_walk_target(mob_state)
            return
    else:
        mob.position = next_position

    if direction.length() > 0:
        mob.rotation_y = math.degrees(math.atan2(direction.x, direction.z))

    mob_state["animation_time"][0] += time.dt * (2.2 + (step_distance * 5.0))
    mob.rotation_z = math.sin(mob_state["animation_time"][0] * 0.45) * 1.2
    if lift_entity_out_of_blocks(mob):
        mob_state["grounded_y"] = mob.y
        mob_state["spawn"] = Vec3(mob_state["spawn"].x, mob.y, mob_state["spawn"].z)


def update_ambient_mobs():
    for mob_state in ambient_mob_states.values():
        mob = mob_state["entity"]
        if lift_entity_out_of_blocks(mob):
            mob_state["grounded_y"] = mob.y
            mob_state["spawn"] = Vec3(mob_state["spawn"].x, mob.y, mob_state["spawn"].z)
        update_generic_mob_walk(mob_state)


ambient_mobs = [
    create_ambient_mob(
        "cow",
        "mobs/minecraft-cow/source/cow.fbx",
        "mobs/minecraft-cow/textures/cow.png",
        Vec3(10, 0.53, 6),
        0.08,
        0.72,
        7.0,
        rotation_y=180,
        ground_offset=-0.02,
        player_radius=0.9,
    ),
    create_ambient_mob(
        "sheep",
        "mobs/minecraft-sheep/source/sheep.fbx",
        "mobs/minecraft-sheep/textures/sheep.png",
        Vec3(-7, 0.53, 9),
        0.08,
        0.78,
        6.0,
        rotation_y=180,
        ground_offset=-0.02,
        player_radius=0.8,
    ),
    create_ambient_mob(
        "villager",
        "mobs/minecraft-villager/source/villager.fbx",
        "mobs/minecraft-villager/textures/villager_farmer.png",
        Vec3(14, 0.53, -5),
        0.075,
        0.68,
        6.5,
        rotation_y=180,
        ground_offset=0.0,
        player_radius=0.8,
    ),
    create_ambient_mob(
        "iron_golem",
        "mobs/minecraft-iron-golem/source/iron_golem.fbx",
        "mobs/minecraft-iron-golem/textures/iron_golem.png",
        Vec3(18, 0.53, 10),
        0.065,
        0.52,
        5.5,
        rotation_y=180,
        ground_offset=0.18,
        player_radius=1.2,
    ),
    create_ambient_mob(
        "spider",
        "mobs/minecraft-spider/source/spider.fbx",
        "mobs/minecraft-spider/textures/spider.png",
        Vec3(-18, 0.53, 4),
        0.07,
        0.84,
        8.0,
        rotation_y=180,
        ground_offset=-0.03,
        player_radius=0.85,
    ),
]

ambient_mob_states = {
    mob_state["name"]: mob_state for mob_state in ambient_mobs
}


def update_chicken_walking():
    target = chicken_walk_target[0]
    if target is None:
        chicken_walk_target[0] = get_new_chicken_walk_target()
        return

    to_target = Vec3(target.x - chicken.x, 0, target.z - chicken.z)
    distance_to_target = to_target.length()

    if distance_to_target <= chicken_walk_reach_distance:
        chicken_walk_target[0] = get_new_chicken_walk_target()
        return

    direction = to_target.normalized()
    step_distance = chicken_walk_speed * time.dt
    next_position = Vec3(
        chicken.x + (direction.x * step_distance),
        chicken_spawn_position.y,
        chicken.z + (direction.z * step_distance),
    )

    if chicken_position_is_blocked(next_position):
        x_only_position = Vec3(next_position.x, chicken_spawn_position.y, chicken.z)
        z_only_position = Vec3(chicken.x, chicken_spawn_position.y, next_position.z)

        if not chicken_position_is_blocked(x_only_position):
            chicken.x = x_only_position.x
        elif not chicken_position_is_blocked(z_only_position):
            chicken.z = z_only_position.z
        else:
            chicken_walk_target[0] = get_new_chicken_walk_target()
            update_chicken_animation(0.0)
            return
    else:
        chicken.position = next_position

    if direction.length() > 0:
        chicken.rotation_y = math.degrees(math.atan2(direction.x, direction.z))

    update_chicken_animation(step_distance)
    lift_entity_out_of_blocks(chicken)

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
player.base_speed = getattr(player, "speed", 5)
spawn_point = Vec3(player.x, player.y, player.z)
set_global_light_level(1.0)
sync_active_blocks(force=True)

menu = None


def on_menu_toggle(state):
    pass


def is_game_paused():
    return bool(menu and menu.menu_open)


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

    if not can_interact_with_block(target_block):
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
    if not is_game_paused():
        update_ambient_mobs()
        update_chicken_walking()

    is_running = bool(
        held_keys.get("control")
        or held_keys.get("left control")
        or held_keys.get("right control")
    )
    player.speed = player.base_speed * (RUN_SPEED_MULTIPLIER if is_running else WALK_SPEED_MULTIPLIER)

    sun_elapsed_time[0] = (sun_elapsed_time[0] + time.dt) % SUN_CYCLE_SECONDS
    day_progress = sun_elapsed_time[0] / SUN_CYCLE_SECONDS
    sun_angle = math.pi * (0.1 + (day_progress * 0.8))
    sun_direction = Vec3(0, math.sin(sun_angle), -math.cos(sun_angle)).normalized()

    sun_visual.position = player.position + (sun_direction * 300)
    sun_visual.look_at(camera.world_position)
    
    # Update procedural cloud field around player
    player_grid_x = math.floor(player.x / CLOUD_GRID_SIZE)
    player_grid_z = math.floor(player.z / CLOUD_GRID_SIZE)
    clouds_to_update = set()

    for offset_x in range(-CLOUD_VIEW_RADIUS, CLOUD_VIEW_RADIUS + 1):
        for offset_z in range(-CLOUD_VIEW_RADIUS, CLOUD_VIEW_RADIUS + 1):
            grid_x = player_grid_x + offset_x
            grid_z = player_grid_z + offset_z
            key = (grid_x, grid_z)

            noise_a = cloud_noise(grid_x, grid_z, 1)
            noise_b = cloud_noise(grid_x, grid_z, 2)
            noise_c = cloud_noise(grid_x, grid_z, 3)
            noise_d = cloud_noise(grid_x, grid_z, 4)
            noise_e = cloud_noise(grid_x, grid_z, 5)

            if noise_a < CLOUD_SPAWN_THRESHOLD:
                continue

            clouds_to_update.add(key)

            cloud_x = (grid_x + 0.5 + ((noise_a - 0.5) * 0.8)) * CLOUD_GRID_SIZE
            cloud_z = (grid_z + 0.5 + ((noise_b - 0.5) * 0.8)) * CLOUD_GRID_SIZE
            cloud_y = CLOUD_MIN_HEIGHT + (noise_c * (CLOUD_MAX_HEIGHT - CLOUD_MIN_HEIGHT))
            cloud_scale = CLOUD_MIN_SCALE + (noise_d * (CLOUD_MAX_SCALE - CLOUD_MIN_SCALE))

            camera_position = camera.world_position
            dx = cloud_x - camera_position.x
            dy = cloud_y - camera_position.y
            dz = cloud_z - camera_position.z
            distance_from_camera = math.sqrt((dx * dx) + (dy * dy) + (dz * dz))
            fade_factor = max(0.0, 1.0 - (distance_from_camera / CLOUD_FADE_RADIUS))
            fade_factor = fade_factor * fade_factor

            alpha = int((CLOUD_MIN_ALPHA + (noise_e * (CLOUD_MAX_ALPHA - CLOUD_MIN_ALPHA))) * fade_factor)

            if key not in active_clouds:
                cloud = get_or_create_cloud()
                active_clouds[key] = cloud
            else:
                cloud = active_clouds[key]

            cloud.position = Vec3(cloud_x, cloud_y, cloud_z)
            cloud.scale = 1

            cloud_width = cloud_scale * 0.95
            cloud_depth = cloud_scale * 0.42
            cloud_height = 70

            puff_offsets = [
                Vec3(-cloud_width * 0.22, 0.08, 0),
                Vec3(cloud_width * 0.16, -0.04, 0),
                Vec3(0, cloud_height * 0.10, 0),
                Vec3(cloud_width * 0.28, 0.02, 0),
            ]

            puff_scales = [
                (cloud_width * 0.78, cloud_depth * 0.55),
                (cloud_width * 0.62, cloud_depth * 0.48),
                (cloud_width * 0.86, cloud_depth * 0.60),
                (cloud_width * 0.50, cloud_depth * 0.42),
            ]

            puff_alphas = [
                int(alpha * 0.96),
                int(alpha * 0.84),
                int(alpha * 1.00),
                int(alpha * 0.74),
            ]

            for puff, puff_offset, puff_scale, puff_alpha in zip(
                cloud.cloud_puffs,
                puff_offsets,
                puff_scales,
                puff_alphas,
            ):
                puff.position = puff_offset
                puff.scale = puff_scale
                puff.color = color.rgba(255, 255, 255, max(0, puff_alpha))

    # Remove clouds that are out of range
    clouds_to_remove = [key for key in active_clouds if key not in clouds_to_update]
    for key in clouds_to_remove:
        return_cloud_to_pool(active_clouds[key])
        del active_clouds[key]

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
