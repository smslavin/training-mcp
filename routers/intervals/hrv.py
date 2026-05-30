import csv
import io
import json
from datetime import date, timedelta
from statistics import mean, stdev
from typing import Optional

from app import mcp
from client_dropbox import get_csv_content

KEEP_COLUMNS = [
    "date",
    "HR",
    "rMSSD",
    "SDNN",
    "HRV4T_Recovery_Points",
    "sleep_quality",
    "sleep_time",
    "mental_energy",
    "muscle_soreness",
    "fatigue",
    "physical_condition",
    "training",
    "trainingRPE",
    "trainingTSS",
    "advice",
]


def _parse_value(v: str):
    v = v.strip()
    if v in ("-", ""):
        return None
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        pass
    return v


@mcp.tool()
def get_hrv_data(
    after: Optional[str] = None,
    before: Optional[str] = None,
    include_rest_days: bool = False,
) -> str:
    """
    Get HRV4Training daily data. Reads from a local CSV directory or Dropbox
    app folder depending on what is configured in .env.
    Returns HRV metrics (rMSSD, SDNN), recovery score, sleep, and subjective
    wellness markers (fatigue, muscle soreness, mental energy).

    Args:
        after: Start date YYYY-MM-DD (inclusive).
        before: End date YYYY-MM-DD (inclusive).
        include_rest_days: Include days with no HRV measurement (rMSSD is null).
            Default False returns only days with an actual reading.
    """
    after_d = date.fromisoformat(after) if after else None
    before_d = date.fromisoformat(before) if before else None

    content = get_csv_content().replace("\r\n", "\n").replace("\r", "\n")
    reader = csv.DictReader(io.StringIO(content))
    reader.fieldnames = [h.strip() for h in reader.fieldnames]

    rows = []
    for row in reader:
        row_date_str = row["date"].split(" ")[0]
        try:
            row_date = date.fromisoformat(row_date_str)
        except ValueError:
            continue

        if after_d and row_date < after_d:
            continue
        if before_d and row_date > before_d:
            continue

        record = {col: _parse_value(row.get(col, "-")) for col in KEEP_COLUMNS}
        record["date"] = row_date_str

        if not include_rest_days and record.get("rMSSD") is None:
            continue

        rows.append(record)

    return json.dumps(rows)


@mcp.tool()
def hrv4t_trend_alert(
    metric: str,
    window_days: int = 28,
    threshold_stddevs: float = 1.5,
) -> str:
    """
    Check whether the most recent HRV4Training reading for a metric is a meaningful
    deviation from the rolling baseline.

    Reads from the HRV4Training CSV (local directory or Dropbox). Computes mean
    and standard deviation over the past window_days, then reports whether the most
    recent reading falls outside the threshold band. Useful for flagging changes in
    HRV, fatigue, soreness, sleep quality, and other subjective markers.

    Args:
        metric: CSV column to analyse. Common values: rMSSD, SDNN,
            HRV4T_Recovery_Points, sleep_quality, sleep_time, mental_energy,
            muscle_soreness, fatigue, physical_condition.
        window_days: Number of days to include in the rolling window (default 28).
        threshold_stddevs: Deviation threshold in standard deviations (default 1.5).
    """
    today = date.today()
    after_d = today - timedelta(days=window_days)

    content = get_csv_content().replace("\r\n", "\n").replace("\r", "\n")
    reader = csv.DictReader(io.StringIO(content))
    reader.fieldnames = [h.strip() for h in reader.fieldnames]

    readings: list[tuple[str, float]] = []
    for row in reader:
        row_date_str = row.get("date", "").split(" ")[0]
        try:
            row_date = date.fromisoformat(row_date_str)
        except ValueError:
            continue
        if row_date < after_d or row_date > today:
            continue
        val = _parse_value(row.get(metric, "-"))
        if val is None or not isinstance(val, (int, float)):
            continue
        readings.append((row_date_str, float(val)))

    readings.sort(key=lambda x: x[0])

    if len(readings) < 3:
        return (
            f"Not enough data: found {len(readings)} non-null reading(s) for "
            f"'{metric}' in the past {window_days} days (need at least 3)."
        )

    most_recent_date, most_recent_value = readings[-1]
    baseline_values = [v for _, v in readings[:-1]]
    oldest = readings[0][0]

    baseline_mean = mean(baseline_values)
    baseline_std = stdev(baseline_values)

    if baseline_std == 0:
        return (
            f"HRV4Training trend: {metric}\n"
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
        f"HRV4Training trend: {metric}",
        f"  Window:        {window_days} days ({oldest} to {today.isoformat()})",
        f"  Readings:      {len(readings)} non-null entries",
        f"  Baseline:      mean {baseline_mean:.2f}, std {baseline_std:.2f}",
        f"  Normal band:   {lower:.2f} – {upper:.2f}  (±{threshold_stddevs} std)",
        f"",
        f"  Most recent:   {most_recent_value:.2f} on {most_recent_date}",
        f"  Deviation:     {abs(deviation):.2f} std {direction} mean",
        f"  Status:        {status}",
    ])
