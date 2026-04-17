from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
MOBS_DIR = BASE_DIR / "mobs"


def test_each_mob_has_fbx_and_png_texture():
    missing = []
    for mob_dir in sorted(MOBS_DIR.iterdir()):
        if not mob_dir.is_dir():
            continue
        source = mob_dir / "source"
        textures = mob_dir / "textures"
        has_fbx = any(p.suffix.lower() == ".fbx" for p in source.glob("*") ) if source.exists() else False
        pngs = [p for p in textures.glob("*.png")]
        has_png = len(pngs) > 0
        zero_pngs = [p for p in pngs if p.stat().st_size == 0]

        if not has_fbx:
            missing.append(f"{mob_dir.name}: missing FBX in source/")
        if not has_png:
            missing.append(f"{mob_dir.name}: missing PNG in textures/")
        if zero_pngs:
            missing.append(f"{mob_dir.name}: zero-byte textures {[p.name for p in zero_pngs]}")

    assert not missing, "\n".join(missing)
