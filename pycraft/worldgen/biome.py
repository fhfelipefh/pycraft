"""Biome classification based on simplified multi-noise parameters."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClimateSample:
    continentalness: float
    erosion: float
    peaks: float
    temperature: float
    humidity: float


def pick_biome(sample: ClimateSample) -> str:
    if sample.continentalness < -0.32:
        return "ocean"
    if sample.continentalness < -0.16:
        return "beach"

    if sample.temperature > 0.35 and sample.humidity < -0.1:
        return "desert"

    if sample.temperature < -0.25 and sample.peaks > 0.22:
        return "snowy_mountains"

    if sample.peaks > 0.45 and sample.erosion < -0.2:
        return "mountains"

    if sample.humidity > 0.35 and sample.temperature > 0.05:
        return "forest"

    if sample.temperature < -0.3:
        return "snowy_plains"

    return "plains"
