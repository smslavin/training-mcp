from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel

from app import mcp
from client_strava import BASE_URL, get_client, handle_response


class ActivityUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    sport_type: Optional[str] = None
    description: Optional[str] = None
    gear_id: Optional[str] = None
    commute: Optional[bool] = None
    trainer: Optional[bool] = None
    hide_from_home: Optional[bool] = None


def _to_timestamp(date_str: str) -> int:
    """Convert YYYY-MM-DD string to a Unix timestamp (start of day UTC)."""
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


# ---------------------------------------------------------------------------
# List / search
# ---------------------------------------------------------------------------

@mcp.tool()
def strava_list_activities(
    after: str,
    before: Optional[str] = None,
    per_page: int = 30,
    page: int = 1,
) -> str:
    """
    List Strava activities for the authenticated athlete in descending date order.

    Args:
        after: Start date YYYY-MM-DD (inclusive).
        before: End date YYYY-MM-DD (inclusive). Defaults to today.
        per_page: Number of activities per page (max 200).
        page: Page number for pagination.
    """
    params: dict = {
        "after": _to_timestamp(after),
        "per_page": min(per_page, 200),
        "page": page,
    }
    if before:
        params["before"] = _to_timestamp(before) + 86400  # include the full day
    with get_client() as c:
        r = c.get(f"{BASE_URL}/athlete/activities", params=params)
    return handle_response(r)


# ---------------------------------------------------------------------------
# Single activity
# ---------------------------------------------------------------------------

@mcp.tool()
def strava_get_activity(activity_id: int, include_all_efforts: bool = False) -> str:
    """
    Get full details for a single Strava activity.

    Args:
        activity_id: The Strava activity ID (integer).
        include_all_efforts: Include all segment efforts, not just PR efforts.
    """
    params: dict = {}
    if include_all_efforts:
        params["include_all_efforts"] = "true"
    with get_client() as c:
        r = c.get(f"{BASE_URL}/activities/{activity_id}", params=params)
    return handle_response(r)


@mcp.tool()
def strava_get_activity_laps(activity_id: int) -> str:
    """
    Get laps for a Strava activity.

    Args:
        activity_id: The Strava activity ID (integer).
    """
    with get_client() as c:
        r = c.get(f"{BASE_URL}/activities/{activity_id}/laps")
    return handle_response(r)


@mcp.tool()
def strava_get_activity_streams(
    activity_id: int,
    keys: Optional[str] = None,
) -> str:
    """
    Get time-series data streams for a Strava activity.

    Args:
        activity_id: The Strava activity ID (integer).
        keys: Comma-separated stream keys to fetch. Available streams:
            time, distance, latlng, altitude, velocity_smooth, heartrate,
            cadence, watts, temp, moving, grade_smooth.
            Defaults to all available streams.
    """
    if not keys:
        keys = "time,distance,altitude,velocity_smooth,heartrate,cadence,watts,temp,moving,grade_smooth"
    params = {"keys": keys, "key_by_type": "true"}
    with get_client() as c:
        r = c.get(f"{BASE_URL}/activities/{activity_id}/streams", params=params)
    return handle_response(r)


@mcp.tool()
def strava_get_activity_zones(activity_id: int) -> str:
    """
    Get heart rate and power zones for a Strava activity.

    Args:
        activity_id: The Strava activity ID (integer).
    """
    with get_client() as c:
        r = c.get(f"{BASE_URL}/activities/{activity_id}/zones")
    return handle_response(r)


@mcp.tool()
def strava_get_activity_comments(activity_id: int, page: int = 1, per_page: int = 30) -> str:
    """
    Get comments on a Strava activity.

    Args:
        activity_id: The Strava activity ID (integer).
        page: Page number.
        per_page: Comments per page (max 200).
    """
    with get_client() as c:
        r = c.get(
            f"{BASE_URL}/activities/{activity_id}/comments",
            params={"page": page, "per_page": min(per_page, 200)},
        )
    return handle_response(r)


@mcp.tool()
def strava_get_activity_kudos(activity_id: int, page: int = 1, per_page: int = 30) -> str:
    """
    Get kudos (likes) on a Strava activity.

    Args:
        activity_id: The Strava activity ID (integer).
        page: Page number.
        per_page: Kudos per page (max 200).
    """
    with get_client() as c:
        r = c.get(
            f"{BASE_URL}/activities/{activity_id}/kudos",
            params={"page": page, "per_page": min(per_page, 200)},
        )
    return handle_response(r)


@mcp.tool()
def strava_update_activity(activity_id: int, updates: ActivityUpdate) -> str:
    """
    Update fields on a Strava activity.

    Args:
        activity_id: The Strava activity ID (integer).
        updates: Fields to update. All fields are optional — only provided fields
            are written. sport_type takes precedence over type when both are set.
    """
    with get_client() as c:
        r = c.put(f"{BASE_URL}/activities/{activity_id}", json=updates.model_dump(exclude_none=True))
    return handle_response(r)
