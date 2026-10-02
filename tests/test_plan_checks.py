import json

import plan_format as pf
from plan_checks import check_plan
from plan_format import Block, Plan, Step, Workout


def plan(*workouts):
    return Plan(format_version=1, name="p", workouts=list(workouts))


def thousandfold_swim():
    # Shape of the real coach error: 2400 m of reps entered as 2,400,000 m,
    # with 280 s of rests; TP's planned time came out at 705 h.
    return Workout(
        day=14, sport="Swim", title="*S TECHNIQUE: Momentum through core", target_unit="pace",
        planned_minutes=42304.1, planned_tss=42983.0,
        blocks=[
            Block(reps=4, steps=[Step(name="WARM UP", meters=50000, target=(80, 90)), Step(kind="rest", name="Rest", seconds=10)]),
            Block(reps=8, steps=[Step(name="MAIN", meters=200000, target=(80, 90)), Step(kind="rest", name="Rest", seconds=30)]),
            Block(steps=[Step(name="Cool Down", meters=200000, target=(70, 80))]),
        ],
    )


def endurance_ride(minutes=75, step_minutes=75, target=(50, 85)):
    return Workout(day=1, sport="Ride", title="B ENDURANCE", target_unit="lthr", planned_minutes=minutes,
                   blocks=[Block(steps=[Step(name="ENDURANCE", seconds=step_minutes * 60, target=target)])])


def test_clean_plan_has_no_warnings():
    assert check_plan(plan(endurance_ride())) == []


def test_thousandfold_swim_is_flagged_once_per_problem():
    warnings = check_plan(plan(thousandfold_swim()))
    assert warnings == [
        "day 14 Swim '*S TECHNIQUE: Momentum through core': 3 swim steps over 5000 m (up to 200000 m)",
        "day 14 Swim '*S TECHNIQUE: Momentum through core': planned 705.1 h",
        "day 14 Swim '*S TECHNIQUE: Momentum through core': planned TSS 42983.0",
    ]


def test_fix_divides_distances_and_rescales_planned_time_and_tss():
    p = plan(thousandfold_swim())
    warnings = check_plan(p, fix=True)
    swim = p.workouts[0]
    assert [s.meters for b in swim.blocks for s in b.steps if s.meters] == [50, 200, 200]
    # 280 s of rest stays; the remaining 42299.4 min of swimming shrinks 1000x.
    assert swim.planned_minutes == 47.0
    assert swim.planned_tss == round(42983.0 * 47.0 / 42304.1, 1)
    assert len(warnings) == 1 and "divided by 1000" in warnings[0]
    assert check_plan(p) == []


def test_fix_leaves_long_but_plausible_distances_alone():
    open_water = Workout(day=0, sport="Swim", title="OW", target_unit="pace", planned_minutes=120,
                         blocks=[Block(steps=[Step(name="Continuous", meters=6500, target=(80, 85))])])
    p = plan(open_water)
    warnings = check_plan(p, fix=True)
    assert p.workouts[0].blocks[0].steps[0].meters == 6500
    assert warnings == ["day 0 Swim 'OW': 1 swim steps over 5000 m (up to 6500 m)"]


def test_hand_edit_slips_are_caught():
    assert check_plan(plan(endurance_ride(step_minutes=120))) == [
        "day 1 Ride 'B ENDURANCE': steps add up to 120 min but planned time is 75 min"]
    assert "steps target over 200%" in check_plan(plan(endurance_ride(target=(50, 850))))[0]


def test_plan_check_tool_saves_fixes_only_when_asked(monkeypatch, tmp_path):
    from routers.plan_files import plan_check

    monkeypatch.setenv("TP_PLANS_DIR", str(tmp_path))
    pf.save_plan(plan(thousandfold_swim()), tmp_path / "p.json")
    assert json.loads(plan_check("p.json"))["saved_fixes"] is False
    assert pf.load_plan(tmp_path / "p.json").workouts[0].planned_minutes == 42304.1
    assert json.loads(plan_check("p.json", fix=True))["saved_fixes"] is True
    assert pf.load_plan(tmp_path / "p.json").workouts[0].planned_minutes == 47.0
