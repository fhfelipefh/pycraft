"""Helpers for the articulated chicken walk animation.

This module stays independent from Ursina/Panda3D so the animation rules can
be unit-tested without booting the engine.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import random
from typing import Mapping, Protocol


CHICKEN_PART_MODEL_PATHS = {
    "body": "mobs/minecraft-chicken/parts/body.obj",
    "head": "mobs/minecraft-chicken/parts/head.obj",
    "beak": "mobs/minecraft-chicken/parts/beak.obj",
    "wattle": "mobs/minecraft-chicken/parts/wattle.obj",
    "left_wing": "mobs/minecraft-chicken/parts/left_wing.obj",
    "right_wing": "mobs/minecraft-chicken/parts/right_wing.obj",
    "left_leg": "mobs/minecraft-chicken/parts/left_leg.obj",
    "right_leg": "mobs/minecraft-chicken/parts/right_leg.obj",
}

# Pivots were derived from the original `chicken.fbx` by separating the mesh
# into loose parts and keeping the original local coordinates.
CHICKEN_PART_PIVOTS = {
    "left_wing": (-3.0, 4.0, -1.0),
    "right_wing": (3.0, 4.0, -1.0),
    "left_leg": (-1.5, 7.0, 5.5),
    "right_leg": (1.5, 7.0, 5.5),
}

CHICKEN_HEAD_PIVOT = (0.0, 7.0, -4.0)
CHICKEN_MODEL_MAX_Y = 7.0
CHICKEN_REFERENCE_SCALE = 0.07
CHICKEN_VISUAL_ROTATION_X = 90.0
CHICKEN_SCRATCHABLE_MATERIALS = frozenset({"grass", "dirt"})
CHICKEN_LEG_SAFE_PITCH_RANGE = (-40.0, 24.0)
CHICKEN_FOOT_CLEARANCE = 0.25

# Left leg vertices after translating the OBJ so the pivot sits at the origin.
# The parent visual root still applies the global +90 X rotation afterwards.
CHICKEN_LEG_LOCAL_VERTICES = (
    (0.5, -3.0, 2.5),
    (0.5, -3.0, -2.5),
    (-0.5, -3.0, 2.5),
    (0.5, -1.0, 2.5),
    (1.5, -3.0, 2.5),
    (1.5, -1.0, 2.5),
    (-0.5, -1.0, 2.5),
    (0.5, 0.0, 2.5),
    (-0.5, 0.0, 2.5),
    (-1.5, -1.0, 2.5),
    (-1.5, -3.0, 2.5),
    (-0.5, -3.0, -2.5),
)
CHICKEN_LEG_ROOT_Y_OFFSET = -CHICKEN_PART_PIVOTS["left_leg"][2]


@dataclass(frozen=True)
class ChickenPose:
    left_leg_pitch: float = 0.0
    right_leg_pitch: float = 0.0
    left_wing_roll: float = 0.0
    right_wing_roll: float = 0.0
    head_pitch: float = 0.0


NEUTRAL_CHICKEN_POSE = ChickenPose()


class SupportsChickenPose(Protocol):
    rotation_x: float
    rotation_z: float


def get_leg_root_min_y_for_pitch(pitch_degrees: float) -> float:
    radians = math.radians(float(pitch_degrees))
    sin_angle = math.sin(radians)
    cos_angle = math.cos(radians)
    relative_root_min_y = min(
        -((vertex_y * sin_angle) + (vertex_z * cos_angle))
        for _, vertex_y, vertex_z in CHICKEN_LEG_LOCAL_VERTICES
    )
    return CHICKEN_LEG_ROOT_Y_OFFSET + relative_root_min_y


def compute_chicken_model_min_y(
    safe_pitch_range: tuple[float, float] = CHICKEN_LEG_SAFE_PITCH_RANGE,
    foot_clearance: float = CHICKEN_FOOT_CLEARANCE,
    step_degrees: float = 0.25,
) -> float:
    start, end = safe_pitch_range
    current = float(start)
    sampled_angles = []
    while current <= end:
        sampled_angles.append(current)
        current += step_degrees
    sampled_angles.append(float(end))
    worst_leg_min_y = min(get_leg_root_min_y_for_pitch(angle) for angle in sampled_angles)
    return worst_leg_min_y - float(foot_clearance)


CHICKEN_MODEL_MIN_Y = compute_chicken_model_min_y()


class ChickenWalkAnimation:
    def __init__(
        self,
        leg_angle: float = 24.0,
        wing_angle: float = 11.0,
        cycle_speed: float = 8.5,
        fall_wing_angle: float = 18.0,
        random_flap_interval: tuple[float, float] = (1.4, 3.4),
        random_flap_duration: tuple[float, float] = (0.16, 0.32),
        random_wing_cycle_speed: float = 17.0,
        fall_wing_cycle_speed: float = 19.5,
        ground_action_interval: tuple[float, float] = (3.6, 7.2),
        scratch_duration: float = 0.42,
        step_back_duration: float = 0.2,
        peck_duration: float = 0.52,
        step_back_speed: float = 0.58,
        rng: random.Random | None = None,
    ) -> None:
        self.leg_angle = float(leg_angle)
        self.wing_angle = float(wing_angle)
        self.cycle_speed = float(cycle_speed)
        self.fall_wing_angle = float(fall_wing_angle)
        self.random_flap_interval = random_flap_interval
        self.random_flap_duration = random_flap_duration
        self.random_wing_cycle_speed = float(random_wing_cycle_speed)
        self.fall_wing_cycle_speed = float(fall_wing_cycle_speed)
        self.ground_action_interval = ground_action_interval
        self.scratch_duration = float(scratch_duration)
        self.step_back_duration = float(step_back_duration)
        self.peck_duration = float(peck_duration)
        self.step_back_speed = float(step_back_speed)
        self.rng = rng or random.Random()
        self.phase = 0.0
        self.wing_phase = 0.0
        self.random_flap_time_remaining = 0.0
        self.time_until_next_random_flap = self._roll_random_interval()
        self.current_action: str | None = None
        self.current_action_elapsed = 0.0
        self.current_action_leg = "left_leg"
        self.blocks_locomotion = False
        self.backward_speed = 0.0
        self.time_until_next_ground_action = self._roll_ground_action_interval()
        self.pose = NEUTRAL_CHICKEN_POSE

    def _roll_random_interval(self) -> float:
        start, end = self.random_flap_interval
        return float(self.rng.uniform(start, end))

    def _roll_random_duration(self) -> float:
        start, end = self.random_flap_duration
        return float(self.rng.uniform(start, end))

    def _roll_ground_action_interval(self) -> float:
        start, end = self.ground_action_interval
        return float(self.rng.uniform(start, end))

    def _clear_wings(self) -> None:
        self.wing_phase = 0.0
        self.random_flap_time_remaining = 0.0
        self.time_until_next_random_flap = self._roll_random_interval()

    def _clear_ground_action(self) -> None:
        self.current_action = None
        self.current_action_elapsed = 0.0
        self.blocks_locomotion = False
        self.backward_speed = 0.0
        self.time_until_next_ground_action = self._roll_ground_action_interval()

    def _start_ground_action(self) -> None:
        self.current_action = "scratch"
        self.current_action_elapsed = 0.0
        self.current_action_leg = "left_leg" if self.rng.random() < 0.5 else "right_leg"
        self.blocks_locomotion = True
        self.backward_speed = 0.0
        self.phase = 0.0
        self._clear_wings()

    def _advance_ground_action(self, dt: float) -> None:
        if self.current_action is None:
            return

        self.current_action_elapsed += dt
        if self.current_action == "scratch" and self.current_action_elapsed >= self.scratch_duration:
            self.current_action = "step_back"
            self.current_action_elapsed = 0.0
            return
        if self.current_action == "step_back" and self.current_action_elapsed >= self.step_back_duration:
            self.current_action = "peck"
            self.current_action_elapsed = 0.0
            return
        if self.current_action == "peck" and self.current_action_elapsed >= self.peck_duration:
            self._clear_ground_action()

    def _build_ground_action_pose(self) -> ChickenPose:
        support_leg = "right_leg" if self.current_action_leg == "left_leg" else "left_leg"

        if self.current_action == "scratch":
            phase = (self.current_action_elapsed / max(self.scratch_duration, 1e-6)) * math.tau * 2.5
            scratch_pitch = -10.0 + (math.sin(phase) * 30.0)
            support_pitch = 7.0 + (math.sin(phase + math.pi) * 4.0)
            pose = {
                self.current_action_leg: scratch_pitch,
                support_leg: support_pitch,
            }
            return ChickenPose(
                left_leg_pitch=pose.get("left_leg", 0.0),
                right_leg_pitch=pose.get("right_leg", 0.0),
                head_pitch=10.0,
            )

        if self.current_action == "step_back":
            progress = min(1.0, self.current_action_elapsed / max(self.step_back_duration, 1e-6))
            settle = math.sin(progress * math.pi)
            self.backward_speed = self.step_back_speed
            return ChickenPose(
                left_leg_pitch=-8.0 + (settle * 5.0),
                right_leg_pitch=6.0 - (settle * 4.0),
                head_pitch=12.0 + (settle * 5.0),
            )

        peck_wave = max(
            0.0,
            math.sin((self.current_action_elapsed / max(self.peck_duration, 1e-6)) * math.tau * 2.0),
        )
        return ChickenPose(
            left_leg_pitch=3.0,
            right_leg_pitch=-3.0,
            head_pitch=34.0 * peck_wave,
        )

    def stop(self) -> ChickenPose:
        self.phase = 0.0
        self._clear_wings()
        self._clear_ground_action()
        self.pose = NEUTRAL_CHICKEN_POSE
        return self.pose

    def update(
        self,
        *,
        is_moving: bool,
        dt: float,
        speed_ratio: float = 1.0,
        is_falling: bool = False,
        allow_random_wings: bool = True,
        on_scratchable_ground: bool = False,
    ) -> ChickenPose:
        clamped_dt = max(0.0, float(dt))
        clamped_speed = max(0.6, min(1.8, float(speed_ratio)))
        self.blocks_locomotion = False
        self.backward_speed = 0.0

        if is_falling and self.current_action is not None:
            self._clear_ground_action()

        if self.current_action is None:
            if is_moving and on_scratchable_ground and not is_falling and clamped_dt > 0.0:
                self.time_until_next_ground_action = max(0.0, self.time_until_next_ground_action - clamped_dt)
                if self.time_until_next_ground_action <= 0.0:
                    self._start_ground_action()
            elif not on_scratchable_ground:
                self.time_until_next_ground_action = self._roll_ground_action_interval()

        if self.current_action is not None:
            self.blocks_locomotion = True
            self.pose = self._build_ground_action_pose()
            self._advance_ground_action(clamped_dt)
            return self.pose

        if is_moving and clamped_dt > 0.0:
            self.phase = (self.phase + (clamped_dt * self.cycle_speed * clamped_speed)) % math.tau
            leg_pitch = math.sin(self.phase) * self.leg_angle
        else:
            self.phase = 0.0
            leg_pitch = 0.0

        wing_roll = 0.0
        if is_falling and clamped_dt > 0.0:
            self.wing_phase = (self.wing_phase + (clamped_dt * self.fall_wing_cycle_speed)) % math.tau
            wing_roll = math.sin(self.wing_phase) * self.fall_wing_angle
        elif allow_random_wings and clamped_dt > 0.0:
            if self.random_flap_time_remaining > 0.0:
                self.wing_phase = (self.wing_phase + (clamped_dt * self.random_wing_cycle_speed)) % math.tau
                wing_roll = math.sin(self.wing_phase) * self.wing_angle
                self.random_flap_time_remaining = max(0.0, self.random_flap_time_remaining - clamped_dt)
                if self.random_flap_time_remaining <= 0.0:
                    self._clear_wings()
                    wing_roll = 0.0
            else:
                self.time_until_next_random_flap = max(0.0, self.time_until_next_random_flap - clamped_dt)
                if self.time_until_next_random_flap <= 0.0:
                    self.random_flap_time_remaining = self._roll_random_duration()
                    self.wing_phase = (clamped_dt * self.random_wing_cycle_speed) % math.tau
                    wing_roll = math.sin(self.wing_phase) * self.wing_angle
                    self.random_flap_time_remaining = max(0.0, self.random_flap_time_remaining - clamped_dt)
                    if self.random_flap_time_remaining <= 0.0:
                        self._clear_wings()
                        wing_roll = 0.0
        else:
            self._clear_wings()

        self.pose = ChickenPose(
            left_leg_pitch=leg_pitch,
            right_leg_pitch=-leg_pitch,
            left_wing_roll=-wing_roll,
            right_wing_roll=wing_roll,
        )
        return self.pose


def get_part_visual_offset(part_name: str, pivot: tuple[float, float, float] | None = None) -> tuple[float, float, float]:
    if pivot is None:
        pivot = CHICKEN_PART_PIVOTS.get(part_name)
    if pivot is None:
        return (0.0, 0.0, 0.0)
    return (-pivot[0], -pivot[1], -pivot[2])


def block_type_is_scratchable(block_type: object) -> bool:
    if not isinstance(block_type, dict):
        return False
    return str(block_type.get("material", "")).lower() in CHICKEN_SCRATCHABLE_MATERIALS


def apply_chicken_pose(parts: Mapping[str, SupportsChickenPose], pose: ChickenPose) -> None:
    left_leg = parts.get("left_leg")
    if left_leg is not None:
        left_leg.rotation_x = pose.left_leg_pitch

    right_leg = parts.get("right_leg")
    if right_leg is not None:
        right_leg.rotation_x = pose.right_leg_pitch

    left_wing = parts.get("left_wing")
    if left_wing is not None:
        left_wing.rotation_z = pose.left_wing_roll

    right_wing = parts.get("right_wing")
    if right_wing is not None:
        right_wing.rotation_z = pose.right_wing_roll

    head = parts.get("head")
    if head is not None:
        head.rotation_x = pose.head_pitch
