"""Exporta a galinha articulada a partir do FBX original.

Uso:
    blender -b --python scripts/export_chicken_parts.py
"""

from __future__ import annotations

from pathlib import Path

import bpy


BASE_DIR = Path(__file__).resolve().parents[1]
SOURCE_FBX = BASE_DIR / "mobs" / "minecraft-chicken" / "source" / "chicken.fbx"
OUTPUT_DIR = BASE_DIR / "mobs" / "minecraft-chicken" / "parts"

PART_NAME_MAP = {
    "Chicken": "body.obj",
    "Chicken.004": "head.obj",
    "Chicken.003": "beak.obj",
    "Chicken.002": "wattle.obj",
    "Chicken.005": "left_wing.obj",
    "Chicken.001": "right_wing.obj",
    "Chicken.006": "left_leg.obj",
    "Chicken.007": "right_leg.obj",
}


def main() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(SOURCE_FBX))

    chicken = bpy.data.objects["Chicken"]
    bpy.context.view_layer.objects.active = chicken
    chicken.select_set(True)
    bpy.ops.mesh.separate(type="LOOSE")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for source_name, output_name in PART_NAME_MAP.items():
        part = bpy.data.objects[source_name]
        part.location = (0.0, 0.0, 0.0)
        part.rotation_euler = (0.0, 0.0, 0.0)
        part.scale = (1.0, 1.0, 1.0)

        for obj in bpy.data.objects:
            obj.select_set(False)

        bpy.context.view_layer.objects.active = part
        part.select_set(True)
        bpy.ops.wm.obj_export(
            filepath=str(OUTPUT_DIR / output_name),
            export_selected_objects=True,
            export_uv=True,
            export_normals=True,
            export_materials=False,
        )


if __name__ == "__main__":
    main()
