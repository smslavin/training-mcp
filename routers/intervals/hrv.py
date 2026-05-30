import csv
import io
import json
from datetime import date
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
