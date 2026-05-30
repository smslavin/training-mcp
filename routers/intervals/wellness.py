from datetime import date, timedelta
from statistics import mean, stdev
from typing import Optional

from pydantic import BaseModel

from app import mcp
from client_intervals import BASE_URL, athlete_id, get_client, handle_response


class WellnessUpdate(BaseModel):
    weight: Optional[float] = None
    restingHR: Optional[int] = None
    hrv: Optional[float] = None
    hrvSDNN: Optional[float] = None
    mentalLoad: Optional[int] = None
    physicalLoad: Optional[int] = None
    sleepSecs: Optional[int] = None
    sleepScore: Optional[float] = None
    sleepQuality: Optional[int] = None
    mood: Optional[int] = None
    motivation: Optional[int] = None
    soreness: Optional[int] = None
    fatigue: Optional[int] = None
    stress: Optional[int] = None
    hydration: Optional[int] = None
    kcalConsumed: Optional[int] = None
    notes: Optional[str] = None


class WellnessUpdateItem(WellnessUpdate):
    id: str  # date YYYY-MM-DD


@mcp.tool()
def intervals_list_wellness(
    oldest: str,
    newest: str,
    athlete_id_override: Optional[str] = None,
) -> str:
    """
    Retrieve wellness entries for a date range from intervals.icu.

    Args:
        oldest: Start date YYYY-MM-DD (inclusive).
        newest: End date YYYY-MM-DD (inclusive).
        athlete_id_override: Athlete ID. Defaults to INTERVALS_ATHLETE_ID env var.
    """
    with get_client() as c:
        r = c.get(
            f"{BASE_URL}/athlete/{athlete_id(athlete_id_override)}/wellness",
            params={"oldest": oldest, "newest": newest},
        )
    return handle_response(r)


@mcp.tool()
def intervals_get_wellness(date: str, athlete_id_override: Optional[str] = None) -> str:
    """
    Retrieve a single wellness entry for a specific date from intervals.icu.

    Args:
        date: Date YYYY-MM-DD.
        athlete_id_override: Athlete ID. Defaults to INTERVALS_ATHLETE_ID env var.
    """
    with get_client() as c:
        r = c.get(f"{BASE_URL}/athlete/{athlete_id(athlete_id_override)}/wellness/{date}")
    return handle_response(r)


@mcp.tool()
def intervals_update_wellness(
    date: str,
    updates: WellnessUpdate,
    athlete_id_override: Optional[str] = None,
) -> str:
    """
    Create or update a wellness entry for a specific date in intervals.icu.

    Args:
        date: Date YYYY-MM-DD.
        updates: Wellness fields to set. All fields are optional — only provided
            fields are written. weight in kg; sleepSecs in seconds; sleepQuality,
            mood, motivation, soreness, fatigue, stress, hydration on a 1-5 scale;
            mentalLoad and physicalLoad on a 0-100 scale.
        athlete_id_override: Athlete ID. Defaults to INTERVALS_ATHLETE_ID env var.
    """
    with get_client() as c:
        r = c.put(
            f"{BASE_URL}/athlete/{athlete_id(athlete_id_override)}/wellness/{date}",
            json=updates.model_dump(exclude_none=True),
        )
    return handle_response(r)


@mcp.tool()
def intervals_bulk_update_wellness(
    updates: list[WellnessUpdateItem],
    athlete_id_override: Optional[str] = None,
) -> str:
    """
    Update multiple intervals.icu wellness records in one call.

    Args:
        updates: List of wellness entries to write. Each entry must include an 'id'
            field set to the date (YYYY-MM-DD) plus any wellness fields to set.
            All wellness fields are optional; only provided fields are written.
        athlete_id_override: Athlete ID. Defaults to INTERVALS_ATHLETE_ID env var.
    """
    data = [item.model_dump(exclude_none=True) for item in updates]
    with get_client() as c:
        r = c.put(
            f"{BASE_URL}/athlete/{athlete_id(athlete_id_override)}/wellness-bulk",
            json=data,
        )
    return handle_response(r)


@mcp.tool()
def intervals_wellness_trend_alert(
    metric: str,
    window_days: int = 28,
    threshold_stddevs: float = 1.5,
    athlete_id_override: Optional[str] = None,
) -> str:
    """
    Check whether the most recent wellness reading for a metric is a meaningful
    deviation from the rolling baseline.

    Fetches the past window_days of entries, computes mean and standard deviation
    from all readings except the most recent, then reports whether the most recent
    reading falls outside the threshold band. Useful for flagging early signs of
    overtraining, illness, or incomplete recovery.

    Args:
        metric: Wellness field to analyse. Common values: hrv, hrvSDNN, restingHR,
            sleepScore, sleepSecs, sleepQuality, mood, motivation, soreness,
            fatigue, stress, hydration, weight.
        window_days: Number of days to include in the rolling window (default 28).
        threshold_stddevs: Deviation threshold in standard deviations (default 1.5).
        athlete_id_override: Athlete ID. Defaults to INTERVALS_ATHLETE_ID env var.
    """
    today = date.today()
    oldest = (today - timedelta(days=window_days)).isoformat()
    newest = today.isoformat()

    with get_client() as c:
        r = c.get(
            f"{BASE_URL}/athlete/{athlete_id(athlete_id_override)}/wellness",
            params={"oldest": oldest, "newest": newest},
        )
    handle_response(r)
    entries = r.json()

    readings = [
        (entry.get("id", ""), float(entry[metric]))
        for entry in entries
        if entry.get(metric) is not None
    ]

    if len(readings) < 3:
        return (
            f"Not enough data: found {len(readings)} non-null reading(s) for "
            f"'{metric}' in the past {window_days} days (need at least 3)."
        )

    most_recent_date, most_recent_value = readings[-1]
    baseline_values = [v for _, v in readings[:-1]]

    baseline_mean = mean(baseline_values)
    baseline_std = stdev(baseline_values)

    if baseline_std == 0:
        return (
            f"Wellness trend: {metric}\n"
            f"  All {len(baseline_values)} baseline readings are identical ({baseline_mean:.2f}). "
            f"Cannot compute a meaningful deviation."
        )

    deviation = (most_recent_value - baseline_mean) / baseline_std
    direction = "above" if deviation > 0 else "below"
    flagged = abs(deviation) >= threshold_stddevs
    status = "FLAGGED" if flagged else "within normal range"

    lower = baseline_mean - threshold_stddevs * baseline_std
    upper = baseline_mean + threshold_stddevs * baseline_std

    return "\n".join([
        f"Wellness trend: {metric}",
        f"  Window:        {window_days} days ({oldest} to {newest})",
        f"  Readings:      {len(readings)} non-null entries",
        f"  Baseline:      mean {baseline_mean:.2f}, std {baseline_std:.2f}",
        f"  Normal band:   {lower:.2f} – {upper:.2f}  (±{threshold_stddevs} std)",
        f"",
        f"  Most recent:   {most_recent_value:.2f} on {most_recent_date}",
        f"  Deviation:     {abs(deviation):.2f} std {direction} mean",
        f"  Status:        {status}",
    ])
