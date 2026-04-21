"""Deterministic value-noise helpers for 2D/3D world generation.

This module intentionally avoids external dependencies so the generator stays
portable in constrained environments.
"""

from __future__ import annotations

import math


def _mix_u32(value: int) -> int:
    value &= 0xFFFFFFFF
    value ^= value >> 16
    value = (value * 0x7FEB352D) & 0xFFFFFFFF
    value ^= value >> 15
    value = (value * 0x846CA68B) & 0xFFFFFFFF
    value ^= value >> 16
    return value & 0xFFFFFFFF


def _hash_coords(seed: int, x: int, y: int, z: int = 0) -> float:
    mixed = _mix_u32(seed)
    mixed = _mix_u32(mixed ^ _mix_u32(x * 0x27D4EB2D))
    mixed = _mix_u32(mixed ^ _mix_u32(y * 0x165667B1))
    mixed = _mix_u32(mixed ^ _mix_u32(z * 0x1B873593))
    # Convert to [-1, 1]
    return (mixed / 0xFFFFFFFF) * 2.0 - 1.0


def _fade(t: float) -> float:
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def value_noise_2d(seed: int, x: float, z: float, frequency: float) -> float:
    sx = x * frequency
    sz = z * frequency
    ix = math.floor(sx)
    iz = math.floor(sz)
    fx = sx - ix
    fz = sz - iz

    v00 = _hash_coords(seed, ix, iz)
    v10 = _hash_coords(seed, ix + 1, iz)
    v01 = _hash_coords(seed, ix, iz + 1)
    v11 = _hash_coords(seed, ix + 1, iz + 1)

    ux = _fade(fx)
    uz = _fade(fz)

    a = _lerp(v00, v10, ux)
    b = _lerp(v01, v11, ux)
    return _lerp(a, b, uz)


def value_noise_3d(seed: int, x: float, y: float, z: float, frequency: float) -> float:
    sx = x * frequency
    sy = y * frequency
    sz = z * frequency
    ix = math.floor(sx)
    iy = math.floor(sy)
    iz = math.floor(sz)
    fx = sx - ix
    fy = sy - iy
    fz = sz - iz

    ux = _fade(fx)
    uy = _fade(fy)
    uz = _fade(fz)

    def corner(dx: int, dy: int, dz: int) -> float:
        return _hash_coords(seed, ix + dx, iy + dy, iz + dz)

    x00 = _lerp(corner(0, 0, 0), corner(1, 0, 0), ux)
    x10 = _lerp(corner(0, 1, 0), corner(1, 1, 0), ux)
    x01 = _lerp(corner(0, 0, 1), corner(1, 0, 1), ux)
    x11 = _lerp(corner(0, 1, 1), corner(1, 1, 1), ux)

    y0 = _lerp(x00, x10, uy)
    y1 = _lerp(x01, x11, uy)
    return _lerp(y0, y1, uz)


def fbm_2d(
    seed: int,
    x: float,
    z: float,
    base_frequency: float,
    octaves: int = 4,
    lacunarity: float = 2.0,
    gain: float = 0.5,
) -> float:
    amplitude = 1.0
    frequency = base_frequency
    total = 0.0
    norm = 0.0

    for octave in range(max(1, octaves)):
        total += value_noise_2d(seed + (octave * 811), x, z, frequency) * amplitude
        norm += amplitude
        amplitude *= gain
        frequency *= lacunarity

    if norm <= 1e-8:
        return 0.0
    return total / norm


def fbm_3d(
    seed: int,
    x: float,
    y: float,
    z: float,
    base_frequency: float,
    octaves: int = 4,
    lacunarity: float = 2.0,
    gain: float = 0.5,
) -> float:
    amplitude = 1.0
    frequency = base_frequency
    total = 0.0
    norm = 0.0

    for octave in range(max(1, octaves)):
        total += value_noise_3d(seed + (octave * 1319), x, y, z, frequency) * amplitude
        norm += amplitude
        amplitude *= gain
        frequency *= lacunarity

    if norm <= 1e-8:
        return 0.0
    return total / norm
