from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
TEXTURES_DIR = BASE_DIR / "textures" / "blocks"
SKY_DIR = BASE_DIR / "skybox" / "generated"


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
