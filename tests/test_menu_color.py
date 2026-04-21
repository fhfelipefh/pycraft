import pytest


pytest.importorskip("ursina")

from pycraft.menu import rgba255


def test_rgba255_normalizes_rgb_and_alpha_channels():
    color_value = rgba255(10, 16, 24, 255)

    assert round(float(color_value[0]), 6) == round(10.0 / 255.0, 6)
    assert round(float(color_value[1]), 6) == round(16.0 / 255.0, 6)
    assert round(float(color_value[2]), 6) == round(24.0 / 255.0, 6)
    assert round(float(color_value[3]), 6) == 1.0
