from pycraft.mob_grounding import (
    compute_bottom_lift_delta,
    compute_grounded_entity_y,
    compute_lift_delta,
    get_support_top_y,
)


def test_get_support_top_y_returns_highest_block_top_under_entity():
    blocks = [
        (0, 0, 0),   # top = 1
        (0, 2, 0),   # top = 3
        (3, 0, 3),
    ]
    top = get_support_top_y(blocks, x=0.1, z=-0.1, footprint=0.5)
    assert top == 3.0


def test_compute_lift_delta_raises_entity_minimally_above_support():
    # Exemplo: fundo do modelo está em y=0.4 e topo do bloco em y=1.0.
    # Precisa subir 0.61 para deixar fundo em 1.01.
    delta = compute_lift_delta(
        entity_y=0.9,
        model_min_y=-0.5,
        scale_y=1.0,
        support_top_y=1.0,
        epsilon=0.01,
    )
    assert round(delta, 2) == 0.61


def test_compute_lift_delta_no_raise_when_already_clear():
    delta = compute_lift_delta(
        entity_y=2.0,
        model_min_y=-0.5,
        scale_y=1.0,
        support_top_y=1.0,
        epsilon=0.01,
    )
    assert delta == 0.0


def test_compute_bottom_lift_delta_uses_bottom_edge():
    delta = compute_bottom_lift_delta(
        current_bottom_y=0.4,
        support_top_y=1.0,
        epsilon=0.01,
    )
    assert round(delta, 2) == 0.61


def test_compute_grounded_entity_y_places_bottom_on_support():
    grounded_y = compute_grounded_entity_y(
        model_min_y=-29,
        scale_y=0.075,
        support_top_y=1.0,
        epsilon=0.01,
    )
    assert round(grounded_y, 2) == 3.18
