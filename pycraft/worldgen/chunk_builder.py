"""Chunk-oriented block composition over terrain density fields."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, Iterable, Iterator, Mapping, Tuple

from pycraft.voxel_chunk import ChunkKey, GridPos, chunk_origin
from pycraft.worldgen.surface import choose_subsurface_block, choose_surface_block
from pycraft.worldgen.terrain import ColumnSample, TerrainGenerator, TerrainGeneratorConfig


BlockType = Dict[str, str]


@dataclass(frozen=True)
class BlockPalette:
    grass: object
    dirt: object
    stone: object
    sand: object
    sandstone: object
    snow: object
    water: object
    lava: object


@dataclass(eq=False)
class WorldGenerator:
    palette: BlockPalette
    terrain: TerrainGenerator
    chunk_size: int = 16

    @classmethod
    def from_config(cls, palette: BlockPalette, config: TerrainGeneratorConfig, chunk_size: int = 16) -> "WorldGenerator":
        return cls(palette=palette, terrain=TerrainGenerator(config), chunk_size=chunk_size)

    def get_base_block_at(self, position: GridPos) -> object | None:
        return self._get_base_block_cached(*position)

    @lru_cache(maxsize=131072)
    def _get_base_block_cached(self, x: int, y: int, z: int) -> object | None:
        if y < self.terrain.config.min_y or y > self.terrain.config.max_y:
            return None

        column = self.terrain.sample_column(x, z)
        density = self.terrain.density_at(x, y, z, column)
        if density > 0.0:
            return self._solid_block_for_depth(y, column)

        fluid = self.terrain.fluid_for_empty(x, y, z)
        if fluid == "water":
            return self.palette.water
        if fluid == "lava":
            return self.palette.lava
        return None

    def iter_base_positions_for_chunk(self, chunk_key: ChunkKey) -> Iterator[GridPos]:
        origin_x, origin_y, origin_z = chunk_origin(chunk_key, chunk_size=self.chunk_size)
        max_x = origin_x + self.chunk_size
        max_y = origin_y + self.chunk_size
        max_z = origin_z + self.chunk_size

        for x in range(origin_x, max_x):
            for z in range(origin_z, max_z):
                for y in range(origin_y, max_y):
                    if self.get_base_block_at((x, y, z)) is not None:
                        yield (x, y, z)

    def _solid_block_for_depth(self, y: int, column: ColumnSample) -> object:
        depth = column.surface_height - y
        if depth <= 0:
            top = choose_surface_block(column.biome)
            return self._palette_block(top)
        if depth <= 3:
            sub = choose_subsurface_block(column.biome)
            return self._palette_block(sub)
        return self.palette.stone

    def _palette_block(self, name: str) -> object:
        return getattr(self.palette, name, self.palette.stone)


def build_block_palette(block_types: Iterable[object]) -> BlockPalette:
    by_texture: Dict[str, object] = {}
    by_name: Dict[str, object] = {}

    for block_type in block_types:
        texture = str(block_type.get("block_texture", "")).lower()
        name = str(block_type.get("name", "")).lower()
        by_texture[texture] = block_type
        by_name[name] = block_type

    def find(*tokens: str, fallback: object | None = None) -> object:
        for token in tokens:
            token_l = token.lower()
            if token_l in by_texture:
                return by_texture[token_l]
            if token_l in by_name:
                return by_name[token_l]

            for texture_name, block_type in by_texture.items():
                if token_l in texture_name:
                    return block_type
            for block_name, block_type in by_name.items():
                if token_l in block_name:
                    return block_type

        if fallback is not None:
            return fallback
        raise ValueError(f"Unable to resolve block for tokens: {tokens}")

    def find_optional(*tokens: str) -> object | None:
        try:
            return find(*tokens)
        except ValueError:
            return None

    stone = find("stone")
    dirt = find("dirt", fallback=stone)
    grass = find("grass_carried", "grass", fallback=dirt)
    sand = find("sand", fallback=dirt)
    sandstone = find("sandstone", fallback=sand)
    snow = find("snow", fallback=stone)
    water = find_optional("water")
    lava = find_optional("lava")

    return BlockPalette(
        grass=grass,
        dirt=dirt,
        stone=stone,
        sand=sand,
        sandstone=sandstone,
        snow=snow,
        water=water,
        lava=lava,
    )
