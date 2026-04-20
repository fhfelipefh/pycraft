"""Chunked voxel mesh helpers for PyCraft.

This module keeps the heavy voxel-world operations independent from Ursina so
they can be tested without booting the engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, Mapping, Optional, Sequence, Tuple
import math

from PIL import Image


GridPos = Tuple[int, int, int]
ChunkKey = Tuple[int, int, int]

CHUNK_SIZE = 16


@dataclass(frozen=True)
class AtlasTile:
    u0: float
    v0: float
    u1: float
    v1: float


@dataclass(frozen=True)
class TextureAtlas:
    texture_path: str
    tiles: Dict[str, AtlasTile]
    tile_size: int
    image_size: int


@dataclass(frozen=True)
class BlockHit:
    position: GridPos
    normal: GridPos
    distance: float
    block_type: Any


@dataclass
class ChunkMeshData:
    vertices: list[tuple[float, float, float]]
    triangles: list[int]
    uvs: list[tuple[float, float]]
    face_count: int = 0

    @property
    def is_empty(self) -> bool:
        return len(self.vertices) == 0


def reverse_triangle_winding(triangles: Sequence[int]) -> list[int]:
    reversed_triangles: list[int] = []
    for index in range(0, len(triangles), 3):
        triangle = triangles[index:index + 3]
        if len(triangle) < 3:
            continue
        reversed_triangles.extend((triangle[0], triangle[2], triangle[1]))
    return reversed_triangles


FACE_DEFINITIONS = (
    (
        (-1, 0, 0),
        ((-0.5, -1, -0.5), (-0.5, -1, 0.5), (-0.5, 0, 0.5), (-0.5, 0, -0.5)),
    ),
    (
        (1, 0, 0),
        ((0.5, -1, 0.5), (0.5, -1, -0.5), (0.5, 0, -0.5), (0.5, 0, 0.5)),
    ),
    (
        (0, -1, 0),
        ((-0.5, -1, -0.5), (0.5, -1, -0.5), (0.5, -1, 0.5), (-0.5, -1, 0.5)),
    ),
    (
        (0, 1, 0),
        ((-0.5, 0, 0.5), (0.5, 0, 0.5), (0.5, 0, -0.5), (-0.5, 0, -0.5)),
    ),
    (
        (0, 0, -1),
        ((0.5, -1, -0.5), (-0.5, -1, -0.5), (-0.5, 0, -0.5), (0.5, 0, -0.5)),
    ),
    (
        (0, 0, 1),
        ((-0.5, -1, 0.5), (0.5, -1, 0.5), (0.5, 0, 0.5), (-0.5, 0, 0.5)),
    ),
)

FACE_TRIANGLES = (0, 1, 2, 0, 2, 3)


def chunk_index(value: float, chunk_size: int = CHUNK_SIZE) -> int:
    return math.floor(value / chunk_size)


def chunk_key_from_block(position: GridPos, chunk_size: int = CHUNK_SIZE) -> ChunkKey:
    x, y, z = position
    return (
        chunk_index(x, chunk_size),
        chunk_index(y, chunk_size),
        chunk_index(z, chunk_size),
    )


def chunk_key_from_world(position: Any, chunk_size: int = CHUNK_SIZE) -> ChunkKey:
    return (
        chunk_index(float(position.x), chunk_size),
        chunk_index(float(position.y), chunk_size),
        chunk_index(float(position.z), chunk_size),
    )


def chunk_origin(chunk_key: ChunkKey, chunk_size: int = CHUNK_SIZE) -> GridPos:
    cx, cy, cz = chunk_key
    return (
        cx * chunk_size,
        cy * chunk_size,
        cz * chunk_size,
    )


def iter_chunk_block_positions(
    chunk_key: ChunkKey,
    ground_y: int,
    ground_block_type: Any,
    custom_positions: Iterable[GridPos],
    custom_blocks: Mapping[GridPos, Any],
    removed_blocks: set[GridPos],
    chunk_size: int = CHUNK_SIZE,
) -> Iterator[GridPos]:
    origin_x, origin_y, origin_z = chunk_origin(chunk_key, chunk_size=chunk_size)
    max_x = origin_x + chunk_size
    max_y = origin_y + chunk_size
    max_z = origin_z + chunk_size

    if origin_y <= ground_y < max_y:
        for world_x in range(origin_x, max_x):
            for world_z in range(origin_z, max_z):
                position = (world_x, ground_y, world_z)
                if position in removed_blocks:
                    continue
                if position in custom_blocks:
                    continue
                yield position

    for position in custom_positions:
        x, y, z = position
        if not (origin_x <= x < max_x and origin_y <= y < max_y and origin_z <= z < max_z):
            continue
        if position in removed_blocks:
            continue

        block_type = custom_blocks.get(position)
        if block_type is None:
            continue
        if y == ground_y and block_type == ground_block_type:
            continue
        yield position


def get_top_block_in_column(
    x: float,
    z: float,
    probe_from_y: float,
    get_block_type_at: Callable[[GridPos], Any],
    ground_y: int,
) -> Optional[GridPos]:
    block_x = math.floor(x + 0.5)
    block_z = math.floor(z + 0.5)
    max_y = math.ceil(probe_from_y)

    for block_y in range(max_y, ground_y - 1, -1):
        position = (block_x, block_y, block_z)
        if get_block_type_at(position) is not None:
            return position

    return None


def build_texture_atlas(
    texture_paths: Sequence[str],
    asset_root: Path,
    output_rel_path: str = "textures/_generated/blocks_atlas.png",
    padding: int = 1,
) -> TextureAtlas:
    if not texture_paths:
        raise ValueError("texture_paths cannot be empty")

    unique_paths = list(dict.fromkeys(texture_paths))
    images: Dict[str, Image.Image] = {}
    tile_size = 0

    for texture_path in unique_paths:
        texture_file = asset_root / texture_path
        if texture_file.exists():
            image = Image.open(texture_file).convert("RGBA")
        else:
            image = Image.new("RGBA", (16, 16), (255, 255, 255, 255))
        images[texture_path] = image
        tile_size = max(tile_size, image.width, image.height)

    resampling = getattr(getattr(Image, "Resampling", Image), "NEAREST")
    columns = math.ceil(math.sqrt(len(unique_paths)))
    rows = math.ceil(len(unique_paths) / columns)
    cell_size = tile_size + (padding * 2)
    atlas_size = max(1, columns * cell_size)
    atlas = Image.new("RGBA", (atlas_size, rows * cell_size), (0, 0, 0, 0))
    tiles: Dict[str, AtlasTile] = {}

    for index, texture_path in enumerate(unique_paths):
        image = images[texture_path]
        if image.width != tile_size or image.height != tile_size:
            image = image.resize((tile_size, tile_size), resample=resampling)

        col = index % columns
        row = index // columns
        px = col * cell_size + padding
        py = row * cell_size + padding
        atlas.paste(image, (px, py))

        left = px / atlas.width
        right = (px + tile_size) / atlas.width
        top = 1.0 - (py / atlas.height)
        bottom = 1.0 - ((py + tile_size) / atlas.height)
        tiles[texture_path] = AtlasTile(u0=left, v0=bottom, u1=right, v1=top)

    output_path = asset_root / output_rel_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    atlas.save(output_path)

    return TextureAtlas(
        texture_path=output_rel_path,
        tiles=tiles,
        tile_size=tile_size,
        image_size=atlas.width,
    )


def build_chunk_mesh(
    chunk_key: ChunkKey,
    positions: Iterable[GridPos],
    get_block_type_at: Callable[[GridPos], Any],
    texture_key_for_block: Callable[[Any], str],
    atlas_tiles: Mapping[str, AtlasTile],
    chunk_size: int = CHUNK_SIZE,
) -> ChunkMeshData:
    origin_x, origin_y, origin_z = chunk_origin(chunk_key, chunk_size=chunk_size)
    vertices: list[tuple[float, float, float]] = []
    triangles: list[int] = []
    uvs: list[tuple[float, float]] = []
    face_count = 0

    for position in positions:
        block_type = get_block_type_at(position)
        if block_type is None:
            continue

        texture_key = texture_key_for_block(block_type)
        tile = atlas_tiles[texture_key]
        local_x = position[0] - origin_x
        local_y = position[1] - origin_y
        local_z = position[2] - origin_z

        for normal, face_vertices in FACE_DEFINITIONS:
            neighbor_position = (
                position[0] + normal[0],
                position[1] + normal[1],
                position[2] + normal[2],
            )
            if get_block_type_at(neighbor_position) is not None:
                continue

            base_index = len(vertices)
            for offset_x, offset_y, offset_z in face_vertices:
                vertices.append(
                    (
                        local_x + offset_x,
                        local_y + offset_y,
                        local_z + offset_z,
                    )
                )

            triangles.extend(base_index + index for index in FACE_TRIANGLES)
            uvs.extend(
                (
                    (tile.u0, tile.v0),
                    (tile.u1, tile.v0),
                    (tile.u1, tile.v1),
                    (tile.u0, tile.v1),
                )
            )
            face_count += 1

    return ChunkMeshData(
        vertices=vertices,
        triangles=triangles,
        uvs=uvs,
        face_count=face_count,
    )


def _nudge_origin(value: float, direction_component: float) -> float:
    if direction_component > 0:
        return math.nextafter(value, math.inf)
    if direction_component < 0:
        return math.nextafter(value, -math.inf)
    return value


def _initial_axis_t(origin_component: float, direction_component: float, step: int) -> float:
    if step == 0:
        return math.inf

    if step > 0:
        next_boundary = math.floor(origin_component) + 1.0
    else:
        next_boundary = math.floor(origin_component)

    return (next_boundary - origin_component) / direction_component


def raycast_blocks(
    origin: tuple[float, float, float],
    direction: tuple[float, float, float],
    max_distance: float,
    get_block_type_at: Callable[[GridPos], Any],
) -> Optional[BlockHit]:
    dx, dy, dz = direction
    length = math.sqrt((dx * dx) + (dy * dy) + (dz * dz))
    if length == 0:
        return None

    dx /= length
    dy /= length
    dz /= length

    transformed_origin_x = origin[0] + 0.5
    transformed_origin_y = origin[1] + 1.0
    transformed_origin_z = origin[2] + 0.5

    ox = _nudge_origin(transformed_origin_x, dx)
    oy = _nudge_origin(transformed_origin_y, dy)
    oz = _nudge_origin(transformed_origin_z, dz)

    x = math.floor(ox)
    y = math.floor(oy)
    z = math.floor(oz)

    step_x = 1 if dx > 0 else -1 if dx < 0 else 0
    step_y = 1 if dy > 0 else -1 if dy < 0 else 0
    step_z = 1 if dz > 0 else -1 if dz < 0 else 0

    t_max_x = _initial_axis_t(ox, dx, step_x) if step_x else math.inf
    t_max_y = _initial_axis_t(oy, dy, step_y) if step_y else math.inf
    t_max_z = _initial_axis_t(oz, dz, step_z) if step_z else math.inf

    t_delta_x = abs(1.0 / dx) if step_x else math.inf
    t_delta_y = abs(1.0 / dy) if step_y else math.inf
    t_delta_z = abs(1.0 / dz) if step_z else math.inf

    distance = 0.0

    while distance <= max_distance:
        if t_max_x <= t_max_y and t_max_x <= t_max_z:
            x += step_x
            distance = t_max_x
            t_max_x += t_delta_x
            normal = (-step_x, 0, 0)
        elif t_max_y <= t_max_z:
            y += step_y
            distance = t_max_y
            t_max_y += t_delta_y
            normal = (0, -step_y, 0)
        else:
            z += step_z
            distance = t_max_z
            t_max_z += t_delta_z
            normal = (0, 0, -step_z)

        if distance > max_distance:
            break

        position = (x, y, z)
        block_type = get_block_type_at(position)
        if block_type is None:
            continue

        return BlockHit(
            position=position,
            normal=normal,
            distance=distance,
            block_type=block_type,
        )

    return None
