"""Helpers de posicionamento vertical para manter mobs fora dos blocos."""

from typing import Iterable, Optional, Tuple

BlockPos = Tuple[float, float, float]


def get_support_top_y(
    block_positions: Iterable[BlockPos],
    x: float,
    z: float,
    footprint: float = 0.5,
) -> Optional[float]:
    """Retorna o topo do bloco imediatamente abaixo da projeção (x, z)."""
    top = None
    for bx, by, bz in block_positions:
        if abs(bx - x) <= footprint and abs(bz - z) <= footprint:
            candidate_top = by + 1.0
            if top is None or candidate_top > top:
                top = candidate_top
    return top


def compute_lift_delta(
    entity_y: float,
    model_min_y: float,
    scale_y: float,
    support_top_y: Optional[float],
    epsilon: float = 0.01,
) -> float:
    """Calcula quanto subir no eixo Y para deixar o fundo acima do bloco de suporte."""
    if support_top_y is None:
        return 0.0

    world_bottom = entity_y + (model_min_y * scale_y)
    needed_bottom = support_top_y + epsilon
    return max(0.0, needed_bottom - world_bottom)


def compute_bottom_lift_delta(
    current_bottom_y: float,
    support_top_y: Optional[float],
    epsilon: float = 0.01,
) -> float:
    """Calcula o ajuste necessário usando diretamente a borda inferior do mob."""
    if support_top_y is None:
        return 0.0

    needed_bottom = support_top_y + epsilon
    return max(0.0, needed_bottom - current_bottom_y)


def compute_grounded_entity_y(
    model_min_y: float,
    scale_y: float,
    support_top_y: Optional[float],
    epsilon: float = 0.01,
) -> Optional[float]:
    """Retorna o Y do pivot para que a borda inferior fique apoiada no bloco."""
    if support_top_y is None:
        return None
    return support_top_y + epsilon - (model_min_y * scale_y)
