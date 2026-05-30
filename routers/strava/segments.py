import json
from datetime import datetime, timezone
from typing import Optional

from app import mcp
from client_strava import BASE_URL, get_client, handle_response


@mcp.tool()
def strava_get_segment(segment_id: int) -> str:
    """
    Get details for a Strava segment (name, location, distance, grade, elevation).

    Args:
        segment_id: The Strava segment ID (integer).
    """
    with get_client() as c:
        r = c.get(f"{BASE_URL}/segments/{segment_id}")
    return handle_response(r)


@mcp.tool()
def strava_get_segment_effort(effort_id: int) -> str:
    """
    Get a single Strava segment effort by ID.

    Args:
        effort_id: The segment effort ID (integer). Find effort IDs via
            strava_get_activity with include_all_efforts=True.
    """
    with get_client() as c:
        r = c.get(f"{BASE_URL}/segment_efforts/{effort_id}")
    return handle_response(r)


@mcp.tool()
def strava_list_segment_efforts(
    segment_id: int,
    after: Optional[str] = None,
    before: Optional[str] = None,
    per_page: int = 30,
) -> str:
    """
    List the authenticated athlete's efforts on a Strava segment, newest first.

    Args:
        segment_id: The Strava segment ID (integer).
        after: Filter to efforts after this date YYYY-MM-DD.
        before: Filter to efforts before this date YYYY-MM-DD.
        per_page: Number of results (max 200).
    """
    params: dict = {
        "segment_id": segment_id,
        "per_page": min(per_page, 200),
    }
    if after:
        dt = datetime.strptime(after, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        params["start_date_local"] = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    if before:
        dt = datetime.strptime(before, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        params["end_date_local"] = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_client() as c:
        r = c.get(f"{BASE_URL}/segment_efforts", params=params)
    return handle_response(r)


@mcp.tool()
def strava_list_starred_segments(per_page: int = 30) -> str:
    """
    List segments starred by the authenticated athlete on Strava.

    Args:
        per_page: Number of results (max 200).
    """
    with get_client() as c:
        r = c.get(
            f"{BASE_URL}/segments/starred",
            params={"per_page": min(per_page, 200)},
        )
    return handle_response(r)


@mcp.tool()
def strava_get_activity_segment_efforts(activity_id: int) -> str:
    """
    Get all segment efforts for a Strava activity including non-PR efforts.
    Returns effort IDs, segment names, elapsed times, and rankings.

    Args:
        activity_id: The Strava activity ID (integer).
    """
    with get_client() as c:
        r = c.get(
            f"{BASE_URL}/activities/{activity_id}",
            params={"include_all_efforts": "true"},
        )
    handle_response(r)
    activity = r.json()
    efforts = activity.get("segment_efforts", [])
    result = [
        {
            "id": e["id"],
            "name": e["segment"]["name"],
            "segment_id": e["segment"]["id"],
            "elapsed_time": e["elapsed_time"],
            "start_date_local": e["start_date_local"],
            "distance": e["distance"],
            "average_watts": e.get("average_watts"),
            "average_heartrate": e.get("average_heartrate"),
            "pr_rank": e.get("pr_rank"),
            "kom_rank": e.get("kom_rank"),
        }
        for e in efforts
    ]
    return json.dumps(result)
