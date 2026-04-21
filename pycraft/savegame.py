"""Local save/load helpers for PyCraft game state."""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, Mapping, Tuple

GridPos = Tuple[int, int, int]


def _encode_position(position: GridPos) -> list[int]:
    return [int(position[0]), int(position[1]), int(position[2])]


def _decode_position(raw: Any) -> GridPos:
    if not isinstance(raw, (list, tuple)) or len(raw) != 3:
        raise ValueError("Invalid grid position payload")
    return (int(raw[0]), int(raw[1]), int(raw[2]))


def serialize_game_state(
    *,
    player_position: Tuple[float, float, float],
    hotbar_block_indices: Iterable[int],
    selected_hotbar_slot: int,
    custom_blocks: Mapping[GridPos, Any],
    removed_blocks: Iterable[GridPos],
    block_key_for_type: Callable[[Any], str],
    world_seed: int,
) -> Dict[str, Any]:
    custom_payload = []
    for position, block_type in custom_blocks.items():
        custom_payload.append(
            {
                "position": _encode_position(position),
                "block": block_key_for_type(block_type),
            }
        )

    removed_payload = [_encode_position(position) for position in removed_blocks]

    return {
        "schema_version": 1,
        "world_seed": int(world_seed),
        "player": {
            "position": [
                float(player_position[0]),
                float(player_position[1]),
                float(player_position[2]),
            ]
        },
        "hotbar": {
            "selected_slot": int(selected_hotbar_slot),
            "block_indices": [int(index) for index in hotbar_block_indices],
        },
        "world": {
            "custom_blocks": custom_payload,
            "removed_blocks": removed_payload,
        },
    }


def deserialize_game_state(payload: Mapping[str, Any]) -> Dict[str, Any]:
    player_data = payload.get("player") or {}
    player_pos_raw = player_data.get("position") or [0, 0, 0]
    if not isinstance(player_pos_raw, (list, tuple)) or len(player_pos_raw) != 3:
        raise ValueError("Invalid player position in save")

    hotbar_data = payload.get("hotbar") or {}
    world_data = payload.get("world") or {}

    custom_blocks_payload = []
    for item in world_data.get("custom_blocks", []):
        if not isinstance(item, Mapping):
            continue
        position = _decode_position(item.get("position"))
        block_key = str(item.get("block", "")).strip()
        if not block_key:
            continue
        custom_blocks_payload.append((position, block_key))

    removed_positions = []
    for raw_pos in world_data.get("removed_blocks", []):
        removed_positions.append(_decode_position(raw_pos))

    return {
        "schema_version": int(payload.get("schema_version", 0)),
        "world_seed": int(payload.get("world_seed", 0)),
        "player_position": (
            float(player_pos_raw[0]),
            float(player_pos_raw[1]),
            float(player_pos_raw[2]),
        ),
        "selected_hotbar_slot": int(hotbar_data.get("selected_slot", 0)),
        "hotbar_block_indices": [int(index) for index in hotbar_data.get("block_indices", [])],
        "custom_blocks": custom_blocks_payload,
        "removed_blocks": removed_positions,
    }
