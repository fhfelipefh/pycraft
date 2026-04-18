from pathlib import Path
import math
import random
import atexit
from concurrent.futures import ThreadPoolExecutor

from ursina import (
    Audio,
    Button,
    Entity,
    Sky,
    Text,
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
from voxel_accel import get_filtered_custom_positions, get_flat_ground_positions
from terrain_async_scheduler import DesiredPositionsScheduler
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
MENU_CLICK_SOUND_PATH = Path("sounds/Click_stereo.ogg.mp3").as_posix()
BGM_CANDIDATES = [
    Path("sounds/Below_and_Above.ogg").as_posix(),
    Path("sounds/Fireflies.ogg").as_posix(),
]
GROUND_Y = 0
RENDER_RADIUS = 30
RENDER_HEIGHT = 12
CUSTOM_RENDER_RADIUS = 88
CUSTOM_RENDER_HEIGHT = 24
PRIORITY_GROUND_RADIUS = 3
SUN_CYCLE_SECONDS = 20 * 60
CLOUD_CYCLE_SECONDS = 9 * 60
BLOCK_INTERACTION_RANGE = 20
WALK_SPEED_MULTIPLIER = 1.0
RUN_SPEED_MULTIPLIER = 1.5
HOTBAR_SLOT_COUNT = 9


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


def resolve_model_sidecar_texture(model_path):
    model_rel = Path(model_path)
    parent = model_rel.parent
    stem = model_rel.stem
    candidates = []

    for ext in ("png", "jpg", "jpeg", "tga", "bmp"):
        candidates.append((parent / f"{stem}.{ext}").as_posix())
        candidates.append((parent / f"{stem}_albedo.{ext}").as_posix())
        candidates.append((parent / f"{stem}_diffuse.{ext}").as_posix())
        candidates.append((parent / f"{stem}_baseColor.{ext}").as_posix())

    return resolve_existing_asset_path(candidates)


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


def play_menu_click_sound():
    if resolve_asset_path(MENU_CLICK_SOUND_PATH).exists():
        Audio(MENU_CLICK_SOUND_PATH, autoplay=True, volume=0.35)


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
    {
        "name": "Bloco Verde",
        "block_texture": "grass.png",
        "icon_texture": "grass.png",
        "material": "grass",
    },
]


def _infer_material_from_texture_name(texture_name):
    name = texture_name.lower()
    if any(token in name for token in ("wood", "plank", "log", "acacia", "birch", "spruce")):
        return "wood"
    if any(token in name for token in ("grass", "dirt", "leaf", "leaves", "moss")):
        return "grass"
    return "stone"


def extend_block_types_from_textures():
    textures_dir = resolve_asset_path(TEXTURE_PATH)
    if not textures_dir.exists():
        return

    known_textures = {block_type["block_texture"] for block_type in BLOCK_TYPES}
    for texture_file in sorted(textures_dir.glob("*.png")):
        texture_name = texture_file.name
        if texture_name in known_textures:
            continue
        if texture_name.endswith("_opacity.png"):
            continue

        BLOCK_TYPES.append(
            {
                "name": texture_file.stem.replace("_", " "),
                "block_texture": texture_name,
                "icon_texture": texture_name,
                "material": _infer_material_from_texture_name(texture_name),
            }
        )


extend_block_types_from_textures()

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

hotbar_block_indices = list(range(min(HOTBAR_SLOT_COUNT, len(BLOCK_TYPES))))
while len(hotbar_block_indices) < HOTBAR_SLOT_COUNT:
    hotbar_block_indices.append(0)

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
fps_overlay_visible = [False]
fps_timer = [0.0]
fps_frames = [0]

active_blocks = {}
custom_blocks = {}
removed_blocks = set()

desired_positions_executor = ThreadPoolExecutor(max_workers=2)
desired_positions_scheduler = [None]


def _shutdown_desired_positions_executor():
    try:
        desired_positions_executor.shutdown(wait=False, cancel_futures=True)
    except Exception:
        pass


atexit.register(_shutdown_desired_positions_executor)


def toggle_fullscreen():
    window.fullscreen = not window.fullscreen
    fullscreen_state[0] = window.fullscreen


def get_block_texture(block_type):
    return block_type["block_texture_path"]


def get_block_icon_texture(block_type):
    return block_type["icon_texture_path"]


def get_selected_block_type():
    return BLOCK_TYPES[hotbar_block_indices[selected_block_index]]


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

    for position in get_flat_ground_positions(px, pz, RENDER_RADIUS, GROUND_Y):
        desired.add(position)

    filtered_custom_positions = get_filtered_custom_positions(
        custom_blocks.keys(),
        px,
        py,
        pz,
        CUSTOM_RENDER_RADIUS,
        CUSTOM_RENDER_HEIGHT,
    )

    for position in filtered_custom_positions:
        desired.add(position)

        for dx in range(-PRIORITY_GROUND_RADIUS, PRIORITY_GROUND_RADIUS + 1):
            for dz in range(-PRIORITY_GROUND_RADIUS, PRIORITY_GROUND_RADIUS + 1):
                ground_position = (position[0] + dx, GROUND_Y, position[2] + dz)
                if ground_position not in removed_blocks:
                    desired.add(ground_position)

    return desired


def get_desired_positions_from_snapshots(render_cell, custom_positions, removed_positions):
    if render_cell is None:
        return set()

    px, py, pz = render_cell
    desired = set()

    for position in get_flat_ground_positions(px, pz, RENDER_RADIUS, GROUND_Y):
        desired.add(position)

    filtered_custom_positions = get_filtered_custom_positions(
        custom_positions,
        px,
        py,
        pz,
        CUSTOM_RENDER_RADIUS,
        CUSTOM_RENDER_HEIGHT,
    )

    removed_positions = set(removed_positions)
    for position in filtered_custom_positions:
        desired.add(position)

        for dx in range(-PRIORITY_GROUND_RADIUS, PRIORITY_GROUND_RADIUS + 1):
            for dz in range(-PRIORITY_GROUND_RADIUS, PRIORITY_GROUND_RADIUS + 1):
                ground_position = (position[0] + dx, GROUND_Y, position[2] + dz)
                if ground_position not in removed_positions:
                    desired.add(ground_position)

    return desired


desired_positions_scheduler[0] = DesiredPositionsScheduler(
    desired_positions_executor,
    get_desired_positions_from_snapshots,
)


def sync_active_blocks(force=False):
    render_cell = to_grid_position(player.position)
    if not force and render_cell == last_render_cell[0]:
        return

    if force:
        desired_positions = get_desired_positions(render_cell)
    else:
        desired_positions_scheduler[0].request(
            render_cell,
            tuple(custom_blocks.keys()),
            tuple(removed_blocks),
        )
        desired_positions = desired_positions_scheduler[0].consume(render_cell)
        if desired_positions is None:
            return

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

    # Evita varrer todos os blocos ativos por frame: verifica apenas células vizinhas.
    min_x = math.floor(position.x - 0.48)
    max_x = math.ceil(position.x + 0.48)
    min_z = math.floor(position.z - 0.48)
    max_z = math.ceil(position.z + 0.48)
    min_y = math.floor(position.y - 1.2)
    max_y = math.ceil(position.y + 1.2)

    for bx in range(min_x, max_x + 1):
        for bz in range(min_z, max_z + 1):
            if abs(bx - position.x) >= 0.48 or abs(bz - position.z) >= 0.48:
                continue

            for by in range(min_y, max_y + 1):
                # Chão base não deve bloquear o deslocamento horizontal do mob.
                if by <= GROUND_Y:
                    continue

                if get_block_type_at((bx, by, bz)) is not None:
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


def create_ambient_mob(name, model_path, texture_path, position, scale, walk_speed, walk_radius, rotation_y=180, tint=color.white, player_radius=0.75, ground_offset=0.0, floating=False, use_opacity_map=True, animations=None, unlit=True):
    spawn_position = Vec3(position.x, position.y + ground_offset, position.z)
    model_resolved = resolve_existing_asset_or_fallback([model_path])
    texture_candidate = texture_path or resolve_model_sidecar_texture(model_resolved)
    tex_obj = load_texture_or_fallback(texture_candidate, use_opacity_map=use_opacity_map) if texture_candidate else None
    mob = Entity(
        parent=scene,
        model=model_resolved,
        texture=tex_obj,
        position=spawn_position,
        scale=scale,
        rotation_y=rotation_y,
        unlit=unlit,
        color=tint,
    )
    if tex_obj is not None:
        apply_texture_recursively(mob, tex_obj)
    mob.setTwoSided(True)
    mob.collider = "box"
    grounded_y = mob.y
    if not floating:
        # Garante que o mob não nasça enterrado no terreno/blocos.
        if lift_entity_out_of_blocks(mob):
            grounded_y = mob.y

    resolved_animations = {}
    if animations:
        for key, anim_path in animations.items():
            resolved_animations[key] = resolve_existing_asset_or_fallback([anim_path], fallback_texture=model_resolved)

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
        "animations": resolved_animations,
        "current_animation": ["__spawn__"],
        "texture_obj": tex_obj,
    }


def set_mob_animation(mob_state, animation_key):
    animations = mob_state.get("animations") or {}
    model_path = animations.get(animation_key)
    if not model_path:
        return

    if mob_state["current_animation"][0] == animation_key:
        return

    mob = mob_state["entity"]
    try:
        mob.model = model_path
    except Exception:
        # Mantém o modelo atual quando a animação/modelo não é compatível.
        return
    tex_obj = mob_state.get("texture_obj")
    if tex_obj is not None:
        apply_texture_recursively(mob, tex_obj)
    mob_state["current_animation"][0] = animation_key


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
        set_mob_animation(mob_state, "idle")
        mob.rotation_z = math.sin((sun_elapsed_time[0] * 1.8) + (mob_state["spawn"].x * 0.3)) * 0.7
        mob_state["target"][0] = get_new_mob_walk_target(mob_state)
        return

    to_target = Vec3(target.x - mob.x, 0, target.z - mob.z)
    distance_to_target = to_target.length()

    if distance_to_target <= mob_state["reach_distance"]:
        set_mob_animation(mob_state, "idle")
        mob.rotation_z = math.sin((sun_elapsed_time[0] * 1.8) + (mob_state["spawn"].x * 0.3)) * 0.7
        mob_state["target"][0] = get_new_mob_walk_target(mob_state)
        return

    direction = to_target.normalized()
    set_mob_animation(mob_state, "walk")
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
if hasattr(player, "cursor") and player.cursor is not None:
    player.cursor.enabled = False
player.base_speed = getattr(player, "speed", 5)
spawn_point = Vec3(player.x, player.y, player.z)
set_global_light_level(1.0)
sync_active_blocks(force=True)

menu = None
crosshair = None
background_music = None
music_enabled = [True]
music_volume = [0.25]
fps_overlay = None
fps_overlay_text = None
inventory_open = [False]
inventory_panel = [None]
inventory_backdrop = [None]
inventory_card = [None]
inventory_slots = []
inventory_slot_frames = []
inventory_slot_buttons = []
inventory_group_buttons = []
inventory_filtered_indices = [[]]
inventory_search_query = [""]
inventory_selected_group = ["all"]
inventory_page = [0]
inventory_search_text = [None]
inventory_page_text = [None]
inventory_group_label = [None]
inventory_hotbar_bg = [None]
inventory_hotbar_selector = [None]
inventory_hotbar_icons = []

INVENTORY_COLUMNS = 8
INVENTORY_ROWS = 3
INVENTORY_PAGE_SIZE = INVENTORY_COLUMNS * INVENTORY_ROWS


def on_menu_toggle(state):
    if state and inventory_open[0]:
        set_inventory_open(False)
    if crosshair is not None:
        crosshair.enabled = not state and not inventory_open[0]
    if fps_overlay is not None:
        fps_overlay.enabled = fps_overlay_visible[0] and not state
    if fps_overlay_text is not None:
        fps_overlay_text.enabled = fps_overlay_visible[0] and not state
    if state:
        play_menu_click_sound()


def toggle_music_enabled():
    music_enabled[0] = not music_enabled[0]
    if background_music is not None:
        background_music.volume = music_volume[0] if music_enabled[0] else 0.0


def get_music_enabled():
    return music_enabled[0]


def get_music_volume():
    return music_volume[0]


def set_music_volume_delta(delta):
    music_volume[0] = max(0.0, min(1.0, music_volume[0] + delta))
    if background_music is not None:
        background_music.volume = music_volume[0] if music_enabled[0] else 0.0


def is_game_paused():
    return bool(menu and menu.menu_open)


menu = GameMenu(
    player,
    on_menu_toggle,
    toggle_fullscreen,
    toggle_music_enabled,
    get_music_enabled,
    get_music_volume,
    set_music_volume_delta,
)

crosshair = Entity(
    parent=camera.ui,
    model="quad",
    texture=resolve_existing_asset_path([f"{UI_PATH}/Crosshair.png"]) or "white_cube",
    position=(0, 0),
    scale=(0.022, 0.022),
    z=-0.5,
)

available_bgm_files = get_existing_sound_files(BGM_CANDIDATES)
if available_bgm_files:
    background_music = Audio(
        random.choice(available_bgm_files),
        autoplay=True,
        loop=True,
        volume=music_volume[0],
    )

fps_overlay = Entity(
    parent=camera.ui,
    model="quad",
    color=color.rgba(0, 0, 0, 120),
    position=(0.43, 0.46, 0.7),
    scale=(0.14, 0.06),
    enabled=False,
)
fps_overlay_text = Text(
    parent=camera.ui,
    text="FPS: --",
    color=color.white,
    position=(0.43, 0.46, 0.6),
    origin=(0, 0),
    scale=0.9,
    enabled=False,
)

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
hud_heart_icons = []
hud_armor_icons = []


def create_hotbar_ui():
    slot_spacing = hotbar_bg.scale_x * (40 / 364)
    start_x = hotbar_bg.x - (hotbar_bg.scale_x / 2) + (hotbar_bg.scale_x * (21.5 / 364))
    icon_scale = (slot_spacing * 0.78, hotbar_bg.scale_y * 0.72)
    icon_y = hotbar_bg.y + (hotbar_bg.scale_y * 0.015)

    for index in range(HOTBAR_SLOT_COUNT):
        slot_x = start_x + (index * slot_spacing)
        hotbar_slot_positions.append(slot_x)
        hotbar_icons.append(
            Entity(
                parent=camera.ui,
                model="quad",
                texture=get_block_icon_texture(BLOCK_TYPES[hotbar_block_indices[index]]),
                position=(slot_x, icon_y, 0.8),
                scale=icon_scale,
            )
        )


def refresh_hotbar_icons():
    for slot_index, icon_entity in enumerate(hotbar_icons):
        block_index = hotbar_block_indices[slot_index]
        icon_entity.texture = get_block_icon_texture(BLOCK_TYPES[block_index])


def update_hotbar_ui():
    hotbar_selector.x = hotbar_slot_positions[selected_block_index]
    refresh_hotbar_icons()
    refresh_inventory_hotbar_preview()


def assign_inventory_block_to_selected_slot(block_index):
    hotbar_block_indices[selected_block_index] = block_index
    update_hotbar_ui()
    refresh_inventory_grid()


def get_inventory_group_for_block(block_type):
    texture_name = block_type.get("block_texture", "").lower()
    material = block_type.get("material", "")

    if any(token in texture_name for token in ("ore", "diamond", "emerald", "iron", "gold", "copper", "lapis", "redstone", "deepslate")):
        return "minerios"
    if any(token in texture_name for token in ("wood", "plank", "log", "acacia", "spruce", "birch", "mangrove", "bamboo")):
        return "madeira"
    if any(token in texture_name for token in ("grass", "dirt", "leaf", "leaves", "moss", "mud")) or material == "grass":
        return "natureza"
    if any(token in texture_name for token in ("terracotta", "glazed", "brick", "polished", "chiseled", "wool", "glass")):
        return "decoracao"
    return "pedra"


def refresh_inventory_hotbar_preview():
    if inventory_hotbar_bg[0] is None or inventory_hotbar_selector[0] is None:
        return

    slot_spacing = inventory_hotbar_bg[0].scale_x * (40 / 364)
    selector_start_x = -(inventory_hotbar_bg[0].scale_x / 2) + (inventory_hotbar_bg[0].scale_x * (21.5 / 364))
    inventory_hotbar_selector[0].x = selector_start_x + (selected_block_index * slot_spacing)

    for slot_index, icon in enumerate(inventory_hotbar_icons):
        block_index = hotbar_block_indices[slot_index]
        icon.texture = get_block_icon_texture(BLOCK_TYPES[block_index])


def refresh_inventory_grid():
    if not inventory_slot_buttons:
        return

    query = inventory_search_query[0].strip().lower()
    selected_group = inventory_selected_group[0]

    filtered = []
    for idx, block_type in enumerate(BLOCK_TYPES):
        block_group = get_inventory_group_for_block(block_type)
        if selected_group != "all" and block_group != selected_group:
            continue

        candidate_text = f"{block_type.get('name', '')} {block_type.get('block_texture', '')}".lower()
        if query and query not in candidate_text:
            continue
        filtered.append(idx)

    inventory_filtered_indices[0] = filtered
    total_pages = max(1, math.ceil(len(filtered) / INVENTORY_PAGE_SIZE))
    inventory_page[0] = max(0, min(inventory_page[0], total_pages - 1))

    start = inventory_page[0] * INVENTORY_PAGE_SIZE
    end = start + INVENTORY_PAGE_SIZE
    page_items = filtered[start:end]

    for slot_idx, button in enumerate(inventory_slot_buttons):
        frame = inventory_slot_frames[slot_idx]
        if slot_idx < len(page_items):
            block_index = page_items[slot_idx]
            block_type = BLOCK_TYPES[block_index]
            frame.enabled = True
            button.enabled = True
            button.visible = True
            button.texture = get_block_icon_texture(block_type)
            button.on_click = (lambda idx=block_index: assign_inventory_block_to_selected_slot(idx))
            if block_index == hotbar_block_indices[selected_block_index]:
                frame.texture = resolve_existing_asset_path([f"{UI_PATH}/GUI_slot_highlight_back.png", f"{UI_PATH}/GUI_slot.png"]) or "white_cube"
            else:
                frame.texture = resolve_existing_asset_path([f"{UI_PATH}/GUI_slot.png"]) or "white_cube"
        else:
            frame.enabled = True
            frame.texture = resolve_existing_asset_path([f"{UI_PATH}/Disabled_slot.png", f"{UI_PATH}/GUI_slot.png"]) or "white_cube"
            button.enabled = False
            button.visible = False

    if inventory_search_text[0] is not None:
        inventory_search_text[0].text = "Buscar"


def set_inventory_group(group_key):
    inventory_selected_group[0] = group_key
    inventory_page[0] = 0
    refresh_inventory_grid()


def next_inventory_page(delta):
    filtered_count = len(inventory_filtered_indices[0])
    total_pages = max(1, math.ceil(filtered_count / INVENTORY_PAGE_SIZE))
    inventory_page[0] = (inventory_page[0] + delta) % total_pages
    refresh_inventory_grid()


def create_inventory_ui():
    inventory_backdrop[0] = Entity(
        parent=camera.ui,
        model="quad",
        color=color.rgba(9, 13, 20, 105),
        scale=(2.0, 2.0),
        z=0.45,
        enabled=False,
    )

    inventory_panel[0] = Entity(
        parent=camera.ui,
        model="quad",
        color=color.rgba(0, 0, 0, 0),
        scale=(1.0, 1.0),
        z=0.44,
        enabled=False,
    )

    inventory_card[0] = Entity(
        parent=inventory_panel[0],
        model="quad",
        texture=resolve_existing_asset_path([f"{UI_PATH}/inventory.png", f"{UI_PATH}/Inworld_menu_list_background.png"]) or "white_cube",
        color=color.rgba(255, 255, 255, 255),
        scale=(0.86, 0.66),
        z=0,
    )

    inventory_search_text[0] = Text(
        parent=inventory_card[0],
        text="Buscar",
        position=(-0.37, 0.21, 0),
        scale=1.15,
        color=color.rgb(50, 50, 50),
    )

    Entity(
        parent=inventory_card[0],
        model="quad",
        texture=resolve_existing_asset_path([f"{UI_PATH}/Text_field.png"]) or "white_cube",
        color=color.rgba(255, 255, 255, 255),
        scale=(0.52, 0.062),
        position=(-0.01, 0.215, 0),
    )

    group_options = [
        ("all", 0),
        ("natureza", 1),
        ("madeira", 2),
        ("pedra", 3),
        ("minerios", 4),
        ("decoracao", 5),
    ]
    tab_textures = {
        "all": resolve_existing_asset_path([f"{UI_PATH}/Creative_tab_items_gui.png", f"{UI_PATH}/GUI_slot.png"]) or "white_cube",
        "natureza": get_block_icon_texture(BLOCK_TYPES[0]),
        "madeira": get_block_icon_texture(BLOCK_TYPES[1 if len(BLOCK_TYPES) > 1 else 0]),
        "pedra": get_block_icon_texture(BLOCK_TYPES[2 if len(BLOCK_TYPES) > 2 else 0]),
        "minerios": get_block_icon_texture(BLOCK_TYPES[min(3, len(BLOCK_TYPES) - 1)]),
        "decoracao": get_block_icon_texture(BLOCK_TYPES[min(4, len(BLOCK_TYPES) - 1)]),
    }
    for group_key, idx in group_options:
        group_button = Button(
            parent=inventory_card[0],
            model="quad",
            texture=resolve_existing_asset_path([f"{UI_PATH}/GUI_slot.png"]) or "white_cube",
            color=color.rgba(255, 255, 255, 255),
            text="",
            scale=(0.072, 0.072),
            position=(-0.34 + (idx * 0.11), 0.13, 0),
            highlight_color=color.rgba(248, 248, 248, 255),
            pressed_color=color.rgba(224, 224, 224, 255),
        )
        Entity(
            parent=group_button,
            model="quad",
            texture=tab_textures[group_key],
            color=color.white,
            scale=(0.78, 0.78),
            position=(0, 0, -0.01),
        )
        group_button.on_click = (lambda g=group_key: set_inventory_group(g))
        inventory_group_buttons.append(group_button)

    prev_button = Button(
        parent=inventory_card[0],
        model="quad",
        texture=resolve_existing_asset_path([f"{UI_PATH}/Sort_down.png", f"{UI_PATH}/GUI_slot.png"]) or "white_cube",
        color=color.rgba(255, 255, 255, 255),
        text="",
        scale=(0.07, 0.07),
        position=(0.30, -0.27, 0),
    )
    prev_button.on_click = lambda: next_inventory_page(-1)

    next_button = Button(
        parent=inventory_card[0],
        model="quad",
        texture=resolve_existing_asset_path([f"{UI_PATH}/Sort_up.png", f"{UI_PATH}/GUI_slot.png"]) or "white_cube",
        color=color.rgba(255, 255, 255, 255),
        text="",
        scale=(0.07, 0.07),
        position=(0.39, -0.27, 0),
    )
    next_button.on_click = lambda: next_inventory_page(1)

    inventory_hotbar_bg[0] = Entity(
        parent=inventory_card[0],
        model="quad",
        texture=resolve_existing_asset_path([f"{UI_PATH}/Hotbar.png"]) or "white_cube",
        position=(0.00, -0.28, 0),
        scale=(0.54, 0.070),
    )
    inventory_hotbar_selector[0] = Entity(
        parent=inventory_hotbar_bg[0],
        model="quad",
        texture=resolve_existing_asset_path([f"{UI_PATH}/Hotbar_selector.png"]) or "white_cube",
        position=(0, 0, -0.01),
        scale=(0.066, 0.078),
    )

    preview_slot_spacing = inventory_hotbar_bg[0].scale_x * (40 / 364)
    preview_start_x = -(inventory_hotbar_bg[0].scale_x / 2) + (inventory_hotbar_bg[0].scale_x * (21.5 / 364))
    preview_icon_scale = (preview_slot_spacing * 0.76, inventory_hotbar_bg[0].scale_y * 0.72)
    for slot_idx in range(HOTBAR_SLOT_COUNT):
        inventory_hotbar_icons.append(
            Entity(
                parent=inventory_hotbar_bg[0],
                model="quad",
                texture=get_block_icon_texture(BLOCK_TYPES[hotbar_block_indices[slot_idx]]),
                position=(preview_start_x + (slot_idx * preview_slot_spacing), 0.001, -0.02),
                scale=preview_icon_scale,
                color=color.white,
            )
        )

    slot_spacing_x = 0.095
    slot_spacing_y = 0.107
    grid_start_x = -0.335
    grid_start_y = 0.04
    for slot_idx in range(INVENTORY_PAGE_SIZE):
        col = slot_idx % INVENTORY_COLUMNS
        row = slot_idx // INVENTORY_COLUMNS
        position = (grid_start_x + (col * slot_spacing_x), grid_start_y - (row * slot_spacing_y), 0)

        slot_frame = Entity(
            parent=inventory_card[0],
            model="quad",
            texture=resolve_existing_asset_path([f"{UI_PATH}/GUI_slot.png"]) or "white_cube",
            color=color.white,
            scale=(0.084, 0.084),
            position=position,
        )

        slot_button = Button(
            parent=slot_frame,
            model="quad",
            texture="white_cube",
            color=color.white,
            scale=(0.76, 0.76),
            position=(0, 0, -0.01),
            text="",
            highlight_color=color.rgba(255, 255, 255, 28),
            pressed_color=color.rgba(255, 255, 255, 70),
        )

        inventory_slot_frames.append(slot_frame)
        inventory_slot_buttons.append(slot_button)
        inventory_slots.append(slot_button)

    refresh_inventory_hotbar_preview()
    refresh_inventory_grid()


def set_inventory_open(state):
    inventory_open[0] = bool(state)
    if inventory_backdrop[0] is not None:
        inventory_backdrop[0].enabled = inventory_open[0]
    if inventory_panel[0] is not None:
        inventory_panel[0].enabled = inventory_open[0]

    if inventory_open[0]:
        player.enabled = False
        mouse.locked = False
        if crosshair is not None:
            crosshair.enabled = False
    else:
        should_enable_player = not is_game_paused()
        player.enabled = should_enable_player
        mouse.locked = should_enable_player
        if crosshair is not None:
            crosshair.enabled = should_enable_player
        return

    # Sempre que abrir, atualiza conteúdo visual com filtros atuais.
    refresh_inventory_hotbar_preview()
    refresh_inventory_grid()


def create_status_hud():
    heart_full = resolve_existing_asset_path([f"{UI_PATH}/Heart_(texture)_JE1_BE1.png"]) or "white_cube"
    armor_full = resolve_existing_asset_path([f"{UI_PATH}/Armor_full.png"]) or "white_cube"
    armor_empty = resolve_existing_asset_path([f"{UI_PATH}/Armor_empty.png"]) or "white_cube"

    # Usa ícones individuais com proporção quadrada para evitar aparência achatada.
    icon_scale = (0.026, 0.026)
    spacing = 0.030
    hotbar_left = hotbar_bg.x - (hotbar_bg.scale_x / 2)
    hotbar_top = hotbar_bg.y + (hotbar_bg.scale_y / 2)
    start_x = hotbar_left + (icon_scale[0] * 0.5)

    # Armadura em cima e corações abaixo, ambos acima da hotbar com margem pequena.
    y_hearts = hotbar_top + 0.008 + (icon_scale[1] * 0.5)
    y_armor = y_hearts + (icon_scale[1] * 1.15)

    for i in range(10):
        hud_heart_icons.append(
            Entity(
                parent=camera.ui,
                model="quad",
                texture=heart_full,
                position=(start_x + (i * spacing), y_hearts, 0.8),
                scale=icon_scale,
                color=color.white,
            )
        )

    for i in range(10):
        hud_armor_icons.append(
            Entity(
                parent=camera.ui,
                model="quad",
                texture=armor_full if i < 8 else armor_empty,
                position=(start_x + (i * spacing), y_armor, 0.8),
                scale=icon_scale,
                color=color.white,
            )
        )


create_hotbar_ui()
update_hotbar_ui()
create_status_hud()
create_inventory_ui()

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

    if key == "f3":
        fps_overlay_visible[0] = not fps_overlay_visible[0]
        if fps_overlay is not None:
            fps_overlay.enabled = fps_overlay_visible[0] and not is_game_paused()
        if fps_overlay_text is not None:
            fps_overlay_text.enabled = fps_overlay_visible[0] and not is_game_paused()
        return

    if key == "escape":
        if inventory_open[0]:
            set_inventory_open(False)
            return
        if menu:
            menu.toggle_menu(not menu.menu_open)
        return

    if key == "e":
        if menu and menu.menu_open:
            return
        set_inventory_open(not inventory_open[0])
        return

    if not menu or menu.menu_open:
        return

    if key.isdigit():
        idx = int(key) - 1
        if 0 <= idx < HOTBAR_SLOT_COUNT:
            selected_block_index = idx
            update_hotbar_ui()
            return

    if inventory_open[0]:
        if key == "left arrow":
            next_inventory_page(-1)
            return
        if key == "right arrow":
            next_inventory_page(1)
            return
        if key == "backspace":
            inventory_search_query[0] = inventory_search_query[0][:-1]
            inventory_page[0] = 0
            refresh_inventory_grid()
            return
        if key == "space":
            inventory_search_query[0] += " "
            inventory_page[0] = 0
            refresh_inventory_grid()
            return
        if len(key) == 1 and (key.isalnum() or key in ("_", "-")):
            inventory_search_query[0] += key.lower()
            inventory_page[0] = 0
            refresh_inventory_grid()
            return
        return

    if key == "scroll up":
        selected_block_index = (selected_block_index + 1) % HOTBAR_SLOT_COUNT
        update_hotbar_ui()
        return

    if key == "scroll down":
        selected_block_index = (selected_block_index - 1) % HOTBAR_SLOT_COUNT
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

    was_grounded[0] = current_grounded

    if (
        fps_overlay_visible[0]
        and fps_overlay is not None
        and fps_overlay.enabled
        and fps_overlay_text is not None
        and fps_overlay_text.enabled
    ):
        fps_frames[0] += 1
        fps_timer[0] += time.dt
        if fps_timer[0] >= 0.25:
            fps_value = int(round(fps_frames[0] / max(fps_timer[0], 1e-6)))
            fps_overlay_text.text = f"FPS: {fps_value}"
            fps_timer[0] = 0.0
            fps_frames[0] = 0


app.run()
