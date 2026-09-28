from typing import Optional

from pydantic import BaseModel

from app import mcp
from client_intervals import BASE_URL, athlete_id, get_client, handle_response


class WorkoutInput(BaseModel):
    date: str  # "YYYY-MM-DD"
    name: str
    type: str  # "Run" | "Ride" | "Swim" | "Other" | ...
    description: str
    category: str = "WORKOUT"  # "WORKOUT" | "RACE_A" | "RACE_B" | "RACE_C" | "NOTE"
    external_id: str
    moving_time: Optional[int] = None


def _event_payload(w: WorkoutInput) -> dict:
    payload = w.model_dump(exclude={"date"}, exclude_none=True)
    payload["start_date_local"] = f"{w.date}T00:00:00"
    return payload


def _existing_ids_by_external_id(
    oldest: str, newest: str, athlete_id_override: Optional[str]
) -> dict[str, int]:
    # intervals.icu's own upsertOnUid mechanism only matches its server-generated
    # uid, never the client-supplied external_id (confirmed by live testing:
    # re-posting the same external_id via upsertOnUid=true created a duplicate
    # rather than updating). So external_id-based idempotency is done here by
    # looking up any existing event on the same date and updating it by id.
    with get_client() as c:
        r = c.get(
            f"{BASE_URL}/athlete/{athlete_id(athlete_id_override)}/events",
            params={"oldest": oldest, "newest": newest},
        )
    handle_response(r)
    return {
        event["external_id"]: event["id"]
        for event in r.json()
        if event.get("external_id")
    }


@mcp.tool()
def intervals_create_workout(
    workout: WorkoutInput,
    athlete_id_override: Optional[str] = None,
) -> str:
    """
    Create or update a single planned workout/event on the intervals.icu calendar.

    Idempotent via external_id — re-pushing the same external_id updates the
    existing event in place instead of creating a duplicate, so it's safe to
    call again after tweaking a target mid-week.

    description can use intervals.icu's structured workout syntax (Ride, Run and
    Swim) to push structured steps to a compatible device. One step per "- " line:
    optional cue text, then a duration (30s, 5m, 1h30m) or distance (400mtr, 2km —
    "m" means minutes), then a target (75-86%, 69% LTHR, 88-91% Pace), then an
    optional cadence (110-115rpm). A "Warmup"/"Cooldown" header line flags the
    step below it; a "<label> Nx" header repeats the steps below it; blank lines
    separate blocks. A step with no target (e.g. "- Static rest 10s") is a plain rest.
    e.g. 'Warmup\\n- 10m 50-65%\\n\\nMain set 6x\\n- 30s 112-120%\\n- 15s 33%\\n\\nCooldown\\n- 10m 50%'.
    %LTHR and %Pace targets need the matching threshold set in intervals.icu sport settings.

    category race flags (RACE_A/RACE_B/RACE_C) highlight the event differently
    on the calendar and in the fitness chart — use them for actual races, not
    just hard workouts.

    Args:
        workout: Workout fields — date (YYYY-MM-DD), name, type, description,
            category (default WORKOUT), external_id (deterministic slug, e.g.
            "run-intervals-2026-07-17"), moving_time in seconds (optional).
        athlete_id_override: Athlete ID. Defaults to INTERVALS_ATHLETE_ID env var.
    """
    aid = athlete_id(athlete_id_override)
    existing = _existing_ids_by_external_id(
        workout.date, workout.date, athlete_id_override
    )
    existing_id = existing.get(workout.external_id)
    with get_client() as c:
        if existing_id is not None:
            r = c.put(
                f"{BASE_URL}/athlete/{aid}/events/{existing_id}",
                json=_event_payload(workout),
            )
        else:
            r = c.post(f"{BASE_URL}/athlete/{aid}/events", json=_event_payload(workout))
    return handle_response(r)


@mcp.tool()
def intervals_create_workouts_bulk(
    workouts: list[WorkoutInput],
    athlete_id_override: Optional[str] = None,
) -> str:
    """
    Create or update multiple planned workouts/events in one call — handy for
    pushing a whole week or training block at once.

    New workouts (no existing event with a matching external_id on that date)
    are created in a single native bulk request. Workouts that already exist
    are updated individually by id — intervals.icu has no bulk update-by-key
    endpoint, only bulk create. Same external_id upsert behavior as
    intervals_create_workout. Use a convention like {type}-{session-label}-{date}
    for external_id so it stays collision-free across a whole season.

    Args:
        workouts: List of workouts, same fields as intervals_create_workout's
            workout param.
        athlete_id_override: Athlete ID. Defaults to INTERVALS_ATHLETE_ID env var.
    """
    if not workouts:
        return "No workouts provided."

    aid = athlete_id(athlete_id_override)
    oldest = min(w.date for w in workouts)
    newest = max(w.date for w in workouts)
    existing = _existing_ids_by_external_id(oldest, newest, athlete_id_override)

    creates = [w for w in workouts if w.external_id not in existing]
    updates = [w for w in workouts if w.external_id in existing]

    results = []
    with get_client() as c:
        if creates:
            r = c.post(
                f"{BASE_URL}/athlete/{aid}/events/bulk",
                params={"upsertOnUid": "false", "updatePlanApplied": "false"},
                json=[_event_payload(w) for w in creates],
            )
            results.append(handle_response(r))
        for w in updates:
            r = c.put(
                f"{BASE_URL}/athlete/{aid}/events/{existing[w.external_id]}",
                json=_event_payload(w),
            )
            results.append(handle_response(r))
    return "\n".join(results)


@mcp.tool()
def intervals_list_events(
    oldest: Optional[str] = None,
    newest: Optional[str] = None,
    category: Optional[str] = None,
    limit: Optional[int] = None,
    athlete_id_override: Optional[str] = None,
) -> str:
    """
    List planned events (workouts, notes, races) from the intervals.icu calendar.
    Useful for pulling planned-vs-actual comparisons back into a chat.

    Args:
        oldest: Start date YYYY-MM-DD (inclusive). Defaults to today.
        newest: End date YYYY-MM-DD (inclusive). Defaults to oldest plus 6 days.
        category: Comma-separated categories to filter for, e.g. "WORKOUT,RACE_A".
        limit: Maximum number of events to return.
        athlete_id_override: Athlete ID. Defaults to INTERVALS_ATHLETE_ID env var.
    """
    params: dict = {}
    if oldest:
        params["oldest"] = oldest
    if newest:
        params["newest"] = newest
    if category:
        params["category"] = category
    if limit:
        params["limit"] = limit
    with get_client() as c:
        r = c.get(
            f"{BASE_URL}/athlete/{athlete_id(athlete_id_override)}/events",
            params=params,
        )
    return handle_response(r)
