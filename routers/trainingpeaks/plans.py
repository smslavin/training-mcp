import json
import re
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Optional

from app import mcp
from client_trainingpeaks import get_client, handle_response, tp_user_id
from plan_format import plan_from_tp, plans_dir, save_plan


@mcp.tool()
def tp_list_plans(search: Optional[str] = None) -> str:
    """
    List the training plans available in the TrainingPeaks account, such as a
    coaching program's plan library.

    Args:
        search: Only plans whose title contains every word of this text
            (case-insensitive), e.g. "off season 8".
    """
    with get_client() as c:
        r = c.get("/plans/v1/plans")
    handle_response(r)
    words = (search or "").lower().split()
    plans = [
        {"plan_id": str(p["planId"]), "title": p["title"], "workouts": p.get("workoutCount")}
        for p in r.json()
        if all(w in p["title"].lower() for w in words)
    ]
    plans.sort(key=lambda p: p["title"])
    return json.dumps(plans, indent=1)


def _next_monday_a_year_out() -> date:
    d = date.today() + timedelta(days=365)
    return d + timedelta(days=-d.weekday() % 7)


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def _calendar_ids(c, user_id: str, start: date, end: date) -> set:
    r = c.get(f"/fitness/v6/athletes/{user_id}/workouts/{start}/{end}")
    handle_response(r)
    return {w["workoutId"] for w in r.json()}


@mcp.tool()
def tp_fetch_plan(
    plan_id: str,
    start_date: Optional[str] = None,
    keep_on_calendar: bool = False,
    filename: Optional[str] = None,
    overwrite: bool = False,
) -> str:
    """
    Fetch a TrainingPeaks training plan's workouts and save them as a plan file
    for analysis, editing and pushing to intervals.icu.

    A TP plan is a template, so this applies it to the TP calendar, reads the
    workouts it created, then removes it again. With the default start date (a
    Monday about a year out) the round trip never touches real workouts.
    Workouts already on the calendar in that range are left out of the plan.

    Args:
        plan_id: Plan id from tp_list_plans.
        start_date: YYYY-MM-DD to apply the plan from. Only matters with
            keep_on_calendar; the saved file uses day offsets either way.
        keep_on_calendar: Leave the applied plan on the TP calendar.
            intervals.icu is the source of truth, so usually leave this off.
        filename: File name inside the plans directory (TP_PLANS_DIR, default
            plans/). Defaults to a slug of the plan title.
        overwrite: Replace an existing file. Off by default so a re-fetch
            can't wipe edits to a plan.
    """
    if keep_on_calendar and not start_date:
        raise ValueError("keep_on_calendar needs an explicit start_date")
    start = date.fromisoformat(start_date) if start_date else _next_monday_a_year_out()

    with get_client() as c:
        r = c.get(f"/plans/v1/plans/{plan_id}")
        handle_response(r)
        title = r.json()["title"]
        path = plans_dir() / (filename or f"{_slug(title)}.json")
        if path.exists() and not overwrite:
            raise ValueError(f"{path} already exists; pass overwrite=True to replace it")

        user_id = tp_user_id()
        # Plan length is only known after applying, so check a generous window
        # for workouts that are already there and must not end up in the plan.
        existing = _calendar_ids(c, user_id, start, start + timedelta(days=400))
        r = c.post(
            "/plans/v1/commands/applyplan",
            json=[{"athleteId": user_id, "planId": plan_id, "targetDate": str(start), "startType": "1"}],
        )
        handle_response(r)
        applied = r.json()[0]
        try:
            end = datetime.fromisoformat(applied["endDate"]).date()
            r = c.get(f"/fitness/v6/athletes/{user_id}/workouts/{start}/{end}")
            handle_response(r)
            on_calendar = r.json()
        finally:
            if not keep_on_calendar:
                handle_response(c.post("/plans/v1/commands/removeplan", json={"appliedPlanId": applied["appliedPlanId"]}))

    plan_workouts = [w for w in on_calendar if w["workoutId"] not in existing]
    skipped = len(on_calendar) - len(plan_workouts)
    plan, warnings = plan_from_tp(plan_workouts, plan_id, title, start)
    save_plan(plan, path)

    sports = Counter(w.sport for w in plan.workouts)
    last_day = max((w.day for w in plan.workouts), default=0)
    return json.dumps({
        "path": str(path),
        "title": title,
        "workouts": len(plan.workouts),
        "weeks": last_day // 7 + 1,
        "by_sport": dict(sports),
        "structured": sum(1 for w in plan.workouts if w.blocks),
        "skipped_existing_calendar_workouts": skipped,
        "left_on_calendar": f"{start} to {end}" if keep_on_calendar else None,
        "warnings": warnings,
    }, indent=1)
