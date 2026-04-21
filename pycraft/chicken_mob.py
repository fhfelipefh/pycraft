"""Runtime wrapper for articulated chicken mobs."""

from __future__ import annotations

from dataclasses import dataclass
import math
import random
from typing import Any, Callable

from ursina import Entity, Vec3, scene, time

from pycraft.chicken_animation import (
    CHICKEN_HEAD_PIVOT,
    CHICKEN_MODEL_MAX_Y,
    CHICKEN_MODEL_MIN_Y,
    CHICKEN_PART_MODEL_PATHS,
    CHICKEN_PART_PIVOTS,
    CHICKEN_REFERENCE_SCALE,
    CHICKEN_VISUAL_ROTATION_X,
    ChickenWalkAnimation,
    apply_chicken_pose,
    block_type_is_scratchable,
    get_part_visual_offset,
)
from pycraft.mob_textures import apply_texture_recursively


@dataclass(frozen=True)
class ChickenMobConfig:
    position: tuple[float, float, float] = (4.0, 0.53, 4.0)
    rotation_y: float = 180.0
    walk_speed: float = 0.9
    walk_radius: float = 6.0
    reach_distance: float = 0.35
    player_radius: float = 0.75
    footprint: float = 0.42
    texture_path: str = "mobs/minecraft-chicken/textures/chicken.png"


class ChickenMob:
    def __init__(
        self,
        *,
        config: ChickenMobConfig,
        resolve_existing_asset_or_fallback: Callable[[list[str]], str],
        load_texture_or_fallback: Callable[..., Any],
        apply_mob_gravity: Callable[..., Any],
        move_entity_with_grounding: Callable[..., tuple[bool, Any]],
        lift_entity_out_of_blocks: Callable[..., bool],
        get_top_solid_block_at_position: Callable[..., Any],
        get_block_type_at: Callable[[tuple[int, int, int]], Any],
        scene_root: Any = scene,
        time_source: Any = time,
        rng: random.Random | None = None,
    ) -> None:
        self.config = config
        self.resolve_existing_asset_or_fallback = resolve_existing_asset_or_fallback
        self.load_texture_or_fallback = load_texture_or_fallback
        self.apply_mob_gravity = apply_mob_gravity
        self.move_entity_with_grounding = move_entity_with_grounding
        self.lift_entity_out_of_blocks = lift_entity_out_of_blocks
        self.get_top_solid_block_at_position = get_top_solid_block_at_position
        self.get_block_type_at = get_block_type_at
        self.scene_root = scene_root
        self.time_source = time_source
        self.rng = rng or random.Random()

        self.texture_obj = self.load_texture_or_fallback(config.texture_path)
        self.entity = self._create_entity()
        self.animation = ChickenWalkAnimation(rng=self.rng)
        self.spawn_position = Vec3(self.entity.x, self.entity.y, self.entity.z)
        self.walk_target: Vec3 | None = None

    def _create_entity(self) -> Entity:
        chicken_root = Entity(
            parent=self.scene_root,
            position=Vec3(*self.config.position),
            scale=CHICKEN_REFERENCE_SCALE,
            rotation_y=self.config.rotation_y,
            unlit=True,
        )
        chicken_root.model_min_y_override = CHICKEN_MODEL_MIN_Y
        chicken_root.model_max_y_override = CHICKEN_MODEL_MAX_Y
        chicken_root.animation_nodes = {}

        chicken_visual_root = Entity(
            parent=chicken_root,
            rotation_x=CHICKEN_VISUAL_ROTATION_X,
            unlit=True,
        )
        head_pivot_entity = Entity(
            parent=chicken_visual_root,
            position=Vec3(*CHICKEN_HEAD_PIVOT),
            unlit=True,
        )
        chicken_root.animation_nodes["head"] = head_pivot_entity

        for part_name, relative_model_path in CHICKEN_PART_MODEL_PATHS.items():
            pivot = CHICKEN_PART_PIVOTS.get(part_name)
            parent_entity = chicken_visual_root
            visual_position = Vec3(0, 0, 0)

            if part_name in {"head", "beak", "wattle"}:
                parent_entity = head_pivot_entity
                visual_position = Vec3(*get_part_visual_offset(part_name, CHICKEN_HEAD_PIVOT))

            if pivot is not None:
                pivot_entity = Entity(
                    parent=chicken_visual_root,
                    position=Vec3(*pivot),
                    unlit=True,
                )
                chicken_root.animation_nodes[part_name] = pivot_entity
                parent_entity = pivot_entity
                visual_position = Vec3(*get_part_visual_offset(part_name))

            Entity(
                parent=parent_entity,
                model=self.resolve_existing_asset_or_fallback([relative_model_path]),
                texture=self.texture_obj,
                position=visual_position,
                unlit=True,
            )

        apply_texture_recursively(chicken_root, self.texture_obj)
        chicken_root.setTwoSided(True)
        chicken_root.collider = "box"
        return chicken_root

    def _get_new_walk_target(self) -> Vec3:
        offset_x = self.rng.uniform(-self.config.walk_radius, self.config.walk_radius)
        offset_z = self.rng.uniform(-self.config.walk_radius, self.config.walk_radius)
        return Vec3(
            self.spawn_position.x + offset_x,
            self.spawn_position.y,
            self.spawn_position.z + offset_z,
        )

    def _get_support_block_type(self) -> Any:
        support_position = self.get_top_solid_block_at_position(
            self.entity.x,
            self.entity.z,
            probe_from_y=max(self.entity.y + 6.0, self.spawn_position.y + 8.0),
            footprint=self.config.footprint,
        )
        if support_position is None:
            return None
        return self.get_block_type_at(support_position)

    def _is_falling(self, grounded_y: float | None, tolerance: float = 0.02) -> bool:
        if grounded_y is None:
            return True
        return self.entity.y > (grounded_y + tolerance)

    def _sync_pose(
        self,
        is_moving: bool,
        *,
        is_falling: bool = False,
        allow_random_wings: bool = True,
        on_scratchable_ground: bool = False,
    ) -> None:
        pose = self.animation.update(
            is_moving=is_moving,
            dt=self.time_source.dt,
            is_falling=is_falling,
            allow_random_wings=allow_random_wings,
            on_scratchable_ground=on_scratchable_ground,
        )
        apply_chicken_pose(self.entity.animation_nodes, pose)

    def pause(self) -> None:
        apply_chicken_pose(self.entity.animation_nodes, self.animation.stop())

    def update(self) -> None:
        grounded_y = self.apply_mob_gravity(
            self.entity,
            fallback_position=self.spawn_position,
            footprint=self.config.footprint,
        )
        falling = self._is_falling(grounded_y)
        scratchable_ground = block_type_is_scratchable(self._get_support_block_type())

        if self.walk_target is None:
            self._sync_pose(False, is_falling=falling)
            self.walk_target = self._get_new_walk_target()
            return

        to_target = Vec3(
            self.walk_target.x - self.entity.x,
            0,
            self.walk_target.z - self.entity.z,
        )
        distance_to_target = to_target.length()
        if distance_to_target <= self.config.reach_distance:
            self._sync_pose(False, is_falling=falling)
            self.walk_target = self._get_new_walk_target()
            return

        direction = to_target.normalized()
        self._sync_pose(
            True,
            is_falling=falling,
            on_scratchable_ground=scratchable_ground,
        )
        if self.animation.blocks_locomotion:
            if direction.length() > 0:
                self.entity.rotation_y = math.degrees(math.atan2(direction.x, direction.z))

            if self.animation.backward_speed > 0.0:
                backward_direction = direction * -1.0
                backward_distance = self.animation.backward_speed * self.time_source.dt
                moved, grounded_y = self.move_entity_with_grounding(
                    self.entity,
                    self.entity.x + (backward_direction.x * backward_distance),
                    self.entity.z + (backward_direction.z * backward_distance),
                    fallback_position=self.spawn_position,
                    player_radius=self.config.player_radius,
                    footprint=self.config.footprint,
                )
                if moved and grounded_y is not None:
                    falling = self._is_falling(grounded_y)
            self.lift_entity_out_of_blocks(self.entity)
            return

        step_distance = self.config.walk_speed * self.time_source.dt
        moved, grounded_y = self.move_entity_with_grounding(
            self.entity,
            self.entity.x + (direction.x * step_distance),
            self.entity.z + (direction.z * step_distance),
            fallback_position=self.spawn_position,
            player_radius=self.config.player_radius,
            footprint=self.config.footprint,
        )
        if not moved:
            moved, grounded_y = self.move_entity_with_grounding(
                self.entity,
                self.entity.x + (direction.x * step_distance),
                self.entity.z,
                fallback_position=self.spawn_position,
                player_radius=self.config.player_radius,
                footprint=self.config.footprint,
            )
        if not moved:
            moved, grounded_y = self.move_entity_with_grounding(
                self.entity,
                self.entity.x,
                self.entity.z + (direction.z * step_distance),
                fallback_position=self.spawn_position,
                player_radius=self.config.player_radius,
                footprint=self.config.footprint,
            )
        falling = self._is_falling(grounded_y)
        if not moved:
            self._sync_pose(False, is_falling=falling)
            self.walk_target = self._get_new_walk_target()
            return

        if direction.length() > 0:
            self.entity.rotation_y = math.degrees(math.atan2(direction.x, direction.z))
        self.lift_entity_out_of_blocks(self.entity)
