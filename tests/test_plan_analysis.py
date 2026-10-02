from datetime import date, timedelta

import pytest

import plan_analysis as pa
from plan_format import Block, Plan, Step, Workout


def session(day, sport, minutes, tss, target=None, unit=None, meters=None):
    blocks = []
    if target:
        step = Step(name="s", meters=meters, target=target) if meters else Step(name="s", seconds=minutes * 60, target=target)
        blocks = [Block(steps=[step])]
    return Workout(day=day, sport=sport, title=f"{sport} {day}", planned_minutes=minutes, planned_tss=tss,
                   target_unit=unit, blocks=blocks)


def plan(*workouts):
    return Plan(format_version=1, name="p", workouts=list(workouts))


def weekly_plan(endurance_minutes_per_week, run_minutes_per_week=None):
    """One ride per week of the given length, plus an optional run."""
    ws = []
    for i, m in enumerate(endurance_minutes_per_week):
        ws.append(session(i * 7, "Ride", m, m * 0.7, target=(70, 80), unit="lthr"))
        if run_minutes_per_week:
            ws.append(session(i * 7 + 2, "Run", run_minutes_per_week[i], run_minutes_per_week[i] * 0.7))
    return plan(*ws)


def test_weekly_stats_hours_sessions_longest_and_strength_kept_separate():
    p = plan(
        session(0, "Ride", 120, 80, target=(50, 85), unit="lthr"),
        session(2, "Ride", 60, 40, target=(50, 85), unit="lthr"),
        session(3, "WeightTraining", 40, None),
        session(4, "Note", 0, None),
        session(8, "Run", 45, 30, target=(73, 89), unit="lthr"),
    )
    w1, w2 = pa.weekly_stats(p)
    assert (w1.hours["Ride"], w1.sessions["Ride"], w1.longest["Ride"]) == (3.0, 2, 2.0)
    assert w1.hours["WeightTraining"] == pytest.approx(40 / 60)
    assert w1.endurance_hours == 3.0  # strength isn't endurance volume
    assert w1.tss == 120 and "Note" not in w1.sessions
    assert w2.hours["Run"] == 0.75


def test_intensity_bands_per_target_unit():
    p = plan(
        session(0, "Ride", 60, 40, target=(60, 70), unit="lthr"),    # easy (<90% LTHR)
        session(1, "Ride", 30, 30, target=(95, 98), unit="lthr"),    # moderate
        session(2, "Ride", 30, 40, target=(105, 115), unit="ftp"),   # hard (>=91% FTP)
    )
    pct = pa.weekly_stats(p)[0].to_dict()["intensity_pct"]
    assert pct == {"easy": 50, "moderate": 25, "hard": 25}


def test_swim_distance_time_uses_threshold_pace():
    p = plan(session(0, "Swim", 30, 25, target=(100, 100), unit="pace", meters=1800))
    week = pa.weekly_stats(p, swim_threshold_mps=1.0)[0]
    assert week.intensity_hours["hard"] == pytest.approx(0.5)  # 1800 m at 1.0 m/s


def test_projection_matches_ewma_and_steady_load_holds_ctl():
    p = weekly_plan([60] * 2)
    weeks = pa.weekly_stats(p)
    days = pa.project(weeks, {d: 50 for d in range(14)}, ctl=50, atl=50)
    assert days[-1] == pytest.approx((50, 50))
    days = pa.project(weeks, {0: 100}, ctl=0, atl=0, scale=2.0)
    assert days[0] == pytest.approx((200 / 42, 200 / 7))
    assert weeks[0].ctl == days[6][0]


def test_load_from_atl_inverts_the_ewma():
    atl, series, loads = 40.0, [], [0, 60, 120, 0, 30]
    d = date(2026, 9, 1)
    series.append((d, atl))
    for i, l in enumerate(loads, 1):
        atl += (l - atl) / 7
        series.append((d + timedelta(days=i), atl))
    back = pa.load_from_atl(series)
    assert list(back.values()) == pytest.approx(loads)


def test_max_sustained_ramp():
    series = [(date(2026, 1, 1) + timedelta(days=i), 50 + (i * 0.5 if i < 40 else 20)) for i in range(80)]
    assert pa.max_sustained_ramp(series, weeks=4) == pytest.approx(3.5)
    assert pa.max_sustained_ramp(series[:20]) is None


def test_flags_jumps_and_missing_recovery():
    p = weekly_plan([480, 600, 600, 620, 640, 650], run_minutes_per_week=[60, 60, 60, 90, 90, 90])
    weeks = pa.weekly_stats(p)
    pa.project(weeks, pa.daily_load(p), 60, 60)
    found = pa.flags(weeks, 60)
    assert "week 2: endurance hours jump 9.0 → 11.0 (+22%)" in found
    assert "week 4: run time jumps 1.0 → 1.5 h (+50%)" in found
    assert any(f.startswith("weeks 1-6: 6 weeks with no recovery week") for f in found)


def test_recovery_week_breaks_the_streak():
    p = weekly_plan([600, 620, 640, 400, 600, 620, 640, 660])
    weeks = pa.weekly_stats(p)
    pa.project(weeks, pa.daily_load(p), 60, 60)
    assert not any("no recovery week" in f for f in pa.flags(weeks, 60))


def test_steep_ramp_and_deep_fatigue_are_flagged():
    p = weekly_plan([600, 600])
    weeks = pa.weekly_stats(p)
    pa.project(weeks, {d: 300 for d in range(14)}, ctl=40, atl=40)
    found = pa.flags(weeks, 40)
    assert any("CTL ramp" in f for f in found) and any("TSB" in f for f in found)
