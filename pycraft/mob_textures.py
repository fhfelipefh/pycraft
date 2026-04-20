"""
Utilitários relacionados a aplicação de texturas nos modelos dos mobs.

Este módulo é deliberadamente independente do Ursina para permitir testes
unitários sem abrir janela gráfica. Ele espera apenas que os objetos
recebam atributos/Chamadas compatíveis: `.texture`, `.children` iterável e
`.setTwoSided(True)` opcional.
"""

from typing import Any


def apply_texture_recursively(entity: Any, texture_obj: Any) -> None:
    """Força a aplicação da textura no entity e em todos os seus filhos.

    - Define `entity.texture` quando possível
    - Tenta marcar faces duplas via `setTwoSided(True)` quando disponível
    - Propaga recursivamente para `entity.children`
    """
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
