import pytest

import intervals_workout as iw
from plan_format import Block, Step, Workout


def ride(**kw):
    return Workout(
        day=1, sport="Ride", title="B ENDURANCE", target_unit="lthr",
        blocks=[
            Block(steps=[Step(kind="warmup", name="Warmup", seconds=1800, target=(50, 75), cadence=(80, 100))]),
            Block(reps=7, steps=[Step(name="MAIN SET #1", seconds=30, target=(75, 86)),
                                 Step(kind="rest", name="Rest", seconds=30, target=(69, 69))]),
            Block(steps=[Step(name="Recovery", seconds=300, target=(50, 75))]),
            Block(steps=[Step(kind="cooldown", name="COOL DOWN", seconds=3725, target=(50, 75))]),
        ],
        **kw,
    )


def test_ride_steps_in_verified_format():
    assert iw.workout_text(ride()) == "\n\n".join([
        "Warmup\n- Warmup 30m 50-75% LTHR 80-100rpm",
        "MAIN SET #1 7x\n- MAIN SET #1 30s 75-86% LTHR\n- Rest 30s 69% LTHR",
        "- Recovery 5m 50-75% LTHR",
        "Cooldown\n- COOL DOWN 1h2m5s 50-75% LTHR",
    ])


def test_swim_distances_notes_and_plain_rest():
    swim = Workout(day=0, sport="Swim", title="S", target_unit="pace", blocks=[
        Block(reps=2, steps=[Step(name="MAIN SET", meters=50, target=(88, 91), notes="fins 4x25m side kick"),
                             Step(kind="rest", name="Static rest", seconds=10)]),
    ])
    assert iw.workout_text(swim) == (
        "MAIN SET 2x\n- MAIN SET: fins 4x25 m side kick 50mtr 88-91% Pace\n- Static rest 10s"
    )


def test_bike_hr_as_power_maps_lthr_to_ftp():
    text = iw.workout_text(ride(), bike_hr_as_power=True)
    assert "- Warmup 30m 40-53% 80-100rpm" in text
    assert "LTHR" not in text
    assert [iw.lthr_to_ftp(v) for v in (50, 81, 89, 93, 100)] == [40, 56, 75, 90, 105]


def test_run_pace_as_power_keeps_values_and_leaves_hr_runs_alone():
    pace_run = Workout(day=0, sport="Run", title="R", target_unit="pace",
                       blocks=[Block(steps=[Step(name="Easy", seconds=1200, target=(67, 83))])])
    hr_run = pace_run.model_copy(update={"target_unit": "lthr"})
    assert iw.workout_text(pace_run, run_pace_as_power=True) == "- Easy 20m 67-83%"
    assert iw.workout_text(hr_run, run_pace_as_power=True) == "- Easy 20m 67-83% LTHR"


@pytest.mark.parametrize("line, expected", [
    ("- keep 1 eye in the water", "• keep 1 eye in the water"),
    ("1. 25m broken arrow + 25m freestyle", "1) 25 m broken arrow + 25 m freestyle"),
    ("Main set 4x", "Main set 4x."),
    ("200 easy freestyle", "200 easy freestyle"),
])
def test_coach_notes_cannot_become_steps(line, expected):
    text = iw.workout_text(ride(description=line))
    assert text.endswith("\n\n" + expected)


def test_unstructured_workout_is_just_its_notes():
    strength = Workout(day=0, sport="WeightTraining", title="Strength", description="- Squats 3x8")
    assert iw.workout_text(strength) == "• Squats 3x8"
