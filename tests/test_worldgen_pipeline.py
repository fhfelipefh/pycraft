import time

from pycraft.worldgen import TerrainGeneratorConfig, WorldGenerator, build_block_palette
from pycraft.worldgen.surface import choose_subsurface_block, choose_surface_block
from pycraft.voxel_chunk import AtlasTile, CHUNK_SIZE, build_chunk_mesh, chunk_key_from_block, chunk_origin


def _block(name, texture):
    return {
        "name": name,
        "block_texture": texture,
        "block_texture_path": f"textures/blocks/{texture}",
    }


def make_generator(seed=1337):
    block_types = [
        _block("Grama", "grass_carried.png"),
        _block("Terra", "dirt.png"),
        _block("Pedra", "stone.png"),
        _block("Areia", "sand.png"),
        _block("Arenito", "sandstone.png"),
        _block("Neve", "snow.png"),
        _block("Agua", "water.png"),
        _block("Lava", "lava.png"),
    ]
    palette = build_block_palette(block_types)
    return WorldGenerator.from_config(
        palette=palette,
        config=TerrainGeneratorConfig(
            seed=seed,
            sea_level=0,
            lava_level=-44,
            min_y=-48,
            max_y=80,
        ),
    )


def test_terrain_sampling_is_deterministic():
    generator_a = make_generator(seed=99)
    generator_b = make_generator(seed=99)

    column_a = generator_a.terrain.sample_column(123, -77)
    column_b = generator_b.terrain.sample_column(123, -77)

    assert column_a.surface_height == column_b.surface_height
    assert column_a.biome == column_b.biome
    assert column_a.continentalness == column_b.continentalness


def test_caves_create_air_or_fluid_inside_columns():
    generator = make_generator(seed=11)

    found_empty_cell = False
    for y in range(-32, 40):
        density = generator.terrain.density_at(40, y, 40)
        if density <= 0.0:
            block = generator.get_base_block_at((40, y, 40))
            assert block is None or block["block_texture"] in {"water.png", "lava.png"}
            found_empty_cell = True
            break

    assert found_empty_cell


def test_surface_rules_map_expected_blocks():
    assert choose_surface_block("desert") == "sand"
    assert choose_surface_block("snowy_mountains") == "snow"
    assert choose_subsurface_block("beach") == "sandstone"
    assert choose_subsurface_block("plains") == "dirt"


def test_missing_fluid_assets_do_not_fallback_to_stone_blocks():
    block_types = [
        _block("Grama", "grass_carried.png"),
        _block("Terra", "dirt.png"),
        _block("Pedra", "stone.png"),
    ]

    palette = build_block_palette(block_types)

    assert palette.water is None
    assert palette.lava is None


def test_chunk_composition_contains_solid_and_fluids():
    generator = make_generator(seed=2026)
    column = generator.terrain.sample_column(0, 0)
    surface_pos = (0, column.surface_height, 0)
    surface_chunk = chunk_key_from_block(surface_pos)
    positions = set(generator.iter_base_positions_for_chunk(surface_chunk))

    assert surface_pos in positions

    surface_block = generator.get_base_block_at(surface_pos)
    below_block = generator.get_base_block_at((0, column.surface_height - 1, 0))
    deep_block = generator.get_base_block_at((0, column.surface_height - 6, 0))

    assert surface_block is not None
    assert below_block is not None
    assert deep_block is not None

    assert surface_block["block_texture"] in {"grass_carried.png", "sand.png", "snow.png"}
    assert below_block["block_texture"] in {"dirt.png", "sandstone.png", "sand.png"}
    assert deep_block["block_texture"] == "stone.png"


def test_bootstrap_surface_chunks_finish_within_thirty_seconds():
    generator = make_generator(seed=2026)
    surface_column = generator.terrain.sample_column(0, 0)
    surface_chunk = chunk_key_from_block((0, surface_column.surface_height, 0))
    candidate_chunks = [
        surface_chunk,
        (surface_chunk[0] - 1, surface_chunk[1], surface_chunk[2]),
        (surface_chunk[0] + 1, surface_chunk[1], surface_chunk[2]),
        (surface_chunk[0], surface_chunk[1], surface_chunk[2] - 1),
    ]

    atlas_tiles = {
        texture_key: AtlasTile(u0=0.0, v0=0.0, u1=1.0, v1=1.0)
        for texture_key in {
            "textures/blocks/grass_carried.png",
            "textures/blocks/dirt.png",
            "textures/blocks/stone.png",
            "textures/blocks/sand.png",
            "textures/blocks/sandstone.png",
            "textures/blocks/snow.png",
        }
    }

    started_at = time.perf_counter()
    total_faces = 0

    for chunk_key in candidate_chunks:
        origin_x, origin_y, origin_z = chunk_origin(chunk_key)
        lookup = {}
        for world_x in range(origin_x - 1, origin_x + CHUNK_SIZE + 1):
            for world_y in range(origin_y - 1, origin_y + CHUNK_SIZE + 1):
                for world_z in range(origin_z - 1, origin_z + CHUNK_SIZE + 1):
                    lookup[(world_x, world_y, world_z)] = generator.get_base_block_at((world_x, world_y, world_z))

        positions = [
            (world_x, world_y, world_z)
            for world_x in range(origin_x, origin_x + CHUNK_SIZE)
            for world_y in range(origin_y, origin_y + CHUNK_SIZE)
            for world_z in range(origin_z, origin_z + CHUNK_SIZE)
            if lookup.get((world_x, world_y, world_z)) is not None
        ]

        mesh = build_chunk_mesh(
            chunk_key=chunk_key,
            positions=positions,
            get_block_type_at=lookup.get,
            texture_key_for_block=lambda block: block["block_texture_path"],
            atlas_tiles=atlas_tiles,
        )
        total_faces += mesh.face_count

    elapsed = time.perf_counter() - started_at

    assert total_faces > 0
    assert elapsed < 30.0
