from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app import mcp
from client_dropbox import load_hrv_by_date
from client_intervals import BASE_URL as INTERVALS_URL
from client_intervals import athlete_id, get_intervals_client, handle_intervals_response
from client_strava import BASE_URL as STRAVA_URL
from client_strava import get_strava_client, handle_strava_response


def _pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return float("nan")
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den_x = sum((x - mean_x) ** 2 for x in xs) ** 0.5
    den_y = sum((y - mean_y) ** 2 for y in ys) ** 0.5
    if den_x == 0 or den_y == 0:
        return float("nan")
    return num / (den_x * den_y)


def _interpret_r(r: float) -> str:
    if r != r:  # nan check
        return "insufficient data"
    a = abs(r)
    direction = "positive" if r > 0 else "negative"
    if a >= 0.7:
        strength = "strong"
    elif a >= 0.4:
        strength = "moderate"
    elif a >= 0.2:
        strength = "weak"
    else:
        strength = "negligible"
    return f"{strength} {direction} (r={r:.3f})"


def _activity_local_date(act: dict) -> str:
    """Return YYYY-MM-DD in the activity's local timezone.

    start_date_local may come back as a UTC-offset string (e.g.
    "2024-01-14T20:00:00+00:00") rather than genuine local time.  When it
    carries timezone info we convert to the activity's IANA timezone so the
    calendar date matches the athlete's local day, not the UTC day.
    """
    raw = act.get("start_date_local", "")
    if not raw:
        return ""
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return raw[:10]
    if dt.tzinfo is None:
        return raw[:10]
    tz_name = act.get("timezone", "")
    if tz_name:
        try:
            dt = dt.astimezone(ZoneInfo(tz_name))
        except (ZoneInfoNotFoundError, KeyError):
            pass
    return dt.strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# correlate_hrv_with_performance
# ---------------------------------------------------------------------------

@mcp.tool()
def correlate_hrv_with_performance(
    after: str,
    before: Optional[str] = None,
    athlete_id_override: Optional[str] = None,
) -> str:
    """
    Correlate daily HRV (rMSSD from HRV4Training via Dropbox) with same-day
    training performance over a date range.

    For each day that has both an HRV reading and at least one activity, pairs
    the rMSSD value with normalized power and HR efficiency (NP / avg HR).
    Returns a day-by-day table and Pearson correlation coefficients for both
    pairings.

    Higher rMSSD generally indicates better recovery. A positive correlation
    with NP and HR efficiency suggests the HRV signal is tracking readiness well.

    Args:
        after: Start date YYYY-MM-DD (inclusive).
        before: End date YYYY-MM-DD (inclusive). Defaults to today.
        athlete_id_override: intervals.icu athlete ID override.
    """
    aid = athlete_id(athlete_id_override)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    newest = before or today

    hrv_by_date = load_hrv_by_date(after=after, before=newest)

    with get_intervals_client() as c:
        ra = c.get(
            f"{INTERVALS_URL}/athlete/{aid}/activities",
            params={"oldest": after, "newest": newest, "fields": "start_date_local,timezone,average_hr,normalized_power"},
        )
    handle_intervals_response(ra)

    # Group activities by local date, pick the one with the highest NP on that day
    activities_by_date: dict[str, dict] = {}
    for act in ra.json():
        d = _activity_local_date(act)
        np_ = act.get("normalized_power") or 0
        hr = act.get("average_hr") or 0
        if np_ > 0 and hr > 0:
            existing = activities_by_date.get(d)
            if existing is None or np_ > (existing.get("normalized_power") or 0):
                activities_by_date[d] = act

    paired_dates = sorted(set(hrv_by_date) & set(activities_by_date))
    if len(paired_dates) < 3:
        return (
            f"Not enough paired days: found {len(paired_dates)} day(s) with both HRV "
            f"and a power activity in {after} – {newest} (need at least 3)."
        )

    hrv_vals, np_vals, eff_vals = [], [], []
    rows = ["Date         rMSSD   NP (w)   HR eff (NP/HR)"]
    rows.append("-" * 47)

    for d in paired_dates:
        hrv = hrv_by_date[d]
        act = activities_by_date[d]
        np_ = float(act["normalized_power"])
        hr = float(act["average_hr"])
        eff = np_ / hr
        hrv_vals.append(hrv)
        np_vals.append(np_)
        eff_vals.append(eff)
        rows.append(f"{d}   {hrv:5.1f}  {np_:6.1f}   {eff:.3f}")

    r_hrv_np = _pearson(hrv_vals, np_vals)
    r_hrv_eff = _pearson(hrv_vals, eff_vals)

    rows.append("")
    rows.append(f"Paired days:          {len(paired_dates)}")
    rows.append(f"HRV vs NP:            {_interpret_r(r_hrv_np)}")
    rows.append(f"HRV vs HR efficiency: {_interpret_r(r_hrv_eff)}")

    return "\n".join(rows)


# ---------------------------------------------------------------------------
# training_load_vs_sleep
# ---------------------------------------------------------------------------

@mcp.tool()
def training_load_vs_sleep(
    after: str,
    before: Optional[str] = None,
    athlete_id_override: Optional[str] = None,
) -> str:
    """
    Correlate training load metrics (CTL, ATL, form) with sleep quality over a date range.

    Fetches daily wellness entries from intervals.icu and joins CTL (fitness),
    ATL (fatigue), and form (TSB) with sleep score. Returns a day-by-day table
    and Pearson correlations for each pairing.

    Useful for identifying how accumulated load affects sleep quality, and whether
    there is a lag between hard training blocks and sleep degradation.

    Args:
        after: Start date YYYY-MM-DD (inclusive).
        before: End date YYYY-MM-DD (inclusive). Defaults to today.
        athlete_id_override: intervals.icu athlete ID override.
    """
    aid = athlete_id(athlete_id_override)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    newest = before or today

    with get_intervals_client() as c:
        r = c.get(
            f"{INTERVALS_URL}/athlete/{aid}/wellness",
            params={"oldest": after, "newest": newest},
        )
    handle_intervals_response(r)

    entries = [
        e for e in r.json()
        if e.get("sleepScore") is not None
        and any(e.get(k) is not None for k in ("ctl", "atl", "form"))
    ]

    if len(entries) < 3:
        return (
            f"Not enough data: found {len(entries)} day(s) with both sleep score and "
            f"fitness metrics in {after} – {newest} (need at least 3)."
        )

    sleep_vals = [float(e["sleepScore"]) for e in entries]
    ctl_vals   = [float(e["ctl"])  if e.get("ctl")  is not None else None for e in entries]
    atl_vals   = [float(e["atl"])  if e.get("atl")  is not None else None for e in entries]
    form_vals  = [float(e["form"]) if e.get("form") is not None else None for e in entries]

    rows = ["Date         Sleep   CTL    ATL    Form"]
    rows.append("-" * 44)
    for e, ctl, atl, form in zip(entries, ctl_vals, atl_vals, form_vals):
        ctl_s  = f"{ctl:5.1f}" if ctl is not None else "  n/a"
        atl_s  = f"{atl:5.1f}" if atl is not None else "  n/a"
        form_s = f"{form:5.1f}" if form is not None else "  n/a"
        rows.append(f"{e['id']}   {e['sleepScore']:5.1f}  {ctl_s}  {atl_s}  {form_s}")

    def _corr_line(label, vals):
        pairs = [(s, v) for s, v in zip(sleep_vals, vals) if v is not None]
        if len(pairs) < 3:
            return f"{label}: insufficient data"
        xs, ys = zip(*pairs)
        return f"{label}: {_interpret_r(_pearson(list(xs), list(ys)))}"

    rows.append("")
    rows.append(f"Days with sleep + fitness data: {len(entries)}")
    rows.append(_corr_line("Sleep vs CTL (fitness)", ctl_vals))
    rows.append(_corr_line("Sleep vs ATL (fatigue)", atl_vals))
    rows.append(_corr_line("Sleep vs Form (TSB)   ", form_vals))

    return "\n".join(rows)


# ---------------------------------------------------------------------------
# fitness_vs_segment_prs
# ---------------------------------------------------------------------------

@mcp.tool()
def fitness_vs_segment_prs(
    segment_id: int,
    after: Optional[str] = None,
    before: Optional[str] = None,
    athlete_id_override: Optional[str] = None,
) -> str:
    """
    Correlate intervals.icu fitness metrics (CTL, ATL, form) with Strava segment
    effort times on a given segment.

    Fetches all of the athlete's efforts on the segment from Strava, then looks up
    CTL, ATL, and form (TSB) from intervals.icu wellness for each effort date. Returns
    a table and Pearson correlations between each fitness metric and elapsed time.

    A negative correlation between CTL and elapsed time (higher fitness → faster time)
    supports the fitness model as a predictor of segment performance.

    Args:
        segment_id: The Strava segment ID (integer).
        after: Filter to efforts after this date YYYY-MM-DD.
        before: Filter to efforts before this date YYYY-MM-DD.
        athlete_id_override: intervals.icu athlete ID override.
    """
    aid = athlete_id(athlete_id_override)

    # Fetch segment efforts from Strava
    params: dict = {"segment_id": segment_id, "per_page": 200}
    if after:
        dt = datetime.strptime(after, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        params["start_date_local"] = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    if before:
        dt = datetime.strptime(before, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        params["end_date_local"] = dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    with get_strava_client() as c:
        rs = c.get(f"{STRAVA_URL}/segment_efforts", params=params)
    handle_strava_response(rs)
    efforts = rs.json()

    if not efforts:
        return f"No segment efforts found for segment {segment_id}."

    # Collect unique effort dates for wellness lookup
    effort_dates = sorted({_activity_local_date(e) for e in efforts})
    oldest = effort_dates[0]
    newest = effort_dates[-1]

    with get_intervals_client() as c:
        rw = c.get(
            f"{INTERVALS_URL}/athlete/{aid}/wellness",
            params={"oldest": oldest, "newest": newest},
        )
    handle_intervals_response(rw)
    wellness_by_date = {e["id"]: e for e in rw.json()}

    # Build joined rows — one row per effort, using wellness from the same date
    rows_data = []
    for e in efforts:
        d = _activity_local_date(e)
        w = wellness_by_date.get(d, {})
        rows_data.append({
            "date": d,
            "elapsed": e["elapsed_time"],
            "ctl":  w.get("ctl"),
            "atl":  w.get("atl"),
            "form": w.get("form"),
        })

    rows_data.sort(key=lambda x: x["date"])

    segment_name = efforts[0].get("name", f"Segment {segment_id}")
    rows = [f"Segment: {segment_name}  (id={segment_id})"]
    rows.append(f"Efforts: {len(rows_data)}  ({oldest} – {newest})")
    rows.append("")
    rows.append("Date         Time     CTL    ATL    Form")
    rows.append("-" * 46)

    time_vals, ctl_vals, atl_vals, form_vals = [], [], [], []
    for row in rows_data:
        mm, ss = divmod(row["elapsed"], 60)
        time_str = f"{mm}:{ss:02d}"
        ctl_s  = f"{row['ctl']:5.1f}"  if row["ctl"]  is not None else "  n/a"
        atl_s  = f"{row['atl']:5.1f}"  if row["atl"]  is not None else "  n/a"
        form_s = f"{row['form']:5.1f}" if row["form"] is not None else "  n/a"
        rows.append(f"{row['date']}   {time_str:>6}   {ctl_s}  {atl_s}  {form_s}")
        time_vals.append(float(row["elapsed"]))
        ctl_vals.append(row["ctl"])
        atl_vals.append(row["atl"])
        form_vals.append(row["form"])

    def _corr_line(label, vals):
        pairs = [(t, v) for t, v in zip(time_vals, vals) if v is not None]
        if len(pairs) < 3:
            return f"{label}: insufficient data"
        ts, vs = zip(*pairs)
        return f"{label}: {_interpret_r(_pearson(list(ts), list(vs)))}"

    rows.append("")
    rows.append(_corr_line("Time vs CTL (fitness)", ctl_vals))
    rows.append(_corr_line("Time vs ATL (fatigue)", atl_vals))
    rows.append(_corr_line("Time vs Form (TSB)   ", form_vals))

    return "\n".join(rows)
