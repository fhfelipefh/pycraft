from pathlib import Path
import math
import random
import atexit
from concurrent.futures import ThreadPoolExecutor

from panda3d.core import WindowProperties, loadPrcFileData
from ursina import (
    Audio,
    Button,
    Entity,
    Mesh,
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
from pycraft.mob_textures import apply_texture_recursively
from pycraft.mob_grounding import compute_grounded_entity_y
from pycraft.voxel_accel import get_filtered_custom_positions
from pycraft.voxel_chunk import (
    BlockHit,
    CHUNK_SIZE,
    build_chunk_mesh,
    build_texture_atlas,
    chunk_key_from_block,
    chunk_key_from_world,
    get_top_block_in_column,
    iter_chunk_block_positions,
    reverse_triangle_winding,
)
from pycraft.terrain_async_scheduler import DesiredPositionsScheduler
from ursina.prefabs.first_person_controller import FirstPersonController

from pycraft.menu import GameMenu

# Keep the main window fully opaque to avoid compositor alpha artifacts
# that can appear as a solid white frame on some Linux setups.
loadPrcFileData("", "framebuffer-alpha #f")
loadPrcFileData("", "alpha-bits 0")
loadPrcFileData("", "framebuffer-alpha 0")
loadPrcFileData("", "framebuffer-srgb 0")
loadPrcFileData("", "background-color 0.06 0.09 0.14 1")

app = Ursina(development_mode=False, editor_ui_enabled=False, fullscreen=False, borderless=False, title="pycraft")


BASE_DIR = Path(__file__).resolve().parent
application.asset_folder = BASE_DIR
window.fullscreen = False
window.color = color.rgb(16, 24, 36)
camera.background_color = color.rgb(16, 24, 36)
try:
    app.win.setClearColor((16 / 255, 24 / 255, 36 / 255, 1.0))
    app.win.setClearColorActive(True)
except Exception:
    pass

for ui_name in ("exit_button", "cog_button", "fps_counter", "entity_counter", "collider_counter"):
    ui_element = getattr(window, ui_name, None)
    if ui_element is not None:
        ui_element.enabled = False

for ui_name in ("cog_menu", "editor_ui"):
    ui_element = getattr(window, ui_name, None)
    if ui_element is not None:
        ui_element.enabled = False


def cleanup_problematic_ui_quads(destroy_matches=False):
    for child in camera.ui.children:
        if not getattr(child, "enabled", False):
            continue
        model_name = str(getattr(child, "model", ""))
        if "quad" not in model_name:
            continue
        scale_x = float(getattr(child, "scale_x", 0) or 0)
        scale_y = float(getattr(child, "scale_y", 0) or 0)
        if scale_x < 20 or scale_y < 20:
            continue

        alpha = 255
        color_value = getattr(child, "color", None)
        try:
            raw_alpha = float(color_value[3])
            alpha = int(raw_alpha * 255) if raw_alpha <= 1 else int(raw_alpha)
        except Exception:
            alpha = 255

        if alpha <= 1:
            if destroy_matches:
                destroy(child)
            else:
                child.enabled = False


cleanup_problematic_ui_quads(destroy_matches=True)

TEXTURE_PATH = Path("textures/blocks").as_posix()
UI_PATH = Path("ui").as_posix()
SKY_PATH = Path("skybox/generated").as_posix()
DAMAGE_SOUND_PATH = Path("sounds/damage.wav").as_posix()
WALK_SOUND_PATH = Path("sounds/walk-sound.wav").as_posix()
MENU_CLICK_SOUND_PATH = Path("sounds/Click_stereo.ogg.mp3").as_posix()
MUSIC_DIR = Path("musics").as_posix()
MUSIC_EXTENSIONS = {".mp3", ".ogg", ".wav", ".flac"}
GROUND_Y = 0
RENDER_RADIUS = 30
RENDER_HEIGHT = 12
CUSTOM_RENDER_RADIUS = 88
CUSTOM_RENDER_HEIGHT = 24
RENDER_UNLOAD_PADDING = 1
PRIORITY_GROUND_RADIUS = 3
SUN_CYCLE_SECONDS = 20 * 60
CLOUD_CYCLE_SECONDS = 9 * 60
BLOCK_INTERACTION_RANGE = 20
GROUND_RENDER_CHUNK_RADIUS = max(1, math.ceil(RENDER_RADIUS / CHUNK_SIZE))
CUSTOM_RENDER_CHUNK_RADIUS = max(1, math.ceil(CUSTOM_RENDER_RADIUS / CHUNK_SIZE))
CUSTOM_RENDER_CHUNK_HEIGHT = max(1, math.ceil(CUSTOM_RENDER_HEIGHT / CHUNK_SIZE))
WALK_SPEED_MULTIPLIER = 1.0
RUN_SPEED_MULTIPLIER = 1.5
HOTBAR_SLOT_COUNT = 9
HOTBAR_TEXTURE_WIDTH = 364
HOTBAR_TEXTURE_HEIGHT = 44
HOTBAR_SELECTOR_TEXTURE_SIZE = 48
HOTBAR_SLOT_SPACING_PX = 40
HOTBAR_FIRST_SLOT_CENTER_PX = 21.5
HOTBAR_BG_SCALE_X = 0.8
HOTBAR_BG_SCALE_Y = HOTBAR_BG_SCALE_X * (HOTBAR_TEXTURE_HEIGHT / HOTBAR_TEXTURE_WIDTH)
HOTBAR_SELECTOR_SCALE = HOTBAR_BG_SCALE_X * (HOTBAR_SELECTOR_TEXTURE_SIZE / HOTBAR_TEXTURE_WIDTH)
MOB_STEP_HEIGHT = 1.15
MOB_FALL_SPEED = 7.5
MOB_RESPAWN_FALL_DISTANCE = 18.0


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


def get_music_playlist_files():
    music_root = resolve_asset_path(MUSIC_DIR)
    if not music_root.exists():
        return []

    return [
        Path(MUSIC_DIR, entry.name).as_posix()
        for entry in sorted(music_root.iterdir(), key=lambda path: path.name.lower())
        if entry.is_file() and entry.suffix.lower() in MUSIC_EXTENSIONS
    ]


def play_menu_click_sound():
    if resolve_asset_path(MENU_CLICK_SOUND_PATH).exists():
        Audio(MENU_CLICK_SOUND_PATH, autoplay=True, volume=0.35)


def approach_value(current, target, max_delta):
    if current < target:
        return min(target, current + max_delta)
    if current > target:
        return max(target, current - max_delta)
    return target


def get_entity_model_min_y(entity):
    try:
        tight_bounds = entity.model.get_tight_bounds()
        if tight_bounds:
            min_point, _ = tight_bounds
            return float(min_point.y)
    except Exception:
        pass
    return -0.5


def get_entity_model_max_y(entity):
    try:
        tight_bounds = entity.model.get_tight_bounds()
        if tight_bounds:
            _, max_point = tight_bounds
            return float(max_point.y)
    except Exception:
        pass
    return 0.5


def get_top_solid_block_at_position(x, z, probe_from_y, footprint=0.5):
    del footprint
    return get_top_block_in_column(
        x=x,
        z=z,
        probe_from_y=probe_from_y,
        get_block_type_at=get_block_type_at,
        ground_y=GROUND_Y,
    )


def get_support_top_y_under_entity(entity, probe_height=6.0, probe_distance=24.0):
    ignore = [entity]
    if highlighted_box[0] is not None:
        ignore.append(highlighted_box[0])

    hit = raycast(
        Vec3(entity.x, entity.y + probe_height, entity.z),
        Vec3(0, -1, 0),
        distance=probe_distance,
        ignore=tuple(ignore),
    )
    if hit.hit and hasattr(hit.entity, "chunk_key"):
        return float(hit.world_point.y)

    support_position = get_top_solid_block_at_position(
        entity.x,
        entity.z,
        entity.y + probe_height,
        footprint=0.5,
    )
    if support_position is None:
        return None
    return float(support_position[1])


def lift_entity_out_of_blocks(entity, footprint=0.5, epsilon=0.01):
    support_top = get_support_top_y_under_entity(entity)
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


def get_support_top_y_at_position(x, z, probe_from_y, ignore_entity=None, footprint=0.5):
    ignore = []
    if ignore_entity is not None:
        ignore.append(ignore_entity)
    if highlighted_box[0] is not None:
        ignore.append(highlighted_box[0])

    hit = raycast(
        Vec3(x, probe_from_y, z),
        Vec3(0, -1, 0),
        distance=max(4.0, probe_from_y - (GROUND_Y - 8.0)),
        ignore=tuple(ignore),
    )
    if hit.hit and hasattr(hit.entity, "chunk_key"):
        return float(hit.world_point.y)

    support_position = get_top_solid_block_at_position(x, z, probe_from_y, footprint=footprint)
    if support_position is None:
        return None
    return float(support_position[1])


def get_grounded_y_for_entity_at(entity, x, z, probe_from_y=None, footprint=0.5, epsilon=0.01):
    probe_y = probe_from_y if probe_from_y is not None else max(entity.y + 6.0, GROUND_Y + 8.0)
    support_top = get_support_top_y_at_position(
        x,
        z,
        probe_y,
        ignore_entity=entity,
        footprint=footprint,
    )
    return compute_grounded_entity_y(
        get_entity_model_min_y(entity),
        getattr(entity, "scale_y", 1.0) or 1.0,
        support_top,
        epsilon=epsilon,
    )

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

BLOCK_ATLAS = build_texture_atlas(
    [block_type["block_texture_path"] for block_type in BLOCK_TYPES],
    BASE_DIR,
)
BLOCK_ATLAS_TEXTURE = load_texture(BLOCK_ATLAS.texture_path)
BLOCK_ATLAS_TEXTURE.filtering = False

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
last_render_chunk = [None]
last_desired_chunks = [set()]
sun_elapsed_time = [0.0]
light_update_timer = [0.0]
current_light_level = [255]
fps_overlay_visible = [False]
fps_timer = [0.0]
fps_frames = [0]

active_chunks = {}
custom_blocks = {}
custom_blocks_by_chunk = {}
removed_blocks = set()
dirty_chunks = set()
chunk_visibility_dirty = [True]

desired_positions_executor = ThreadPoolExecutor(max_workers=2)
desired_positions_scheduler = [None]


def _shutdown_desired_positions_executor():
    try:
        desired_positions_executor.shutdown(wait=False, cancel_futures=True)
    except Exception:
        pass


atexit.register(_shutdown_desired_positions_executor)


def center_game_window():
    if is_window_fullscreen():
        return

    try:
        current_props = app.win.getProperties()
        window_width = current_props.getXSize()
        window_height = current_props.getYSize()
        if window_width <= 0 or window_height <= 0:
            return

        display_width = app.pipe.getDisplayWidth()
        display_height = app.pipe.getDisplayHeight()
        origin_x = max(0, int((display_width - window_width) / 2))
        origin_y = max(0, int((display_height - window_height) / 2))

        props = WindowProperties()
        props.setOrigin(origin_x, origin_y)
        app.win.requestProperties(props)
    except Exception:
        pass


def is_window_fullscreen():
    try:
        return bool(app.win.getProperties().getFullscreen())
    except Exception:
        return bool(window.fullscreen)


def toggle_fullscreen():
    target_state = not is_window_fullscreen()
    window.fullscreen = target_state
    fullscreen_state[0] = target_state
    if not target_state:
        invoke(center_game_window, delay=0.05)


def get_block_texture(block_type):
    return block_type["block_texture_path"]


def get_block_icon_texture(block_type):
    return block_type["icon_texture_path"]


def get_selected_block_type():
    return BLOCK_TYPES[hotbar_block_indices[selected_block_index]]


def to_grid_position(position):
    return tuple(int(round(value)) for value in position)


def get_render_cell(position):
    return (
        math.floor(position.x),
        int(round(position.y)),
        math.floor(position.z),
    )


def get_render_chunk(position):
    return chunk_key_from_world(position)


def world_point_to_block_position(point):
    return (
        math.floor(point.x + 0.5),
        math.ceil(point.y),
        math.floor(point.z + 0.5),
    )


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


def can_interact_with_block(block_hit):
    if block_hit is None:
        return False

    block_center = Vec3(
        block_hit.position[0],
        block_hit.position[1] - 0.5,
        block_hit.position[2],
    )
    return (player.position - block_center).length() <= BLOCK_INTERACTION_RANGE


def get_block_type_at(position):
    if position in removed_blocks:
        return None
    if position in custom_blocks:
        return custom_blocks[position]
    if position[1] == GROUND_Y:
        return GROUND_BLOCK_TYPE
    return None


def get_block_texture_key(block_type):
    return block_type["block_texture_path"]


def register_custom_block(position, block_type):
    custom_blocks[position] = block_type
    custom_blocks_by_chunk.setdefault(chunk_key_from_block(position), set()).add(position)


def unregister_custom_block(position):
    custom_blocks.pop(position, None)
    chunk_key = chunk_key_from_block(position)
    chunk_positions = custom_blocks_by_chunk.get(chunk_key)
    if not chunk_positions:
        return
    chunk_positions.discard(position)
    if not chunk_positions:
        custom_blocks_by_chunk.pop(chunk_key, None)


def get_chunk_positions_for_mesh(chunk_key):
    return tuple(
        iter_chunk_block_positions(
            chunk_key,
            GROUND_Y,
            GROUND_BLOCK_TYPE,
            custom_blocks_by_chunk.get(chunk_key, ()),
            custom_blocks,
            removed_blocks,
        )
    )


def mark_chunk_dirty(chunk_key):
    dirty_chunks.add(chunk_key)


def mark_dirty_chunks_for_position(position):
    chunk_key = chunk_key_from_block(position)
    cx, cy, cz = chunk_key
    for delta_x, delta_y, delta_z in (
        (0, 0, 0),
        (-1, 0, 0),
        (1, 0, 0),
        (0, -1, 0),
        (0, 1, 0),
        (0, 0, -1),
        (0, 0, 1),
    ):
        mark_chunk_dirty((cx + delta_x, cy + delta_y, cz + delta_z))


def create_chunk_entity(chunk_key):
    origin_x = chunk_key[0] * CHUNK_SIZE
    origin_y = chunk_key[1] * CHUNK_SIZE
    origin_z = chunk_key[2] * CHUNK_SIZE
    chunk_entity = Entity(
        parent=scene,
        position=Vec3(origin_x, origin_y, origin_z),
        texture=BLOCK_ATLAS_TEXTURE,
        shader=unlit_shader,
        color=color.white,
        enabled=False,
    )
    chunk_entity.chunk_key = chunk_key
    active_chunks[chunk_key] = chunk_entity
    rebuild_chunk_entity(chunk_key)
    return chunk_entity


def rebuild_chunk_entity(chunk_key):
    chunk_entity = active_chunks.get(chunk_key)
    if chunk_entity is None:
        return

    mesh_data = build_chunk_mesh(
        chunk_key,
        get_chunk_positions_for_mesh(chunk_key),
        get_block_type_at,
        get_block_texture_key,
        BLOCK_ATLAS.tiles,
    )

    if mesh_data.is_empty:
        chunk_entity.enabled = False
        chunk_entity.collider = None
        chunk_entity.model = None
        dirty_chunks.discard(chunk_key)
        return

    render_triangles = reverse_triangle_winding(mesh_data.triangles)

    chunk_entity.collider = None
    chunk_entity.model = Mesh(
        vertices=mesh_data.vertices,
        triangles=render_triangles,
        uvs=mesh_data.uvs,
        mode="triangle",
        static=True,
    )
    chunk_entity.texture = BLOCK_ATLAS_TEXTURE
    chunk_entity.collider = Mesh(
        vertices=mesh_data.vertices,
        triangles=render_triangles,
        mode="triangle",
        static=True,
    )
    chunk_entity.enabled = True
    apply_lighting_to_entity(chunk_entity)
    dirty_chunks.discard(chunk_key)


def remove_chunk_entity(chunk_key):
    chunk_entity = active_chunks.pop(chunk_key, None)
    if chunk_entity is not None:
        destroy(chunk_entity)
    dirty_chunks.discard(chunk_key)


def set_block_at(position, block_type):
    removed_blocks.discard(position)

    if position[1] == GROUND_Y and block_type == GROUND_BLOCK_TYPE:
        unregister_custom_block(position)
    else:
        register_custom_block(position, block_type)

    mark_dirty_chunks_for_position(position)
    chunk_visibility_dirty[0] = True


def remove_block_at(position):
    unregister_custom_block(position)
    if position[1] == GROUND_Y:
        removed_blocks.add(position)
    else:
        removed_blocks.discard(position)

    mark_dirty_chunks_for_position(position)
    chunk_visibility_dirty[0] = True


def get_priority_ground_chunks(position):
    min_chunk_x = math.floor((position[0] - PRIORITY_GROUND_RADIUS) / CHUNK_SIZE)
    max_chunk_x = math.floor((position[0] + PRIORITY_GROUND_RADIUS) / CHUNK_SIZE)
    min_chunk_z = math.floor((position[2] - PRIORITY_GROUND_RADIUS) / CHUNK_SIZE)
    max_chunk_z = math.floor((position[2] + PRIORITY_GROUND_RADIUS) / CHUNK_SIZE)
    ground_chunk_y = chunk_key_from_block((0, GROUND_Y, 0))[1]

    desired = set()
    for chunk_x in range(min_chunk_x, max_chunk_x + 1):
        for chunk_z in range(min_chunk_z, max_chunk_z + 1):
            desired.add((chunk_x, ground_chunk_y, chunk_z))
    return desired


def get_desired_positions(render_cell):
    if render_cell is None:
        return set()

    px, py, pz = render_cell
    desired = set()
    player_chunk = chunk_key_from_block(render_cell)
    ground_chunk_y = chunk_key_from_block((0, GROUND_Y, 0))[1]

    for delta_x in range(-GROUND_RENDER_CHUNK_RADIUS, GROUND_RENDER_CHUNK_RADIUS + 1):
        for delta_z in range(-GROUND_RENDER_CHUNK_RADIUS, GROUND_RENDER_CHUNK_RADIUS + 1):
            desired.add((player_chunk[0] + delta_x, ground_chunk_y, player_chunk[2] + delta_z))

    filtered_custom_positions = get_filtered_custom_positions(
        custom_blocks.keys(),
        px,
        py,
        pz,
        CUSTOM_RENDER_RADIUS,
        CUSTOM_RENDER_HEIGHT,
    )

    for position in filtered_custom_positions:
        desired.add(chunk_key_from_block(position))
        desired.update(get_priority_ground_chunks(position))

    return desired


def get_desired_positions_from_snapshots(render_cell, custom_positions, removed_positions):
    del removed_positions
    if render_cell is None:
        return set()

    px, py, pz = render_cell
    desired = set()
    player_chunk = chunk_key_from_block(render_cell)
    ground_chunk_y = chunk_key_from_block((0, GROUND_Y, 0))[1]

    for delta_x in range(-GROUND_RENDER_CHUNK_RADIUS, GROUND_RENDER_CHUNK_RADIUS + 1):
        for delta_z in range(-GROUND_RENDER_CHUNK_RADIUS, GROUND_RENDER_CHUNK_RADIUS + 1):
            desired.add((player_chunk[0] + delta_x, ground_chunk_y, player_chunk[2] + delta_z))

    filtered_custom_positions = get_filtered_custom_positions(
        custom_positions,
        px,
        py,
        pz,
        CUSTOM_RENDER_RADIUS,
        CUSTOM_RENDER_HEIGHT,
    )

    for position in filtered_custom_positions:
        desired.add(chunk_key_from_block(position))
        desired.update(get_priority_ground_chunks(position))

    return desired


desired_positions_scheduler[0] = DesiredPositionsScheduler(
    desired_positions_executor,
    get_desired_positions_from_snapshots,
)


def sync_active_blocks(force=False):
    render_cell = get_render_cell(player.position)
    render_chunk = get_render_chunk(player.position)
    desired_chunks = last_desired_chunks[0]
    needs_visibility_refresh = force or chunk_visibility_dirty[0] or render_chunk != last_render_chunk[0]

    if needs_visibility_refresh:
        if force:
            desired_chunks = get_desired_positions(render_cell)
        else:
            desired_positions_scheduler[0].request(
                render_cell,
                tuple(custom_blocks.keys()),
                tuple(removed_blocks),
            )
            desired_chunks = desired_positions_scheduler[0].consume(render_cell)
            if desired_chunks is None:
                for chunk_key in tuple(dirty_chunks):
                    if chunk_key in active_chunks:
                        rebuild_chunk_entity(chunk_key)
                return

        current_chunks = set(active_chunks)
        for chunk_key in current_chunks - desired_chunks:
            remove_chunk_entity(chunk_key)

        for chunk_key in desired_chunks - current_chunks:
            create_chunk_entity(chunk_key)

        last_render_chunk[0] = render_chunk
        last_render_cell[0] = render_cell
        last_desired_chunks[0] = desired_chunks
        chunk_visibility_dirty[0] = False

    for chunk_key in tuple(dirty_chunks):
        if chunk_key not in last_desired_chunks[0]:
            dirty_chunks.discard(chunk_key)
            continue
        if chunk_key not in active_chunks:
            create_chunk_entity(chunk_key)
            continue
        rebuild_chunk_entity(chunk_key)


def get_target_block():
    ignore = [player]
    if highlighted_box[0] is not None:
        ignore.append(highlighted_box[0])

    hit = raycast(
        camera.world_position,
        camera.forward,
        distance=BLOCK_INTERACTION_RANGE,
        ignore=tuple(ignore),
    )
    if not hit.hit or not hasattr(hit.entity, "chunk_key"):
        return None

    block_position = world_point_to_block_position(hit.world_point - (hit.world_normal * 0.001))
    block_type = get_block_type_at(block_position)
    if block_type is None:
        return None

    return BlockHit(
        position=block_position,
        normal=(
            int(round(hit.world_normal.x)),
            int(round(hit.world_normal.y)),
            int(round(hit.world_normal.z)),
        ),
        distance=hit.distance,
        block_type=block_type,
    )


def highlight_box(block_hit):
    if highlighted_box[0] is None:
        return

    if block_hit is None:
        highlighted_box[0].enabled = False
        return

    highlighted_box[0].enabled = True
    highlighted_box[0].position = Vec3(
        block_hit.position[0],
        block_hit.position[1],
        block_hit.position[2],
    )


def update_highlight():
    highlight_box(get_target_block())


def get_supporting_block():
    ignore = [player]
    if highlighted_box[0] is not None:
        ignore.append(highlighted_box[0])

    hit = raycast(
        player.position + Vec3(0, 0.1, 0),
        Vec3(0, -1, 0),
        distance=2,
        ignore=tuple(ignore),
    )
    if not hit.hit or not hasattr(hit.entity, "chunk_key"):
        return None

    support_position = world_point_to_block_position(hit.world_point - (hit.world_normal * 0.001))
    return get_block_type_at(support_position)


def set_global_light_level(daylight):
    current_light_level[0] = int(145 + (110 * daylight))


def apply_lighting_to_entity(entity):
    entity.color = color.white


def refresh_active_block_lighting():
    for chunk_entity in active_chunks.values():
        apply_lighting_to_entity(chunk_entity)


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


def mob_position_is_blocked(position, entity=None, player_radius=0.75, footprint=0.48):
    player_distance = Vec3(position.x - player.x, 0, position.z - player.z).length()
    if player_distance < player_radius and abs(position.y - player.y) < 1.4:
        return True

    model_min_y = get_entity_model_min_y(entity) if entity is not None else -0.5
    model_max_y = get_entity_model_max_y(entity) if entity is not None else 0.5
    scale_y = getattr(entity, "scale_y", 1.0) if entity is not None else 1.0
    body_bottom = position.y + (model_min_y * scale_y) + 0.04
    body_top = position.y + (model_max_y * scale_y) - 0.04

    min_x = math.floor(position.x - footprint)
    max_x = math.ceil(position.x + footprint)
    min_z = math.floor(position.z - footprint)
    max_z = math.ceil(position.z + footprint)
    min_y = math.floor(body_bottom)
    max_y = math.ceil(body_top)

    for bx in range(min_x, max_x + 1):
        for bz in range(min_z, max_z + 1):
            if abs(bx - position.x) > footprint or abs(bz - position.z) > footprint:
                continue

            for by in range(min_y, max_y + 1):
                if get_block_type_at((bx, by, bz)) is None:
                    continue

                block_top = float(by)
                block_bottom = block_top - 1.0
                if block_top <= body_bottom or block_bottom >= body_top:
                    continue
                return True

    return False


def chicken_position_is_blocked(position):
    return mob_position_is_blocked(position, entity=chicken, player_radius=0.75)


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


def apply_mob_gravity(entity, fallback_position=None, footprint=0.5):
    grounded_y = get_grounded_y_for_entity_at(
        entity,
        entity.x,
        entity.z,
        probe_from_y=max(entity.y + 6.0, GROUND_Y + 8.0),
        footprint=footprint,
    )
    if grounded_y is None:
        entity.y -= MOB_FALL_SPEED * time.dt
        if fallback_position is not None and entity.y < fallback_position.y - MOB_RESPAWN_FALL_DISTANCE:
            entity.position = Vec3(fallback_position.x, fallback_position.y, fallback_position.z)
            grounded_y = get_grounded_y_for_entity_at(
                entity,
                entity.x,
                entity.z,
                probe_from_y=max(entity.y + 6.0, GROUND_Y + 8.0),
                footprint=footprint,
            )
            if grounded_y is not None:
                entity.y = grounded_y
        return grounded_y

    if grounded_y < entity.y:
        entity.y = max(grounded_y, entity.y - (MOB_FALL_SPEED * time.dt))
    else:
        entity.y = grounded_y
    return grounded_y


def move_entity_with_grounding(entity, next_x, next_z, fallback_position=None, player_radius=0.75, footprint=0.5):
    target_grounded_y = get_grounded_y_for_entity_at(
        entity,
        next_x,
        next_z,
        probe_from_y=max(entity.y + 6.0, GROUND_Y + 8.0),
        footprint=footprint,
    )

    if target_grounded_y is not None:
        step_up = target_grounded_y - entity.y
        if step_up > MOB_STEP_HEIGHT:
            return False, None
        candidate_position = Vec3(next_x, target_grounded_y, next_z)
    else:
        candidate_position = Vec3(next_x, entity.y, next_z)

    if mob_position_is_blocked(candidate_position, entity=entity, player_radius=player_radius, footprint=footprint):
        return False, target_grounded_y

    entity.position = candidate_position
    grounded_y = apply_mob_gravity(
        entity,
        fallback_position=fallback_position,
        footprint=footprint,
    )
    return True, grounded_y


def update_generic_mob_walk(mob_state):
    mob = mob_state["entity"]
    target = mob_state["target"][0]
    fallback_position = mob_state["spawn"]
    grounded_y = apply_mob_gravity(
        mob,
        fallback_position=fallback_position,
        footprint=0.52,
    )
    if grounded_y is not None:
        mob_state["grounded_y"] = grounded_y

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
    moved, grounded_y = move_entity_with_grounding(
        mob,
        mob.x + (direction.x * step_distance),
        mob.z + (direction.z * step_distance),
        fallback_position=fallback_position,
        player_radius=mob_state["player_radius"],
        footprint=0.52,
    )

    if not moved:
        moved, grounded_y = move_entity_with_grounding(
            mob,
            mob.x + (direction.x * step_distance),
            mob.z,
            fallback_position=fallback_position,
            player_radius=mob_state["player_radius"],
            footprint=0.52,
        )
    if not moved:
        moved, grounded_y = move_entity_with_grounding(
            mob,
            mob.x,
            mob.z + (direction.z * step_distance),
            fallback_position=fallback_position,
            player_radius=mob_state["player_radius"],
            footprint=0.52,
        )
    if not moved:
        mob_state["target"][0] = get_new_mob_walk_target(mob_state)
        return

    if grounded_y is not None:
        mob_state["grounded_y"] = grounded_y

    if direction.length() > 0:
        mob.rotation_y = math.degrees(math.atan2(direction.x, direction.z))

    mob_state["animation_time"][0] += time.dt * (2.2 + (step_distance * 5.0))
    mob.rotation_z = math.sin(mob_state["animation_time"][0] * 0.45) * 1.2


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
    apply_mob_gravity(
        chicken,
        fallback_position=chicken_spawn_position,
        footprint=0.42,
    )
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
    moved, _ = move_entity_with_grounding(
        chicken,
        chicken.x + (direction.x * step_distance),
        chicken.z + (direction.z * step_distance),
        fallback_position=chicken_spawn_position,
        player_radius=0.75,
        footprint=0.42,
    )
    if not moved:
        moved, _ = move_entity_with_grounding(
            chicken,
            chicken.x + (direction.x * step_distance),
            chicken.z,
            fallback_position=chicken_spawn_position,
            player_radius=0.75,
            footprint=0.42,
        )
    if not moved:
        moved, _ = move_entity_with_grounding(
            chicken,
            chicken.x,
            chicken.z + (direction.z * step_distance),
            fallback_position=chicken_spawn_position,
            player_radius=0.75,
            footprint=0.42,
        )
    if not moved:
        chicken_walk_target[0] = get_new_chicken_walk_target()
        return

    if direction.length() > 0:
        chicken.rotation_y = math.degrees(math.atan2(direction.x, direction.z))

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
if hasattr(player, "height"):
    player.height = 1.8
if hasattr(player, "cursor") and player.cursor is not None:
    player.cursor.enabled = False
player.base_speed = getattr(player, "speed", 5)
spawn_point = Vec3(player.x, player.y, player.z)
set_global_light_level(1.0)
sync_active_blocks(force=True)
highlighted_box[0] = Entity(
    parent=scene,
    model="wireframe_cube",
    position=Vec3(0, -999, 0),
    scale=1.005,
    origin_y=0.5,
    color=color.rgba(255, 255, 255, 180),
    shader=unlit_shader,
    collider=None,
    enabled=False,
)

menu = None
crosshair = None
background_music = None
background_music_playlist = get_music_playlist_files()
background_music_track_index = [0]
music_enabled = [True]
music_volume = [0.25]
fps_overlay = None
fps_overlay_text = None
inventory_open = [False]
inventory_panel = [None]
inventory_backdrop = [None]
inventory_card = [None]
inventory_slot_buttons = []
inventory_slot_icons = []
inventory_slot_block_indices = [[]]
inventory_hotbar_selector = [None]
inventory_hotbar_buttons = []
inventory_hotbar_icons = []
inventory_drag_icon = [None]
inventory_drag_origin = [None]
inventory_drag_block_index = [None]
inventory_player_preview = [None]

INVENTORY_TEXTURE_WIDTH = 176
INVENTORY_TEXTURE_HEIGHT = 166
INVENTORY_CARD_SCALE_X = 0.94
INVENTORY_CARD_SCALE_Y = INVENTORY_CARD_SCALE_X * (INVENTORY_TEXTURE_HEIGHT / INVENTORY_TEXTURE_WIDTH)
INVENTORY_COLUMNS = 9
INVENTORY_ROWS = 3
INVENTORY_PAGE_SIZE = INVENTORY_COLUMNS * INVENTORY_ROWS


def on_menu_toggle(state):
    if state and inventory_open[0]:
        set_inventory_open(False)
    if crosshair is not None:
        crosshair.enabled = not state and not inventory_open[0]
    if "hotbar_bg" in globals():
        set_game_hud_visible(not state and not inventory_open[0])
    if fps_overlay is not None:
        fps_overlay.enabled = fps_overlay_visible[0] and not state
    if fps_overlay_text is not None:
        fps_overlay_text.enabled = fps_overlay_visible[0] and not state
    if state:
        highlight_box(None)


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


def play_background_music_track(track_index):
    global background_music

    if not background_music_playlist:
        background_music = None
        return

    normalized_index = track_index % len(background_music_playlist)
    background_music_track_index[0] = normalized_index

    if background_music is not None:
        try:
            background_music.stop()
        except Exception:
            pass

    background_music = Audio(
        background_music_playlist[normalized_index],
        autoplay=True,
        loop=False,
        volume=music_volume[0] if music_enabled[0] else 0.0,
    )


def update_background_music():
    if not background_music_playlist or background_music is None:
        return
    if not music_enabled[0]:
        return

    try:
        if background_music.playing:
            return
    except Exception:
        pass

    play_background_music_track(background_music_track_index[0] + 1)


def is_game_paused():
    return bool(menu and menu.is_blocking_gameplay())


menu = GameMenu(
    player,
    on_menu_toggle,
    toggle_fullscreen,
    toggle_music_enabled,
    get_music_enabled,
    get_music_volume,
    set_music_volume_delta,
)

crosshair = None

if background_music_playlist:
    play_background_music_track(0)

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
    scale=(HOTBAR_BG_SCALE_X, HOTBAR_BG_SCALE_Y),
)

hotbar_selector = Entity(
    parent=camera.ui,
    model="quad",
    texture=resolve_existing_asset_path([f"{UI_PATH}/Hotbar_selector.png"]) or "white_cube",
    position=(0, -0.45, 0.9),
    scale=(HOTBAR_SELECTOR_SCALE, HOTBAR_SELECTOR_SCALE),
)

hotbar_icons = []
hotbar_slot_positions = []
hud_heart_icons = []
hud_armor_icons = []


def create_hotbar_ui():
    slot_spacing = hotbar_bg.scale_x * (HOTBAR_SLOT_SPACING_PX / HOTBAR_TEXTURE_WIDTH)
    start_x = hotbar_bg.x - (hotbar_bg.scale_x / 2) + (
        hotbar_bg.scale_x * (HOTBAR_FIRST_SLOT_CENTER_PX / HOTBAR_TEXTURE_WIDTH)
    )
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


def set_selected_hotbar_slot(slot_index):
    global selected_block_index
    selected_block_index = max(0, min(slot_index, HOTBAR_SLOT_COUNT - 1))
    update_hotbar_ui()


def assign_inventory_block_to_selected_slot(block_index):
    hotbar_block_indices[selected_block_index] = block_index
    update_hotbar_ui()
    refresh_inventory_grid()


def inventory_pixel_to_local(x_px, y_px, z=-0.02):
    return Vec3((x_px / INVENTORY_TEXTURE_WIDTH) - 0.5, 0.5 - (y_px / INVENTORY_TEXTURE_HEIGHT), z)


def inventory_pixel_scale(width_px, height_px):
    return Vec3(width_px / INVENTORY_TEXTURE_WIDTH, height_px / INVENTORY_TEXTURE_HEIGHT, 1.0)


def inventory_slot_icon_scale():
    return Vec3(16 / 18, 16 / 18, 1.0)


def get_inventory_grid_slot_position(slot_index):
    col = slot_index % INVENTORY_COLUMNS
    row = slot_index // INVENTORY_COLUMNS
    return inventory_pixel_to_local(15.5 + (col * 18), 91.5 + (row * 18))


def get_inventory_hotbar_slot_position(slot_index):
    return inventory_pixel_to_local(16.5 + (slot_index * 18), 149.5)


def refresh_inventory_hotbar_preview():
    if inventory_hotbar_selector[0] is None:
        return

    inventory_hotbar_selector[0].position = get_inventory_hotbar_slot_position(selected_block_index)

    for slot_index, icon in enumerate(inventory_hotbar_icons):
        block_index = hotbar_block_indices[slot_index]
        icon.texture = get_block_icon_texture(BLOCK_TYPES[block_index])


def refresh_inventory_grid():
    if not inventory_slot_icons:
        return

    visible_indices = list(range(min(INVENTORY_PAGE_SIZE, len(BLOCK_TYPES))))
    inventory_slot_block_indices[0] = visible_indices

    for slot_index, icon in enumerate(inventory_slot_icons):
        has_block = slot_index < len(visible_indices)
        inventory_slot_buttons[slot_index].enabled = has_block
        inventory_slot_buttons[slot_index].visible = has_block
        icon.enabled = has_block
        if has_block:
            block_index = visible_indices[slot_index]
            icon.texture = get_block_icon_texture(BLOCK_TYPES[block_index])

    refresh_inventory_hotbar_preview()


def get_inventory_hovered_slot():
    for slot_index, button in enumerate(inventory_hotbar_buttons):
        if button.hovered:
            return ("hotbar", slot_index)

    for slot_index, button in enumerate(inventory_slot_buttons):
        if button.enabled and button.hovered:
            return ("inventory", slot_index)

    return (None, None)


def clear_inventory_drag():
    inventory_drag_origin[0] = None
    inventory_drag_block_index[0] = None
    if inventory_drag_icon[0] is not None:
        inventory_drag_icon[0].enabled = False


def set_inventory_entities_enabled(enabled):
    if inventory_card[0] is not None:
        inventory_card[0].enabled = enabled
    if inventory_hotbar_selector[0] is not None:
        inventory_hotbar_selector[0].enabled = enabled
    if inventory_player_preview[0] is not None:
        inventory_player_preview[0].enabled = enabled

    for button in inventory_hotbar_buttons:
        button.enabled = enabled
    for icon in inventory_hotbar_icons:
        icon.enabled = enabled

    for button in inventory_slot_buttons:
        button.enabled = enabled
    for icon in inventory_slot_icons:
        icon.enabled = enabled


def set_game_hud_visible(visible):
    hotbar_bg.enabled = visible
    hotbar_selector.enabled = visible
    for icon in hotbar_icons:
        icon.enabled = visible
    for icon in hud_heart_icons:
        icon.enabled = visible
    for icon in hud_armor_icons:
        icon.enabled = visible


def create_inventory_player_preview():
    inventory_player_preview[0] = Entity(
        parent=inventory_card[0],
        model="quad",
        texture=resolve_existing_asset_path([f"{UI_PATH}/player_preview.png"]) or "white_cube",
        color=color.white,
        position=inventory_pixel_to_local(48.5, 40.5, -0.02),
        scale=inventory_pixel_scale(32, 64),
    )


def start_inventory_drag():
    slot_kind, slot_index = get_inventory_hovered_slot()
    if slot_kind is None:
        return False

    if slot_kind == "inventory":
        visible_indices = inventory_slot_block_indices[0]
        if slot_index >= len(visible_indices):
            return False
        block_index = visible_indices[slot_index]
    else:
        block_index = hotbar_block_indices[slot_index]
        set_selected_hotbar_slot(slot_index)

    inventory_drag_origin[0] = (slot_kind, slot_index)
    inventory_drag_block_index[0] = block_index

    if inventory_drag_icon[0] is not None:
        inventory_drag_icon[0].texture = get_block_icon_texture(BLOCK_TYPES[block_index])
        inventory_drag_icon[0].position = Vec3(mouse.position[0], mouse.position[1], -0.35)
        inventory_drag_icon[0].enabled = True

    return True


def finish_inventory_drag():
    if inventory_drag_origin[0] is None or inventory_drag_block_index[0] is None:
        return False

    origin_kind, origin_index = inventory_drag_origin[0]
    target_kind, target_index = get_inventory_hovered_slot()

    if target_kind == "hotbar":
        if origin_kind == "hotbar":
            hotbar_block_indices[origin_index], hotbar_block_indices[target_index] = (
                hotbar_block_indices[target_index],
                hotbar_block_indices[origin_index],
            )
        else:
            hotbar_block_indices[target_index] = inventory_drag_block_index[0]
        set_selected_hotbar_slot(target_index)
        update_hotbar_ui()
    elif target_kind == "inventory" and origin_kind == "hotbar":
        visible_indices = inventory_slot_block_indices[0]
        if target_index < len(visible_indices):
            hotbar_block_indices[origin_index] = visible_indices[target_index]
            set_selected_hotbar_slot(origin_index)
            update_hotbar_ui()

    clear_inventory_drag()
    refresh_inventory_grid()
    return True


def create_inventory_ui():
    inventory_backdrop[0] = Entity(
        parent=camera.ui,
        model="quad",
        color=color.rgba(0, 0, 0, 0),
        scale=(2.0, 2.0),
        z=0.45,
        enabled=False,
    )

    inventory_panel[0] = Entity(
        parent=camera.ui,
        color=color.rgba(0, 0, 0, 0),
        scale=(1.0, 1.0),
        z=0.44,
        enabled=False,
    )

    inventory_card[0] = Entity(
        parent=inventory_panel[0],
        model="quad",
        texture=resolve_existing_asset_path([f"{UI_PATH}/inventory.png"]) or "white_cube",
        color=color.white,
        scale=(INVENTORY_CARD_SCALE_X, INVENTORY_CARD_SCALE_Y),
        z=0,
    )

    inventory_hotbar_selector[0] = Entity(
        parent=inventory_card[0],
        model="quad",
        texture=resolve_existing_asset_path([f"{UI_PATH}/Hotbar_selector.png"]) or "white_cube",
        color=color.white,
        scale=inventory_pixel_scale(24, 24),
        position=get_inventory_hotbar_slot_position(selected_block_index),
        z=-0.03,
    )

    for slot_idx in range(HOTBAR_SLOT_COUNT):
        slot_button = Button(
            parent=inventory_card[0],
            model="quad",
            texture="white_cube",
            color=color.rgba(255, 255, 255, 1),
            scale=inventory_pixel_scale(18, 18),
            position=get_inventory_hotbar_slot_position(slot_idx),
            text="",
            highlight_color=color.rgba(255, 255, 255, 18),
            pressed_color=color.rgba(255, 255, 255, 36),
        )
        inventory_hotbar_buttons.append(slot_button)
        inventory_hotbar_icons.append(
            Entity(
                parent=slot_button,
                model="quad",
                texture=get_block_icon_texture(BLOCK_TYPES[hotbar_block_indices[slot_idx]]),
                position=(0, 0, -0.02),
                scale=inventory_slot_icon_scale(),
                color=color.white,
            )
        )

    for slot_idx in range(INVENTORY_PAGE_SIZE):
        slot_button = Button(
            parent=inventory_card[0],
            model="quad",
            texture="white_cube",
            color=color.rgba(255, 255, 255, 1),
            scale=inventory_pixel_scale(18, 18),
            position=get_inventory_grid_slot_position(slot_idx),
            text="",
            highlight_color=color.rgba(255, 255, 255, 18),
            pressed_color=color.rgba(255, 255, 255, 36),
        )
        inventory_slot_buttons.append(slot_button)
        inventory_slot_icons.append(
            Entity(
                parent=slot_button,
                model="quad",
                texture="white_cube",
                position=(0, 0, -0.02),
                scale=inventory_slot_icon_scale(),
                color=color.white,
            )
        )

    create_inventory_player_preview()

    inventory_drag_icon[0] = Entity(
        parent=camera.ui,
        model="quad",
        texture="white_cube",
        scale=Vec3(
            INVENTORY_CARD_SCALE_X * (16 / INVENTORY_TEXTURE_WIDTH),
            INVENTORY_CARD_SCALE_Y * (16 / INVENTORY_TEXTURE_HEIGHT),
            1.0,
        ),
        color=color.white,
        z=-0.35,
        enabled=False,
    )

    refresh_inventory_hotbar_preview()
    refresh_inventory_grid()
    set_inventory_entities_enabled(False)


def set_inventory_open(state):
    inventory_open[0] = bool(state)
    if inventory_backdrop[0] is not None:
        inventory_backdrop[0].enabled = inventory_open[0]
    if inventory_panel[0] is not None:
        inventory_panel[0].enabled = inventory_open[0]

    set_inventory_entities_enabled(inventory_open[0])

    if inventory_open[0]:
        player.enabled = False
        mouse.locked = False
        set_game_hud_visible(False)
        if crosshair is not None:
            crosshair.enabled = False
    else:
        should_enable_player = not is_game_paused()
        player.enabled = should_enable_player
        mouse.locked = should_enable_player
        set_game_hud_visible(should_enable_player)
        if crosshair is not None:
            crosshair.enabled = should_enable_player
        clear_inventory_drag()
        update_hotbar_ui()
        return

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
set_game_hud_visible(False)
if crosshair is not None:
    crosshair.enabled = False
highlight_box(None)
invoke(center_game_window, delay=0.05)

flash = None


def respawn_flash():
    Audio(DAMAGE_SOUND_PATH, autoplay=True)


def input(key):
    global selected_block_index

    if key == "f11":
        toggle_fullscreen()
        return

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
        if menu and menu.handle_escape():
            return
        return

    if key == "e":
        if menu and menu.is_blocking_gameplay():
            return
        if inventory_panel[0] is None:
            create_inventory_ui()
        set_inventory_open(not inventory_open[0])
        return

    if not menu or menu.is_blocking_gameplay():
        return

    if key.isdigit():
        idx = int(key) - 1
        if 0 <= idx < HOTBAR_SLOT_COUNT:
            set_selected_hotbar_slot(idx)
            return

    if inventory_open[0]:
        if key == "left mouse down":
            start_inventory_drag()
            return
        if key == "left mouse up":
            finish_inventory_drag()
            return
        return

    if key == "scroll up":
        set_selected_hotbar_slot((selected_block_index + 1) % HOTBAR_SLOT_COUNT)
        return

    if key == "scroll down":
        set_selected_hotbar_slot((selected_block_index - 1) % HOTBAR_SLOT_COUNT)
        return

    if key == "space":
        support_block = last_support_block[0]
        if player.enabled and player.grounded and support_block is not None:
            play_material_sound(support_block, "jump")
        return

    target_block = get_target_block()
    if target_block is None:
        return

    if not can_interact_with_block(target_block):
        return

    if key == "right mouse down":
        new_position = (
            target_block.position[0] + target_block.normal[0],
            target_block.position[1] + target_block.normal[1],
            target_block.position[2] + target_block.normal[2],
        )
        if get_block_type_at(new_position) is None:
            block_type = get_selected_block_type()
            set_block_at(new_position, block_type)
            play_material_sound(block_type, "place")
        return

    if key == "left mouse down":
        play_material_sound(target_block.block_type, "hit")
        play_material_sound(target_block.block_type, "break")
        remove_block_at(target_block.position)
        highlight_box(None)


def update():
    camera.background_color = color.rgb(16, 24, 36)
    try:
        app.win.setClearColor((16 / 255, 24 / 255, 36 / 255, 1.0))
    except Exception:
        pass
    # Defensive workaround: some environments expose a giant transparent UI
    # quad that renders as opaque white. Hide/destroy it when detected.
    cleanup_problematic_ui_quads(destroy_matches=False)
    update_background_music()

    sync_active_blocks()
    if is_game_paused():
        highlight_box(None)
    else:
        update_highlight()
    if inventory_open[0] and inventory_drag_icon[0] is not None and inventory_drag_icon[0].enabled:
        inventory_drag_icon[0].position = Vec3(mouse.position[0], mouse.position[1], -0.35)
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
        play_material_sound(support_block, "land")

    if player.enabled and moving and current_grounded:
        step_cooldown[0] -= time.dt
        if step_cooldown[0] <= 0:
            if support_block is not None:
                play_material_sound(support_block, "step")
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
