import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Optional

from app import mcp
from client_intervals import BASE_URL as INTERVALS_URL
from client_intervals import athlete_id, get_intervals_client, handle_intervals_response
from client_strava import BASE_URL as STRAVA_URL
from client_strava import get_strava_client, handle_strava_response
from client_trainingpeaks import get_tp_client, handle_tp_response, tp_user_id
from plan_analysis import (
    ATL_DAYS, CTL_DAYS, ENDURANCE_SPORTS, daily_load, flags, load_from_atl,
    max_sustained_ramp, project, weekly_stats,
)
from plan_checks import check_plan
from plan_format import load_plan, plans_dir, save_plan


@mcp.tool()
def plan_check(plan_file: str, fix: bool = False) -> str:
    """
    Check a plan file for implausible values: swim steps over 5 km, steps
    over 6 h, targets over 200% of threshold, workouts over 8 h or TSS 400,
    and steps that don't add up to the planned time. Run it after editing a
    plan and before pushing it.

    Args:
        plan_file: File in the plans directory (TP_PLANS_DIR, default plans/).
        fix: Repair swim distances entered 1000x too large and save the file.
    """
    path = plans_dir() / plan_file
    plan = load_plan(path)
    warnings = check_plan(plan, fix=fix)
    fixed = fix and any("divided by 1000" in w for w in warnings)
    if fixed:
        save_plan(plan, path)
    return json.dumps({"plan": plan.name, "warnings": warnings, "saved_fixes": fixed}, indent=1)


STRAVA_SPORTS = {
    "Ride": "Ride", "VirtualRide": "Ride", "GravelRide": "Ride", "MountainBikeRide": "Ride", "EBikeRide": "Ride",
    "Run": "Run", "TrailRun": "Run", "VirtualRun": "Run", "Swim": "Swim",
}


def _intervals_fitness(days: int):
    with get_intervals_client() as c:
        aid = athlete_id()
        r = c.get(f"{INTERVALS_URL}/athlete/{aid}/wellness",
                  params={"oldest": str(date.today() - timedelta(days=days)), "newest": str(date.today())})
        handle_intervals_response(r)
        wellness = [(date.fromisoformat(d["id"]), d["ctl"], d["atl"]) for d in r.json() if d.get("ctl") is not None]
        r = c.get(f"{INTERVALS_URL}/athlete/{aid}")
        handle_intervals_response(r)
        swim = next((s for s in r.json().get("sportSettings", []) if "Swim" in s.get("types", [])), {})
    return wellness, swim.get("threshold_pace") or 1.0


def _recent_strava_hours(monday: date, weeks: int) -> dict[str, float]:
    after = datetime.combine(monday - timedelta(weeks=weeks), datetime.min.time()).timestamp()
    activities, page = [], 1
    with get_strava_client() as c:
        while True:
            r = c.get(f"{STRAVA_URL}/athlete/activities", params={"after": int(after), "per_page": 200, "page": page})
            handle_strava_response(r)
            batch = r.json()
            activities += batch
            if len(batch) < 200:
                break
            page += 1
    hours = defaultdict(float)
    for a in activities:
        if date.fromisoformat(a["start_date_local"][:10]) < monday:
            hours[STRAVA_SPORTS.get(a["sport_type"], a["sport_type"])] += a["moving_time"] / 3600 / weeks
    return {k: round(v, 1) for k, v in sorted(hours.items(), key=lambda kv: -kv[1]) if v >= 0.05}


def _tp_to_intervals_scale(icu_load: dict[date, float], monday: date, weeks: int = 4) -> tuple[float, str]:
    """intervals.icu load per TrainingPeaks TSS point over recent weeks.

    Plans carry TP's planned TSS but fitness comes from intervals.icu, which
    scores the same sessions differently (about 1.16x for this athlete).
    """
    oldest = monday - timedelta(weeks=weeks)
    try:
        with get_tp_client() as c:
            r = c.get(f"/fitness/v6/athletes/{tp_user_id()}/workouts/{oldest}/{monday - timedelta(days=1)}")
            handle_tp_response(r)
        tp_total = sum(w.get("tssActual") or 0 for w in r.json())
    except RuntimeError as e:
        return 1.0, f"TrainingPeaks unavailable ({e}); planned TSS used unscaled"
    icu_total = sum(l for d, l in icu_load.items() if oldest <= d < monday)
    if tp_total < 100 * weeks:
        return 1.0, "too little TrainingPeaks history to calibrate; planned TSS used unscaled"
    return round(icu_total / tp_total, 2), f"intervals.icu load / TP TSS over the {weeks} weeks before {monday}"


@mcp.tool()
def plan_analyze(
    plan_files: list[str],
    start_date: str,
    recent_weeks: int = 8,
    load_scale: Optional[float] = None,
) -> str:
    """
    Compare one or more plan files against the athlete's current and past
    fitness: weekly hours, sessions, longest sessions, easy/moderate/hard split
    and planned TSS per week, plus a CTL/ATL/TSB projection seeded from
    intervals.icu, and flags for big week-on-week jumps, missing recovery
    weeks, steep ramps and deep fatigue.

    Fitness comes from intervals.icu; recent volume from Strava (intervals.icu
    hides Strava-sourced activities). Planned load is the plan's TSS, scaled to
    intervals.icu's scoring. Strength sessions carry no planned TSS, so load
    is slightly understated.

    Args:
        plan_files: Files in the plans directory, e.g.
            ["enthusiast-off-season-12-weeks.json", "recreational-off-season-12-weeks.json"].
        start_date: YYYY-MM-DD the plan would start (a Monday).
        recent_weeks: Full weeks of recent training to average for comparison.
        load_scale: intervals.icu load per planned TSS point. Default: calibrated
            from recent TrainingPeaks vs intervals.icu numbers, else 1.0.
    """
    start = date.fromisoformat(start_date)
    monday = date.today() - timedelta(days=date.today().weekday())
    wellness, swim_mps = _intervals_fitness(days=420)
    icu_load = load_from_atl([(d, atl) for d, _, atl in wellness])
    if load_scale is None:
        load_scale, scale_note = _tp_to_intervals_scale(icu_load, monday)
    else:
        scale_note = "set by caller"

    today, ctl, atl = wellness[-1]
    # Carry fitness from the latest wellness day to the plan start at the recent average load.
    recent = [l for d, l in icu_load.items() if d > today - timedelta(days=28)]
    avg = sum(recent) / len(recent) if recent else 0
    for _ in range((start - today).days - 1):
        ctl += (avg - ctl) / CTL_DAYS
        atl += (avg - atl) / ATL_DAYS

    ctl_series = [(d, c) for d, c, _ in wellness]
    by_day = dict(ctl_series)
    last_year = {str(start - timedelta(days=364) + timedelta(weeks=i)):
                 round(by_day[start - timedelta(days=364) + timedelta(weeks=i)], 1)
                 for i in range(0, 13) if start - timedelta(days=364) + timedelta(weeks=i) in by_day}
    recent_weekly_load = round(sum(l for d, l in icu_load.items() if monday - timedelta(weeks=recent_weeks) <= d < monday) / recent_weeks)

    plans = []
    for f in plan_files:
        plan = load_plan(plans_dir() / f)
        weeks = weekly_stats(plan, swim_mps)
        project(weeks, daily_load(plan), ctl, atl, load_scale)
        n = len(weeks)
        ramps = [weeks[0].ctl - ctl] + [b.ctl - a.ctl for a, b in zip(weeks, weeks[1:])]
        totals = defaultdict(float)
        for wk in weeks:
            for s, h in wk.hours.items():
                totals[s] += h / n
        plans.append({
            "file": f,
            "name": plan.name,
            "summary": {
                "avg_hours_per_week": {s: round(h, 1) for s, h in totals.items()},
                "avg_endurance_hours": round(sum(totals[s] for s in ENDURANCE_SPORTS), 1),
                "avg_planned_tss": round(sum(wk.tss for wk in weeks) / n),
                "ctl": [round(ctl, 1), round(weeks[-1].ctl, 1)],
                "max_weekly_ramp": round(max(ramps), 1),
                "min_week_end_tsb": round(min(wk.ctl - wk.atl for wk in weeks), 1),
            },
            "weeks": [wk.to_dict() for wk in weeks],
            "flags": flags(weeks, ctl),
        })

    return json.dumps({
        "athlete": {
            "fitness_on": str(today),
            "ctl": round(wellness[-1][1], 1),
            "atl": round(wellness[-1][2], 1),
            "projected_start": {"date": str(start), "ctl": round(ctl, 1), "atl": round(atl, 1)},
            f"recent_{recent_weeks}wk_hours_per_week": _recent_strava_hours(monday, recent_weeks),
            f"recent_{recent_weeks}wk_load_per_week": recent_weekly_load,
            "max_4wk_ctl_ramp_last_year": round(max_sustained_ramp(ctl_series) or 0, 1),
            "ctl_same_window_last_year": last_year,
        },
        "load_scale": {"value": load_scale, "source": scale_note},
        "plans": plans,
        "notes": [
            "Planned load is the plan's TSS x load_scale; strength sessions have no planned TSS.",
            "Intensity split is from step targets (HR, power or pace bands), so unstructured sessions count as easy.",
        ],
    }, indent=1)
