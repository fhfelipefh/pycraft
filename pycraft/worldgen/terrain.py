"""Terrain and density samplers inspired by Minecraft 1.18+ concepts."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math

from pycraft.worldgen.biome import ClimateSample, pick_biome
from pycraft.worldgen.noise import fbm_2d, fbm_3d, value_noise_2d


@dataclass(frozen=True)
class TerrainGeneratorConfig:
    seed: int = 90210
    sea_level: int = 0
    lava_level: int = -44
    min_y: int = -48
    max_y: int = 80

    continentalness_freq: float = 0.0014
    erosion_freq: float = 0.0022
    peaks_freq: float = 0.0058
    climate_freq: float = 0.0009

    detail_freq: float = 0.022
    detail_strength: float = 1.9
    macro_3d_freq: float = 0.0052
    macro_3d_strength: float = 6.4

    cave_freq: float = 0.031
    cave_threshold: float = 0.62
    cave_strength: float = 128.0


@dataclass(frozen=True)
class ColumnSample:
    continentalness: float
    erosion: float
    peaks: float
    temperature: float
    humidity: float
    biome: str
    surface_height: int


class TerrainGenerator:
    def __init__(self, config: TerrainGeneratorConfig):
        self.config = config
        self._seed_cont = config.seed + 101
        self._seed_ero = config.seed + 211
        self._seed_peak = config.seed + 307
        self._seed_temp = config.seed + 401
        self._seed_hum = config.seed + 503
        self._seed_detail = config.seed + 601
        self._seed_macro = config.seed + 701
        self._seed_cave = config.seed + 809
        self._seed_aquifer = config.seed + 907

    @lru_cache(maxsize=32768)
    def sample_column(self, x: int, z: int) -> ColumnSample:
        continentalness = fbm_2d(self._seed_cont, x, z, self.config.continentalness_freq, octaves=4)
        erosion = fbm_2d(self._seed_ero, x, z, self.config.erosion_freq, octaves=3)
        peaks = fbm_2d(self._seed_peak, x, z, self.config.peaks_freq, octaves=4)
        temperature = fbm_2d(self._seed_temp, x, z, self.config.climate_freq, octaves=2)
        humidity = fbm_2d(self._seed_hum, x, z, self.config.climate_freq, octaves=2)

        climate = ClimateSample(
            continentalness=continentalness,
            erosion=erosion,
            peaks=peaks,
            temperature=temperature,
            humidity=humidity,
        )
        biome = pick_biome(climate)
        surface_height = self._compute_surface_height(continentalness, erosion, peaks)

        return ColumnSample(
            continentalness=continentalness,
            erosion=erosion,
            peaks=peaks,
            temperature=temperature,
            humidity=humidity,
            biome=biome,
            surface_height=surface_height,
        )

    def _compute_surface_height(self, continentalness: float, erosion: float, peaks: float) -> int:
        # Curves mirror the intent of continentalness/erosion/peaks composition.
        base = self._smoothstep(-0.62, 0.72, continentalness)
        base_height = -34.0 + (base * 74.0)

        roughness = max(0.0, 1.0 - abs(erosion))
        mountain_shape = max(0.0, peaks)
        mountain_boost = (mountain_shape * mountain_shape) * (16.0 + (22.0 * roughness))

        valley_cut = max(0.0, -peaks) * (9.0 + (7.0 * roughness))

        world_height = self.config.sea_level + base_height + mountain_boost - valley_cut
        world_height = max(self.config.min_y + 3, min(self.config.max_y - 2, world_height))
        return int(round(world_height))

    @staticmethod
    def _smoothstep(edge0: float, edge1: float, value: float) -> float:
        if edge1 == edge0:
            return 0.0
        t = max(0.0, min(1.0, (value - edge0) / (edge1 - edge0)))
        return t * t * (3.0 - (2.0 * t))

    def density_at(self, x: int, y: int, z: int, column: ColumnSample | None = None) -> float:
        column_sample = column or self.sample_column(x, z)
        density = float(column_sample.surface_height - y)
        density += fbm_3d(self._seed_detail, x, y, z, self.config.detail_freq, octaves=3) * self.config.detail_strength
        density += fbm_3d(self._seed_macro, x, y, z, self.config.macro_3d_freq, octaves=2) * self.config.macro_3d_strength

        cave = fbm_3d(self._seed_cave, x, y, z, self.config.cave_freq, octaves=3)
        if cave > self.config.cave_threshold:
            density -= self.config.cave_strength

        return density

    @lru_cache(maxsize=32768)
    def water_table_at(self, x: int, z: int) -> int:
        water_bias = value_noise_2d(self._seed_aquifer, x, z, 0.004)
        # Some columns remain drier to mimic aquifer variation.
        return self.config.sea_level - 3 + int(round(water_bias * 4.0))

    def fluid_for_empty(self, x: int, y: int, z: int) -> str:
        if y <= self.config.lava_level:
            return "lava"
        if y <= self.water_table_at(x, z):
            return "water"
        return "air"
