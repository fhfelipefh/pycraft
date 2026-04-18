from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]

EXPECTED = {
    "minecraft-chicken": ["chicken.png"],
    "minecraft-cow": ["cow.png"],
    "minecraft-ender-dragon": ["ender_dragon.png"],
    "minecraft-iron-golem": ["iron_golem.png"],
    "minecraft-sheep": ["sheep.png", "sheep_fur.png"],
    "minecraft-snow-golem": [],  # sem assets no repo? manter flexível
    "minecraft-spider": ["spider.png"],
    "minecraft-villager": ["villager_farmer.png"],
    "minecraft-wither": ["wither.png"],
}


def test_expected_textures_present_and_non_empty():
    missing = []
    zero = []
    for mob, files in EXPECTED.items():
        textures_dir = BASE_DIR / "mobs" / mob / "textures"
        for fname in files:
            fpath = textures_dir / fname
            if not fpath.exists():
                missing.append(str(fpath.relative_to(BASE_DIR)))
            else:
                if fpath.stat().st_size == 0:
                    zero.append(str(fpath.relative_to(BASE_DIR)))
    assert not missing, f"Missing textures: {missing}"
    assert not zero, f"Zero-byte textures: {zero}"
