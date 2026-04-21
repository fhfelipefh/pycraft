from pycraft.savegame import deserialize_game_state, serialize_game_state


STONE = {"block_texture_path": "textures/blocks/stone.png"}
DIRT = {"block_texture_path": "textures/blocks/dirt.png"}


def _block_key(block_type):
    return block_type["block_texture_path"]


def test_serialize_game_state_contains_player_hotbar_and_world_changes():
    payload = serialize_game_state(
        player_position=(10.5, 42.0, -3.25),
        hotbar_block_indices=[0, 1, 2, 3, 4, 5, 6, 7, 8],
        selected_hotbar_slot=4,
        custom_blocks={(1, 2, 3): STONE, (9, -5, 0): DIRT},
        removed_blocks={(0, 0, 0), (1, 0, 1)},
        block_key_for_type=_block_key,
        world_seed=90210,
    )

    assert payload["schema_version"] == 1
    assert payload["world_seed"] == 90210
    assert payload["player"]["position"] == [10.5, 42.0, -3.25]
    assert payload["hotbar"]["selected_slot"] == 4
    assert payload["hotbar"]["block_indices"] == [0, 1, 2, 3, 4, 5, 6, 7, 8]
    assert len(payload["world"]["custom_blocks"]) == 2
    assert len(payload["world"]["removed_blocks"]) == 2


def test_deserialize_game_state_recovers_core_fields():
    payload = {
        "schema_version": 1,
        "world_seed": 123,
        "player": {"position": [1.0, 2.5, -8.0]},
        "hotbar": {
            "selected_slot": 2,
            "block_indices": [8, 7, 6, 5, 4, 3, 2, 1, 0],
        },
        "world": {
            "custom_blocks": [
                {"position": [1, 2, 3], "block": "textures/blocks/stone.png"},
                {"position": [4, 5, 6], "block": "textures/blocks/dirt.png"},
            ],
            "removed_blocks": [[0, 0, 0], [1, 0, 1]],
        },
    }

    state = deserialize_game_state(payload)

    assert state["schema_version"] == 1
    assert state["world_seed"] == 123
    assert state["player_position"] == (1.0, 2.5, -8.0)
    assert state["selected_hotbar_slot"] == 2
    assert state["hotbar_block_indices"] == [8, 7, 6, 5, 4, 3, 2, 1, 0]
    assert ((1, 2, 3), "textures/blocks/stone.png") in state["custom_blocks"]
    assert (0, 0, 0) in state["removed_blocks"]
