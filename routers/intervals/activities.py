from typing import Optional

from pydantic import BaseModel

from app import mcp
from client_intervals import BASE_URL, athlete_id, get_client, handle_response


class ActivityUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    type: Optional[str] = None
    indoor: Optional[bool] = None
    perceived_exertion: Optional[int] = None
    feel: Optional[int] = None
    race: Optional[bool] = None
    commute: Optional[bool] = None


# ---------------------------------------------------------------------------
# List / search
# ---------------------------------------------------------------------------

@mcp.tool()
def intervals_list_activities(
    oldest: str,
    newest: Optional[str] = None,
    limit: Optional[int] = None,
    fields: Optional[str] = None,
    athlete_id_override: Optional[str] = None,
) -> str:
    """
    List activities for a date range from intervals.icu in descending date order.

    Args:
        oldest: Start date YYYY-MM-DD (inclusive, required).
        newest: End date YYYY-MM-DD (inclusive). Defaults to today.
        limit: Maximum number of activities to return.
        fields: Comma-separated list of fields to include (reduces response size).
        athlete_id_override: Athlete ID. Defaults to INTERVALS_ATHLETE_ID env var.
    """
    params: dict = {"oldest": oldest}
    if newest:
        params["newest"] = newest
    if limit:
        params["limit"] = limit
    if fields:
        params["fields"] = fields
    with get_client() as c:
        r = c.get(
            f"{BASE_URL}/athlete/{athlete_id(athlete_id_override)}/activities",
            params=params,
        )
    return handle_response(r)


@mcp.tool()
def intervals_search_activities(
    q: str,
    limit: Optional[int] = None,
    athlete_id_override: Optional[str] = None,
) -> str:
    """
    Search for intervals.icu activities by name or tag. Returns summary info.

    Args:
        q: Search query (name or tag).
        limit: Maximum number of results.
        athlete_id_override: Athlete ID. Defaults to INTERVALS_ATHLETE_ID env var.
    """
    params: dict = {"q": q}
    if limit:
        params["limit"] = limit
    with get_client() as c:
        r = c.get(
            f"{BASE_URL}/athlete/{athlete_id(athlete_id_override)}/activities/search",
            params=params,
        )
    return handle_response(r)


@mcp.tool()
def intervals_search_activities_full(
    q: str,
    limit: Optional[int] = None,
    athlete_id_override: Optional[str] = None,
) -> str:
    """
    Search for intervals.icu activities by name or tag. Returns full activity objects.

    Args:
        q: Search query (name or tag).
        limit: Maximum number of results.
        athlete_id_override: Athlete ID. Defaults to INTERVALS_ATHLETE_ID env var.
    """
    params: dict = {"q": q}
    if limit:
        params["limit"] = limit
    with get_client() as c:
        r = c.get(
            f"{BASE_URL}/athlete/{athlete_id(athlete_id_override)}/activities/search-full",
            params=params,
        )
    return handle_response(r)


@mcp.tool()
def intervals_interval_search_activities(
    min_secs: int,
    max_secs: int,
    min_intensity: float,
    max_intensity: float,
    activity_type: Optional[str] = None,
    min_reps: Optional[int] = None,
    max_reps: Optional[int] = None,
    limit: Optional[int] = None,
    athlete_id_override: Optional[str] = None,
) -> str:
    """
    Find intervals.icu activities that contain intervals matching duration and intensity criteria.

    Args:
        min_secs: Minimum interval duration in seconds.
        max_secs: Maximum interval duration in seconds.
        min_intensity: Minimum interval intensity (0-100 scale, e.g. 80).
        max_intensity: Maximum interval intensity (0-100 scale, e.g. 100).
        activity_type: Filter by sport type (e.g. 'Ride', 'Run').
        min_reps: Minimum number of matching intervals.
        max_reps: Maximum number of matching intervals.
        limit: Maximum number of activities to return.
        athlete_id_override: Athlete ID. Defaults to INTERVALS_ATHLETE_ID env var.
    """
    params: dict = {
        "minSecs": min_secs,
        "maxSecs": max_secs,
        "minIntensity": min_intensity,
        "maxIntensity": max_intensity,
    }
    if activity_type:
        params["type"] = activity_type
    if min_reps:
        params["minReps"] = min_reps
    if max_reps:
        params["maxReps"] = max_reps
    if limit:
        params["limit"] = limit
    with get_client() as c:
        r = c.get(
            f"{BASE_URL}/athlete/{athlete_id(athlete_id_override)}/activities/interval-search",
            params=params,
        )
    return handle_response(r)


@mcp.tool()
def intervals_get_activities_by_ids(
    ids: str,
    include_intervals: bool = False,
    athlete_id_override: Optional[str] = None,
) -> str:
    """
    Fetch multiple intervals.icu activities by ID in one call. Missing activities are ignored.

    Args:
        ids: Comma-separated activity IDs (e.g. 'A123,A456').
        include_intervals: Whether to include interval data in the response.
        athlete_id_override: Athlete ID. Defaults to INTERVALS_ATHLETE_ID env var.
    """
    params: dict = {}
    if include_intervals:
        params["intervals"] = "true"
    with get_client() as c:
        r = c.get(
            f"{BASE_URL}/athlete/{athlete_id(athlete_id_override)}/activities/{ids}",
            params=params,
        )
    return handle_response(r)


# ---------------------------------------------------------------------------
# Single activity CRUD
# ---------------------------------------------------------------------------

@mcp.tool()
def intervals_get_activity(activity_id: str, include_intervals: bool = False) -> str:
    """
    Get full details for a single intervals.icu activity.

    Args:
        activity_id: The activity ID (e.g. 'A12345678').
        include_intervals: Whether to include interval data in the response.
    """
    params: dict = {}
    if include_intervals:
        params["intervals"] = "true"
    with get_client() as c:
        r = c.get(f"{BASE_URL}/activity/{activity_id}", params=params)
    return handle_response(r)


@mcp.tool()
def intervals_update_activity(activity_id: str, updates: ActivityUpdate) -> str:
    """
    Update fields on an existing intervals.icu activity.

    Args:
        activity_id: The activity ID (e.g. 'A12345678').
        updates: Fields to update. All fields are optional — only provided fields
            are written. perceived_exertion 1-10; feel 1-5.
    """
    with get_client() as c:
        r = c.put(f"{BASE_URL}/activity/{activity_id}", json=updates.model_dump(exclude_none=True))
    return handle_response(r)


@mcp.tool()
def intervals_delete_activity(activity_id: str) -> str:
    """
    Delete an intervals.icu activity permanently.

    Args:
        activity_id: The activity ID (e.g. 'A12345678').
    """
    with get_client() as c:
        r = c.delete(f"{BASE_URL}/activity/{activity_id}")
    return handle_response(r) or "Deleted."


# ---------------------------------------------------------------------------
# Streams / intervals
# ---------------------------------------------------------------------------

@mcp.tool()
def intervals_get_activity_streams(
    activity_id: str,
    types: Optional[str] = None,
) -> str:
    """
    Get time-series data streams for an intervals.icu activity (power, HR, cadence, speed, etc.).

    Args:
        activity_id: The activity ID (e.g. 'A12345678').
        types: Comma-separated stream types to fetch. Common values:
            time, watts, heartrate, cadence, distance, altitude, latlng,
            velocity_smooth, temp. Omit to fetch all available streams.
    """
    params: dict = {}
    if types:
        params["types"] = types
    with get_client() as c:
        r = c.get(f"{BASE_URL}/activity/{activity_id}/streams", params=params)
    return handle_response(r)


@mcp.tool()
def intervals_get_activity_intervals(activity_id: str) -> str:
    """
    Get the computed intervals and laps for an intervals.icu activity.

    Args:
        activity_id: The activity ID (e.g. 'A12345678').
    """
    with get_client() as c:
        r = c.get(f"{BASE_URL}/activity/{activity_id}/intervals")
    return handle_response(r)


@mcp.tool()
def intervals_get_activity_interval_stats(
    activity_id: str,
    start_index: int,
    end_index: int,
) -> str:
    """
    Return interval-like stats for a portion of an intervals.icu activity (by stream index).

    Args:
        activity_id: The activity ID.
        start_index: Start stream index.
        end_index: End stream index.
    """
    with get_client() as c:
        r = c.get(
            f"{BASE_URL}/activity/{activity_id}/interval-stats",
            params={"start_index": start_index, "end_index": end_index},
        )
    return handle_response(r)


# ---------------------------------------------------------------------------
# Analysis / curves / histograms
# ---------------------------------------------------------------------------

@mcp.tool()
def intervals_get_activity_best_efforts(
    activity_id: str,
    stream: str,
    duration: Optional[int] = None,
    distance: Optional[float] = None,
    count: Optional[int] = None,
    min_value: Optional[float] = None,
) -> str:
    """
    Find best efforts within an intervals.icu activity for a given stream.

    Args:
        activity_id: The activity ID.
        stream: Stream to analyse, e.g. 'watts', 'heartrate', 'velocity_smooth'.
        duration: Duration in seconds to find best effort for.
        distance: Distance in metres to find best effort for.
        count: Number of best efforts to return.
        min_value: Minimum value threshold to count as an effort.
    """
    params: dict = {"stream": stream}
    if duration:
        params["duration"] = duration
    if distance:
        params["distance"] = distance
    if count:
        params["count"] = count
    if min_value:
        params["minValue"] = min_value
    with get_client() as c:
        r = c.get(f"{BASE_URL}/activity/{activity_id}/best-efforts", params=params)
    return handle_response(r)


@mcp.tool()
def intervals_get_activity_power_curve(activity_id: str, fatigue: Optional[bool] = None) -> str:
    """
    Get the mean-maximal power curve for an intervals.icu activity.

    Args:
        activity_id: The activity ID.
        fatigue: If true, include fatigue-adjusted curve.
    """
    params: dict = {}
    if fatigue is not None:
        params["fatigue"] = str(fatigue).lower()
    with get_client() as c:
        r = c.get(f"{BASE_URL}/activity/{activity_id}/power-curve", params=params)
    return handle_response(r)


@mcp.tool()
def intervals_get_activity_hr_curve(activity_id: str) -> str:
    """
    Get the mean-maximal heart rate curve for an intervals.icu activity.

    Args:
        activity_id: The activity ID.
    """
    with get_client() as c:
        r = c.get(f"{BASE_URL}/activity/{activity_id}/hr-curve")
    return handle_response(r)


@mcp.tool()
def intervals_get_activity_pace_curve(activity_id: str, gap: Optional[bool] = None) -> str:
    """
    Get the mean-maximal pace curve for an intervals.icu activity.

    Args:
        activity_id: The activity ID.
        gap: If true, use gradient adjusted pace.
    """
    params: dict = {}
    if gap is not None:
        params["gap"] = str(gap).lower()
    with get_client() as c:
        r = c.get(f"{BASE_URL}/activity/{activity_id}/pace-curve", params=params)
    return handle_response(r)


@mcp.tool()
def intervals_get_activity_power_histogram(
    activity_id: str,
    bucket_size: Optional[int] = None,
) -> str:
    """
    Get the power histogram for an intervals.icu activity.

    Args:
        activity_id: The activity ID.
        bucket_size: Histogram bucket width in watts.
    """
    params: dict = {}
    if bucket_size:
        params["bucketSize"] = bucket_size
    with get_client() as c:
        r = c.get(f"{BASE_URL}/activity/{activity_id}/power-histogram", params=params)
    return handle_response(r)


@mcp.tool()
def intervals_get_activity_hr_histogram(
    activity_id: str,
    bucket_size: Optional[int] = None,
) -> str:
    """
    Get the heart rate histogram for an intervals.icu activity.

    Args:
        activity_id: The activity ID.
        bucket_size: Histogram bucket width in bpm.
    """
    params: dict = {}
    if bucket_size:
        params["bucketSize"] = bucket_size
    with get_client() as c:
        r = c.get(f"{BASE_URL}/activity/{activity_id}/hr-histogram", params=params)
    return handle_response(r)


@mcp.tool()
def intervals_get_activity_pace_histogram(activity_id: str) -> str:
    """
    Get the pace histogram for an intervals.icu activity.

    Args:
        activity_id: The activity ID.
    """
    with get_client() as c:
        r = c.get(f"{BASE_URL}/activity/{activity_id}/pace-histogram")
    return handle_response(r)


@mcp.tool()
def intervals_get_activity_power_vs_hr(activity_id: str) -> str:
    """
    Get power vs heart rate data for an intervals.icu activity (useful for aerobic decoupling analysis).

    Args:
        activity_id: The activity ID.
    """
    with get_client() as c:
        r = c.get(f"{BASE_URL}/activity/{activity_id}/power-vs-hr")
    return handle_response(r)


@mcp.tool()
def intervals_get_activity_time_at_hr(activity_id: str) -> str:
    """
    Get time-at-heart-rate zone data for an intervals.icu activity.

    Args:
        activity_id: The activity ID.
    """
    with get_client() as c:
        r = c.get(f"{BASE_URL}/activity/{activity_id}/time-at-hr")
    return handle_response(r)


# ---------------------------------------------------------------------------
# Map / weather / segments
# ---------------------------------------------------------------------------

@mcp.tool()
def intervals_get_activity_map(
    activity_id: str,
    bounds_only: bool = False,
    include_weather: bool = False,
) -> str:
    """
    Get map data (route coordinates and metadata) for an intervals.icu activity.

    Args:
        activity_id: The activity ID.
        bounds_only: Return only the bounding box, not the full route.
        include_weather: Include weather data in the response.
    """
    params: dict = {}
    if bounds_only:
        params["boundsOnly"] = "true"
    if include_weather:
        params["weather"] = "true"
    with get_client() as c:
        r = c.get(f"{BASE_URL}/activity/{activity_id}/map", params=params)
    return handle_response(r)


@mcp.tool()
def intervals_get_activity_weather(activity_id: str) -> str:
    """
    Get weather summary for an intervals.icu activity.

    Args:
        activity_id: The activity ID.
    """
    with get_client() as c:
        r = c.get(f"{BASE_URL}/activity/{activity_id}/weather-summary")
    return handle_response(r)


@mcp.tool()
def intervals_get_activity_segments(activity_id: str) -> str:
    """
    Get Strava/local segments matched in an intervals.icu activity.

    Args:
        activity_id: The activity ID.
    """
    with get_client() as c:
        r = c.get(f"{BASE_URL}/activity/{activity_id}/segments")
    return handle_response(r)


# ---------------------------------------------------------------------------
# Messages (comments)
# ---------------------------------------------------------------------------

@mcp.tool()
def intervals_get_activity_messages(
    activity_id: str,
    limit: Optional[int] = None,
    since_id: Optional[int] = None,
) -> str:
    """
    List all comments/messages on an intervals.icu activity.

    Args:
        activity_id: The activity ID.
        limit: Maximum number of messages to return.
        since_id: Return only messages with ID greater than this value.
    """
    params: dict = {}
    if limit:
        params["limit"] = limit
    if since_id:
        params["sinceId"] = since_id
    with get_client() as c:
        r = c.get(f"{BASE_URL}/activity/{activity_id}/messages", params=params)
    return handle_response(r)


@mcp.tool()
def intervals_post_activity_message(activity_id: str, message: str) -> str:
    """
    Add a comment/message to an intervals.icu activity.

    Args:
        activity_id: The activity ID.
        message: The comment text to post.
    """
    with get_client() as c:
        r = c.post(f"{BASE_URL}/activity/{activity_id}/messages", json={"message": message})
    return handle_response(r)
