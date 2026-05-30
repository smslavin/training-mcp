import csv
import glob
import io
import json
import os
import time
from datetime import date

import httpx
from dotenv import load_dotenv, set_key

ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(ENV_PATH)


def _cfg(key: str) -> str:
    return os.getenv(key, "")


def _dropbox_access_token() -> str:
    refresh_token = _cfg("DROPBOX_REFRESH_TOKEN")
    if not refresh_token:
        return _cfg("DROPBOX_ACCESS_TOKEN")

    expires_at = int(_cfg("DROPBOX_TOKEN_EXPIRES_AT") or "0")
    if time.time() < expires_at - 60:
        return _cfg("DROPBOX_ACCESS_TOKEN")

    r = httpx.post(
        "https://api.dropboxapi.com/oauth2/token",
        data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        auth=(_cfg("DROPBOX_APP_KEY"), _cfg("DROPBOX_APP_SECRET")),
    )
    if r.is_error:
        raise RuntimeError(f"Dropbox token refresh failed: {r.status_code} {r.text}")

    data = r.json()
    access_token = data["access_token"]
    new_expires_at = int(time.time()) + int(data.get("expires_in", 14400))
    set_key(ENV_PATH, "DROPBOX_ACCESS_TOKEN", access_token)
    set_key(ENV_PATH, "DROPBOX_TOKEN_EXPIRES_AT", str(new_expires_at))
    os.environ["DROPBOX_ACCESS_TOKEN"] = access_token
    os.environ["DROPBOX_TOKEN_EXPIRES_AT"] = str(new_expires_at)
    return access_token


def _fetch_dropbox_csv() -> str:
    """Download the most recently modified CSV from the Dropbox app folder."""
    token = _dropbox_access_token()

    r = httpx.post(
        "https://api.dropboxapi.com/2/files/list_folder",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"path": ""},
    )
    if r.is_error:
        raise RuntimeError(f"Dropbox list_folder failed: {r.status_code} {r.text}")

    entries = [
        e for e in r.json().get("entries", [])
        if e[".tag"] == "file" and e["name"].endswith(".csv")
    ]
    if not entries:
        raise RuntimeError("No CSV files found in Dropbox app folder")

    latest = max(entries, key=lambda e: e["server_modified"])

    r = httpx.post(
        "https://content.dropboxapi.com/2/files/download",
        headers={
            "Authorization": f"Bearer {token}",
            "Dropbox-API-Arg": json.dumps({"path": latest["id"]}),
        },
    )
    if r.is_error:
        raise RuntimeError(f"Dropbox download failed: {r.status_code} {r.text}")

    return r.text


def get_csv_content() -> str:
    """Return HRV4Training CSV content — local directory first, then Dropbox."""
    local_dir = _cfg("HRV4TRAINING_CSV_DIR")
    if local_dir:
        candidates = glob.glob(os.path.join(local_dir, "*.csv"))
        if not candidates:
            raise RuntimeError(f"No CSV files found in {local_dir}")
        path = max(candidates, key=os.path.getmtime)
        with open(path, encoding="utf-8") as f:
            return f.read()

    if _cfg("DROPBOX_APP_KEY"):
        return _fetch_dropbox_csv()

    raise RuntimeError(
        "No HRV source configured. Set HRV4TRAINING_CSV_DIR or DROPBOX_APP_KEY in .env"
    )


def load_hrv_by_date(after: str | None = None, before: str | None = None) -> dict[str, float]:
    """Return {YYYY-MM-DD: rMSSD} for days with a valid HRV reading in the date range."""
    after_d = date.fromisoformat(after) if after else None
    before_d = date.fromisoformat(before) if before else None

    content = get_csv_content().replace("\r\n", "\n").replace("\r", "\n")
    reader = csv.DictReader(io.StringIO(content))
    reader.fieldnames = [h.strip() for h in reader.fieldnames]

    result: dict[str, float] = {}
    for row in reader:
        raw_date = row.get("date", "").split(" ")[0]
        try:
            row_date = date.fromisoformat(raw_date)
        except ValueError:
            continue

        if after_d and row_date < after_d:
            continue
        if before_d and row_date > before_d:
            continue

        rmssd_str = (row.get("rMSSD") or "").strip()
        if rmssd_str in ("-", ""):
            continue
        try:
            result[raw_date] = float(rmssd_str)
        except ValueError:
            continue

    return result
