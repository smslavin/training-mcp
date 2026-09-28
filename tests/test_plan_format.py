import json
from datetime import date

import pytest
from pydantic import ValidationError

import plan_format as pf

START = date(2027, 10, 4)


def tp_step(seconds=None, meters=None, lo=None, hi=None, kind="active", name="Step", cadence=None, notes=None):
    length = {"value": seconds, "unit": "second"} if seconds is not None else {"value": meters, "unit": "meter"}
    targets = [{"minValue": lo, "maxValue": hi}]
    if cadence:
        targets.append({"minValue": cadence[0], "maxValue": cadence[1], "unit": "roundOrStridePerMinute"})
    step = {"name": name, "length": length, "targets": targets, "intensityClass": kind, "openDuration": False}
    if notes:
        step["notes"] = notes
    return step


def tp_workout(workout_id, day, type_id, title, metric=None, blocks=None, order=None, **extra):
    w = {
        "workoutId": workout_id,
        "workoutDay": f"2027-10-{4 + day:02d}T00:00:00",
        "workoutTypeValueId": type_id,
        "title": title,
        **extra,
    }
    if order is not None:
        w["orderOnDay"] = order
    if blocks is not None:
        w["structure"] = {"structure": blocks, "primaryIntensityMetric": metric, "primaryLengthMetric": "duration"}
    return w


def single(step):
    return {"type": "step", "length": {"value": 1, "unit": "repetition"}, "steps": [step]}


def repeat(n, *steps):
    return {"type": "repetition", "length": {"value": n, "unit": "repetition"}, "steps": list(steps)}


BIKE = tp_workout(
    101, 0, 2, "B ENDURANCE", "percentOfThresholdHr",
    [
        single(tp_step(1800, lo=50, hi=75, kind="warmUp", name="Warmup", cadence=(80.0, 100.0))),
        repeat(7, tp_step(30, lo=75, hi=86, name="MAIN"), tp_step(30, lo=69, hi=None, kind="rest", name="Rest")),
        single(tp_step(600, lo=50, hi=75, kind="coolDown", name="COOL DOWN")),
    ],
    totalTimePlanned=1.1833333, tssPlanned=47.32, ifPlanned=0.6789, description="  Easy spin.  ",
)
SWIM = tp_workout(
    102, 1, 1, "S TECHNIQUE", "percentOfThresholdPace",
    [repeat(2, tp_step(meters=50, lo=88, hi=91, notes="fins 25 side kick"), tp_step(10, lo=0, kind="rest", name="Static rest"))],
)
STRENGTH = tp_workout(103, 1, 9, "Foundational Strength", order=2, description="Squats, push ups")
DAY_OFF = tp_workout(104, 2, 7, "Day off", blocks=[])


def test_maps_structured_workout_fields():
    plan, warnings = pf.plan_from_tp([BIKE], "459451", "Off season", START)
    w = plan.workouts[0]
    assert warnings == []
    assert (w.day, w.sport, w.target_unit, w.source_id) == (0, "Ride", "lthr", "101")
    assert (w.planned_minutes, w.planned_tss, w.planned_if) == (71.0, 47.3, 0.679)
    assert w.description == "Easy spin."
    warmup, main, cooldown = w.blocks
    assert warmup.steps[0].model_dump(exclude_none=True) == {
        "kind": "warmup", "name": "Warmup", "seconds": 1800, "target": (50, 75), "cadence": (80, 100),
    }
    assert main.reps == 7
    assert main.steps[1].target == (69, 69)  # TP leaves maxValue empty for a single value
    assert cooldown.steps[0].kind == "cooldown"


def test_swim_distance_notes_and_plain_rest():
    plan, _ = pf.plan_from_tp([SWIM], "1", "p", START)
    work, rest = plan.workouts[0].blocks[0].steps
    assert (work.meters, work.seconds, work.notes) == (50, None, "fins 25 side kick")
    assert rest.target is None  # TP's 0% target means a plain rest


def test_unstructured_workouts_and_ordering():
    plan, _ = pf.plan_from_tp([DAY_OFF, STRENGTH, SWIM], "1", "p", START)
    assert [(w.day, w.sport) for w in plan.workouts] == [(1, "Swim"), (1, "WeightTraining"), (2, "Note")]
    assert plan.workouts[1].blocks == [] and plan.workouts[1].target_unit is None


def test_unsupported_structure_keeps_workout_and_warns():
    odd = tp_workout(105, 0, 3, "R ODD", "percentOfThresholdHr", [single(tp_step(60, lo=70, hi=80) | {"length": {"value": 1, "unit": "lap"}})])
    plan, warnings = pf.plan_from_tp([odd], "1", "p", START)
    assert plan.workouts[0].blocks == []
    assert len(warnings) == 1 and "R ODD" in warnings[0] and "lap" in warnings[0]


def test_round_trip_and_one_step_per_line(tmp_path):
    plan, _ = pf.plan_from_tp([BIKE, SWIM, STRENGTH, DAY_OFF], "459451", "Off season", START)
    path = pf.save_plan(plan, tmp_path / "nested" / "plan.json")
    assert pf.load_plan(path) == plan
    text = path.read_text()
    step_lines = [line for line in text.splitlines() if '"seconds"' in line or '"meters"' in line]
    assert len(step_lines) == 6
    assert all(line.strip().startswith("{") and line.rstrip(",").endswith("}") for line in step_lines)
    assert "[80, 100]" in text and ".0]" not in text  # whole-number targets stay whole
    json.loads(text)  # still plain JSON


def test_defaults_are_omitted_from_file():
    plan, _ = pf.plan_from_tp([BIKE], "1", "p", START)
    data = json.loads(pf.dump_plan(plan))
    main = data["workouts"][0]["blocks"][1]
    assert "reps" not in data["workouts"][0]["blocks"][0]  # reps 1 is the default
    assert "kind" not in main["steps"][0]  # "active" is the default


def test_hand_edits_are_validated():
    plan, _ = pf.plan_from_tp([BIKE], "1", "p", START)
    data = json.loads(pf.dump_plan(plan))
    data["workouts"][0]["blocks"][0]["steps"][0]["meters"] = 400  # now has seconds and meters
    with pytest.raises(ValidationError, match="exactly one of seconds or meters"):
        pf.Plan.model_validate(data)
    data = json.loads(pf.dump_plan(plan))
    del data["workouts"][0]["target_unit"]
    with pytest.raises(ValidationError, match="need a target_unit"):
        pf.Plan.model_validate(data)


def test_plans_dir_override(monkeypatch, tmp_path):
    monkeypatch.setenv("TP_PLANS_DIR", str(tmp_path))
    assert pf.plans_dir() == tmp_path
