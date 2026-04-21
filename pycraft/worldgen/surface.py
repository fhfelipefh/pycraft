"""Surface block rules by biome."""

from __future__ import annotations


def choose_surface_block(biome: str) -> str:
    if biome == "desert":
        return "sand"
    if biome in {"snowy_plains", "snowy_mountains"}:
        return "snow"
    if biome == "beach":
        return "sand"
    return "grass"


def choose_subsurface_block(biome: str) -> str:
    if biome in {"desert", "beach"}:
        return "sandstone"
    return "dirt"
