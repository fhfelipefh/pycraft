from pathlib import Path

from PIL import Image

from pycraft.voxel_chunk import (
    build_chunk_mesh,
    build_texture_atlas,
    chunk_key_from_block,
    get_top_block_in_column,
    iter_chunk_block_positions,
    raycast_blocks,
    reverse_triangle_winding,
)


GROUND_BLOCK = {"name": "ground", "block_texture_path": "textures/blocks/ground.png"}
STONE_BLOCK = {"name": "stone", "block_texture_path": "textures/blocks/stone.png"}


def test_iter_chunk_block_positions_keeps_ground_and_custom_blocks():
    custom_blocks = {
        (1, 0, 1): STONE_BLOCK,
        (2, 1, 2): STONE_BLOCK,
    }
    positions = list(
        iter_chunk_block_positions(
            chunk_key=(0, 0, 0),
            ground_y=0,
            ground_block_type=GROUND_BLOCK,
            custom_positions=((1, 0, 1), (2, 1, 2)),
            custom_blocks=custom_blocks,
            removed_blocks={(3, 0, 3)},
        )
    )

    assert (0, 0, 0) in positions
    assert (1, 0, 1) in positions
    assert (2, 1, 2) in positions
    assert (3, 0, 3) not in positions


def test_iter_chunk_block_positions_avoids_duplicate_ground_when_custom_overrides_cell():
    custom_blocks = {
        (1, 0, 1): STONE_BLOCK,
    }
    positions = list(
        iter_chunk_block_positions(
            chunk_key=(0, 0, 0),
            ground_y=0,
            ground_block_type=GROUND_BLOCK,
            custom_positions=((1, 0, 1),),
            custom_blocks=custom_blocks,
            removed_blocks=set(),
        )
    )

    assert positions.count((1, 0, 1)) == 1


def test_chunk_meshing_culls_internal_faces_between_adjacent_blocks():
    positions = ((0, 0, 0), (1, 0, 0))
    blocks = {position: STONE_BLOCK for position in positions}
    mesh = build_chunk_mesh(
        chunk_key=(0, 0, 0),
        positions=positions,
        get_block_type_at=blocks.get,
        texture_key_for_block=lambda block: block["block_texture_path"],
        atlas_tiles={"textures/blocks/stone.png": build_dummy_tile()},
    )

    assert mesh.face_count == 10
    assert len(mesh.vertices) == 40
    assert len(mesh.triangles) == 60


def test_chunk_meshing_hides_shared_faces_across_chunk_boundaries():
    positions = ((15, 0, 0),)
    blocks = {
        (15, 0, 0): STONE_BLOCK,
        (16, 0, 0): STONE_BLOCK,
    }
    mesh = build_chunk_mesh(
        chunk_key=chunk_key_from_block((15, 0, 0)),
        positions=positions,
        get_block_type_at=blocks.get,
        texture_key_for_block=lambda block: block["block_texture_path"],
        atlas_tiles={"textures/blocks/stone.png": build_dummy_tile()},
    )

    assert mesh.face_count == 5


def test_chunk_mesh_uses_centered_xz_and_bottom_aligned_y_coordinates():
    mesh = build_chunk_mesh(
        chunk_key=(0, 0, 0),
        positions=((0, 1, 0),),
        get_block_type_at={(0, 1, 0): STONE_BLOCK}.get,
        texture_key_for_block=lambda block: block["block_texture_path"],
        atlas_tiles={"textures/blocks/stone.png": build_dummy_tile()},
    )

    xs = [vertex[0] for vertex in mesh.vertices]
    ys = [vertex[1] for vertex in mesh.vertices]
    zs = [vertex[2] for vertex in mesh.vertices]

    assert min(xs) == -0.5
    assert max(xs) == 0.5
    assert min(zs) == -0.5
    assert max(zs) == 0.5
    assert min(ys) == 0.0
    assert max(ys) == 1.0


def test_block_raycast_returns_first_hit_and_surface_normal():
    blocks = {
        (0, 0, 0): STONE_BLOCK,
        (2, 0, 0): STONE_BLOCK,
    }
    hit = raycast_blocks(
        origin=(-1.5, -0.5, 0.0),
        direction=(1.0, 0.0, 0.0),
        max_distance=8.0,
        get_block_type_at=blocks.get,
    )

    assert hit is not None
    assert hit.position == (0, 0, 0)
    assert hit.normal == (-1, 0, 0)
    assert hit.block_type is STONE_BLOCK


def test_top_block_in_column_ignores_taller_neighboring_block():
    blocks = {
        (0, 0, 0): GROUND_BLOCK,
        (1, 1, 0): STONE_BLOCK,
    }

    top = get_top_block_in_column(
        x=0.20,
        z=0.00,
        probe_from_y=3.0,
        get_block_type_at=blocks.get,
        ground_y=0,
    )

    assert top == (0, 0, 0)


def test_top_block_in_column_returns_stack_under_center():
    blocks = {
        (0, 0, 0): GROUND_BLOCK,
        (1, 1, 0): STONE_BLOCK,
    }

    top = get_top_block_in_column(
        x=0.80,
        z=0.00,
        probe_from_y=3.0,
        get_block_type_at=blocks.get,
        ground_y=0,
    )

    assert top == (1, 1, 0)


def test_block_world_point_maps_back_to_top_aligned_block_coordinates():
    import math

    point = type("Point", (), {"x": 0.49, "y": -0.001, "z": -0.49})()
    mapped = (
        math.floor(point.x + 0.5),
        math.ceil(point.y),
        math.floor(point.z + 0.5),
    )

    assert mapped == (0, 0, 0)


def test_texture_atlas_is_generated_with_uvs_for_each_texture(tmp_path: Path):
    blocks_dir = tmp_path / "textures" / "blocks"
    blocks_dir.mkdir(parents=True)
    Image.new("RGBA", (16, 16), (255, 0, 0, 255)).save(blocks_dir / "ground.png")
    Image.new("RGBA", (16, 16), (0, 255, 0, 255)).save(blocks_dir / "stone.png")

    atlas = build_texture_atlas(
        texture_paths=("textures/blocks/ground.png", "textures/blocks/stone.png"),
        asset_root=tmp_path,
        output_rel_path="textures/_generated/test_atlas.png",
    )

    assert (tmp_path / atlas.texture_path).exists()
    assert "textures/blocks/ground.png" in atlas.tiles
    assert "textures/blocks/stone.png" in atlas.tiles
    for tile in atlas.tiles.values():
        assert 0.0 <= tile.u0 < tile.u1 <= 1.0
        assert 0.0 <= tile.v0 < tile.v1 <= 1.0


def test_reverse_triangle_winding_flips_each_triangle():
    assert reverse_triangle_winding([0, 1, 2, 3, 4, 5]) == [0, 2, 1, 3, 5, 4]


def build_dummy_tile():
    from pycraft.voxel_chunk import AtlasTile

    return AtlasTile(u0=0.0, v0=0.0, u1=1.0, v1=1.0)
