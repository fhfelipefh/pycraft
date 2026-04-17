from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
TEXTURES_DIR = BASE_DIR / "textures" / "blocks"
SKY_DIR = BASE_DIR / "skybox" / "generated"
SOUNDS_DIR = BASE_DIR / "sounds"
CHICKEN_MODEL = BASE_DIR / "mobs" / "minecraft-chicken" / "source" / "chicken.fbx"
CHICKEN_TEXTURE = BASE_DIR / "mobs" / "minecraft-chicken" / "textures" / "chicken.png"


def test_block_textures_exist():
    expected = [
        "grass_carried.png",
        "planks_birch.png",
        "stone.png",
        "dirt.png",
    ]
    missing = [name for name in expected if not (TEXTURES_DIR / name).exists()]
    assert not missing, f"Missing block textures: {missing}"


def test_sky_textures_exist():
    expected = [
        "sky_base.png",
        "sky_clouds.png",
    ]
    missing = [name for name in expected if not (SKY_DIR / name).exists()]
    assert not missing, f"Missing sky textures: {missing}"


def test_no_zero_byte_textures():
    texture_files = list(TEXTURES_DIR.glob("*.png")) + list(SKY_DIR.glob("*.png"))
    zero_sized = [str(path.relative_to(BASE_DIR)) for path in texture_files if path.stat().st_size == 0]
    assert not zero_sized, f"Zero-byte texture files: {zero_sized}"


def test_chicken_assets_exist():
    missing = [
        str(path.relative_to(BASE_DIR))
        for path in [CHICKEN_MODEL, CHICKEN_TEXTURE]
        if not path.exists()
    ]
    assert not missing, f"Missing chicken assets: {missing}"


def test_stone_hit_sound_exists():
    stone_hit_sound = SOUNDS_DIR / "Stone_mining1.ogg"
    assert stone_hit_sound.exists(), "Missing stone hit sound: sounds/Stone_mining1.ogg"
