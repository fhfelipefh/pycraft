from pathlib import Path

from pycraft.chicken_animation import (
    CHICKEN_MODEL_MAX_Y,
    CHICKEN_MODEL_MIN_Y,
    CHICKEN_PART_MODEL_PATHS,
    CHICKEN_HEAD_PIVOT,
    CHICKEN_FOOT_CLEARANCE,
    CHICKEN_VISUAL_ROTATION_X,
    ChickenPose,
    ChickenWalkAnimation,
    NEUTRAL_CHICKEN_POSE,
    apply_chicken_pose,
    block_type_is_scratchable,
    compute_chicken_model_min_y,
    get_part_visual_offset,
    get_leg_root_min_y_for_pitch,
)


BASE_DIR = Path(__file__).resolve().parents[1]


class Node:
    def __init__(self, rotation_x: float = 0.0, rotation_z: float = 0.0):
        self.rotation_x = rotation_x
        self.rotation_z = rotation_z


def test_exported_chicken_part_assets_exist():
    missing = [
        relative_path
        for relative_path in CHICKEN_PART_MODEL_PATHS.values()
        if not (BASE_DIR / relative_path).exists()
    ]
    assert not missing, f"Missing articulated chicken part assets: {missing}"


def test_walk_animation_keeps_neutral_pose_while_stopped():
    animation = ChickenWalkAnimation(random_flap_interval=(10.0, 10.0))
    moving_pose = animation.update(is_moving=True, dt=0.125)
    assert moving_pose != NEUTRAL_CHICKEN_POSE

    stopped_pose = animation.update(is_moving=False, dt=0.125, allow_random_wings=False)

    assert stopped_pose == NEUTRAL_CHICKEN_POSE
    assert animation.phase == 0.0


def test_walk_animation_advances_only_while_the_chicken_moves():
    animation = ChickenWalkAnimation(random_flap_interval=(10.0, 10.0))

    first_pose = animation.update(is_moving=True, dt=0.125)
    first_phase = animation.phase
    second_pose = animation.update(is_moving=True, dt=0.125)

    assert first_phase > 0.0
    assert animation.phase > first_phase
    assert second_pose != first_pose
    assert second_pose.left_leg_pitch == -second_pose.right_leg_pitch
    assert second_pose.left_wing_roll == -second_pose.right_wing_roll


def test_random_wing_flap_can_happen_without_leg_motion():
    animation = ChickenWalkAnimation(
        random_flap_interval=(0.1, 0.1),
        random_flap_duration=(0.3, 0.3),
    )

    pose = animation.update(is_moving=False, dt=0.12)

    assert pose.left_leg_pitch == 0.0
    assert pose.right_leg_pitch == 0.0
    assert pose.left_wing_roll != 0.0
    assert pose.left_wing_roll == -pose.right_wing_roll


def test_wings_flap_continuously_while_falling():
    animation = ChickenWalkAnimation(random_flap_interval=(10.0, 10.0))

    first_pose = animation.update(is_moving=False, is_falling=True, dt=0.1)
    second_pose = animation.update(is_moving=False, is_falling=True, dt=0.1)

    assert first_pose.left_leg_pitch == 0.0
    assert first_pose.left_wing_roll != 0.0
    assert second_pose.left_wing_roll != first_pose.left_wing_roll
    assert second_pose.left_wing_roll == -second_pose.right_wing_roll


def test_allow_random_wings_false_forces_neutral_wings():
    animation = ChickenWalkAnimation(
        random_flap_interval=(0.1, 0.1),
        random_flap_duration=(0.3, 0.3),
    )

    flapping_pose = animation.update(is_moving=False, dt=0.12)
    stopped_pose = animation.update(is_moving=False, dt=0.12, allow_random_wings=False)

    assert flapping_pose.left_wing_roll != 0.0
    assert stopped_pose == NEUTRAL_CHICKEN_POSE


def test_ground_action_triggers_only_on_scratchable_ground():
    animation = ChickenWalkAnimation(
        ground_action_interval=(0.1, 0.1),
        random_flap_interval=(10.0, 10.0),
    )

    non_scratch_pose = animation.update(
        is_moving=True,
        dt=0.12,
        on_scratchable_ground=False,
    )

    assert animation.current_action is None
    assert animation.blocks_locomotion is False
    assert non_scratch_pose.head_pitch == 0.0

    scratch_pose = animation.update(
        is_moving=True,
        dt=0.12,
        on_scratchable_ground=True,
    )

    assert animation.current_action == "scratch"
    assert animation.blocks_locomotion is True
    assert scratch_pose.head_pitch > 0.0


def test_ground_action_advances_through_scratch_step_back_and_peck():
    animation = ChickenWalkAnimation(
        ground_action_interval=(0.1, 0.1),
        scratch_duration=0.2,
        step_back_duration=0.15,
        peck_duration=0.2,
        random_flap_interval=(10.0, 10.0),
    )

    animation.update(is_moving=True, dt=0.12, on_scratchable_ground=True)
    assert animation.current_action == "scratch"

    animation.update(is_moving=True, dt=0.12, on_scratchable_ground=True)
    assert animation.current_action == "step_back"

    step_back_pose = animation.update(is_moving=True, dt=0.08, on_scratchable_ground=True)
    assert animation.backward_speed > 0.0
    assert step_back_pose.head_pitch > 0.0

    animation.update(is_moving=True, dt=0.1, on_scratchable_ground=True)
    assert animation.current_action == "peck"

    peck_pose = animation.update(is_moving=True, dt=0.08, on_scratchable_ground=True)
    assert peck_pose.head_pitch >= 0.0

    animation.update(is_moving=True, dt=0.2, on_scratchable_ground=True)
    assert animation.current_action is None


def test_apply_chicken_pose_affects_only_wings_and_legs():
    left_leg = Node()
    right_leg = Node()
    left_wing = Node()
    right_wing = Node()
    head = Node()
    body = Node(rotation_x=9.0, rotation_z=3.0)

    apply_chicken_pose(
        {
            "left_leg": left_leg,
            "right_leg": right_leg,
            "left_wing": left_wing,
            "right_wing": right_wing,
            "head": head,
            "body": body,
        },
        ChickenPose(
            left_leg_pitch=12.0,
            right_leg_pitch=-12.0,
            left_wing_roll=-6.0,
            right_wing_roll=6.0,
            head_pitch=18.0,
        ),
    )

    assert left_leg.rotation_x == 12.0
    assert right_leg.rotation_x == -12.0
    assert left_wing.rotation_z == -6.0
    assert right_wing.rotation_z == 6.0
    assert head.rotation_x == 18.0
    assert body.rotation_x == 9.0
    assert body.rotation_z == 3.0


def test_visual_offset_is_negative_of_the_registered_pivot():
    assert get_part_visual_offset("body") == (0.0, 0.0, 0.0)
    assert get_part_visual_offset("left_wing") == (3.0, -4.0, 1.0)
    assert get_part_visual_offset("right_leg") == (-1.5, -7.0, -5.5)
    assert get_part_visual_offset("head", CHICKEN_HEAD_PIVOT) == (0.0, -7.0, 4.0)


def test_chicken_visual_uses_expected_orientation_fix():
    assert CHICKEN_VISUAL_ROTATION_X == 90.0
    assert CHICKEN_MODEL_MIN_Y == compute_chicken_model_min_y()
    assert CHICKEN_MODEL_MAX_Y == 7.0


def test_block_type_is_scratchable_matches_grass_and_dirt_materials():
    assert block_type_is_scratchable({"material": "grass"}) is True
    assert block_type_is_scratchable({"material": "dirt"}) is True
    assert block_type_is_scratchable({"material": "stone"}) is False
    assert block_type_is_scratchable(None) is False


def test_model_min_y_includes_extra_clearance_for_animated_feet():
    animated_leg_min_y = get_leg_root_min_y_for_pitch(-40.0)
    assert CHICKEN_MODEL_MIN_Y < animated_leg_min_y
    assert round(animated_leg_min_y - CHICKEN_MODEL_MIN_Y, 2) >= CHICKEN_FOOT_CLEARANCE
