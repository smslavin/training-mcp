import json
from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Optional

from app import mcp
from client_intervals import BASE_URL, athlete_id, get_client, handle_response
from intervals_workout import planned_seconds, workout_text
from plan_format import Plan, load_plan, plans_dir
from routers.intervals.events import WorkoutInput, _event_payload

NOTE_TYPE = "Other"


def _external_ids(plan_key: str, plan: Plan) -> list[str]:
    """Stable id per workout so re-pushing an edited plan updates in place.

    Fetched workouts keep their source id; added ones are keyed by day, sport
    and position among added workouts of that sport on that day.
    """
    added = Counter()
    ids = []
    for w in plan.workouts:
        if w.source_id:
            ids.append(f"plan:{plan_key}:{w.source_id}")
        else:
            added[(w.day, w.sport)] += 1
            ids.append(f"plan:{plan_key}:d{w.day}-{w.sport.lower()}-{added[(w.day, w.sport)]}")
    return ids


def build_events(
    plan_key: str,
    plan: Plan,
    start: date,
    run_pace_as_power: bool = False,
    bike_hr_as_power: bool = False,
) -> list[WorkoutInput]:
    events = []
    for w, ext_id in zip(plan.workouts, _external_ids(plan_key, plan)):
        # Day-off entries and 0-minute placeholders ("REST: Post training rest")
        # are calendar notes, not workouts.
        is_note = w.sport == "Note" or (not w.blocks and not w.planned_minutes)
        events.append(WorkoutInput(
            date=str(start + timedelta(days=w.day)),
            name=w.title,
            type=NOTE_TYPE if is_note else w.sport,
            category="NOTE" if is_note else "WORKOUT",
            description=workout_text(w, run_pace_as_power, bike_hr_as_power) or w.title,
            external_id=ext_id,
            moving_time=None if is_note else planned_seconds(w),
        ))
    return events


def _unchanged(current: dict, payload: dict) -> bool:
    """True when the calendar event already holds every field we would send.

    intervals.icu stores notes without a type, and when it creates a
    distance-based swim it sets moving_time from its own pace estimate, so
    those two fields can differ without the workout having changed.
    """
    for k, v in payload.items():
        have = current.get(k)
        if k == "type" and payload.get("category") == "NOTE":
            continue
        if k == "moving_time" and have is not None and v is not None and abs(have - v) <= 60:
            continue
        if have != v:
            return False
    return True


@mcp.tool()
def plan_push_to_intervals(
    plan_file: str,
    start_date: str,
    dry_run: bool = True,
    run_pace_as_power: bool = False,
    bike_hr_as_power: bool = False,
    prune: bool = True,
    athlete_id_override: Optional[str] = None,
) -> str:
    """
    Put a plan file's workouts on the intervals.icu calendar.

    Re-pushing an edited plan updates its events in place (matched by
    external_id), leaves events whose content is unchanged alone, and, with
    prune, deletes events for workouts that were removed from the file. Only
    events this tool created for this plan file are touched.

    Args:
        plan_file: File in the plans directory (TP_PLANS_DIR, default plans/),
            e.g. "enthusiast-off-season-12-weeks.json".
        start_date: YYYY-MM-DD for day 0 of the plan. Plans start on a Monday.
        dry_run: Report what would change without writing. On by default.
        run_pace_as_power: Write %-of-threshold-pace runs as %FTP power
            targets (running power tracks speed on flat ground).
        bike_hr_as_power: Write %LTHR rides as approximate %FTP power targets.
            Needed for Zwift, which only accepts power-based workouts.
        prune: Delete this plan's events that are no longer in the file.
        athlete_id_override: Athlete ID. Defaults to INTERVALS_ATHLETE_ID env var.
    """
    path = plans_dir() / plan_file
    plan = load_plan(path)
    start = date.fromisoformat(start_date)
    plan_key = path.stem
    events = build_events(plan_key, plan, start, run_pace_as_power, bike_hr_as_power)
    oldest = str(start)
    newest = str(start + timedelta(days=max((w.day for w in plan.workouts), default=0)))

    aid = athlete_id(athlete_id_override)
    with get_client() as c:
        r = c.get(f"{BASE_URL}/athlete/{aid}/events", params={"oldest": oldest, "newest": newest})
        handle_response(r)
        ours = {
            e["external_id"]: e
            for e in r.json()
            if (e.get("external_id") or "").startswith(f"plan:{plan_key}:")
        }
        wanted = {e.external_id for e in events}
        creates = [e for e in events if e.external_id not in ours]
        existing = [e for e in events if e.external_id in ours]
        updates = [e for e in existing if not _unchanged(ours[e.external_id], _event_payload(e))]
        deletes = [(x, e["id"]) for x, e in ours.items() if x not in wanted] if prune else []

        if not dry_run:
            if creates:
                handle_response(c.post(
                    f"{BASE_URL}/athlete/{aid}/events/bulk",
                    params={"upsertOnUid": "false", "updatePlanApplied": "false"},
                    json=[_event_payload(e) for e in creates],
                ))
            for e in updates:
                handle_response(c.put(f"{BASE_URL}/athlete/{aid}/events/{ours[e.external_id]['id']}", json=_event_payload(e)))
            for _, event_id in deletes:
                handle_response(c.delete(f"{BASE_URL}/athlete/{aid}/events/{event_id}"))

    weeks = defaultdict(Counter)
    for w in plan.workouts:
        weeks[w.day // 7 + 1][w.sport] += 1
    sample = next((e for e in events if e.category == "WORKOUT" and e.type in ("Ride", "Run")), None)
    return json.dumps({
        "dry_run": dry_run,
        "plan": plan.name,
        "dates": f"{oldest} ({start.strftime('%A')}) to {newest}",
        "created": len(creates),
        "updated": len(updates),
        "unchanged": len(existing) - len(updates),
        "deleted": len(deletes),
        "notes": sum(1 for e in events if e.category == "NOTE"),
        "options": {"run_pace_as_power": run_pace_as_power, "bike_hr_as_power": bike_hr_as_power},
        "sessions_by_week": {wk: dict(c) for wk, c in sorted(weeks.items())},
        "sample": {"date": sample.date, "name": sample.name, "description": sample.description[:600]} if sample else None,
    }, indent=1)
