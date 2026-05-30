import os

import httpx
from dotenv import load_dotenv

ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(ENV_PATH)

ATHLETE_ID = os.getenv("INTERVALS_ATHLETE_ID")
API_KEY = os.getenv("INTERVALS_API_KEY")
BASE_URL = "https://intervals.icu/api/v1"


def get_intervals_client() -> httpx.Client:
    return httpx.Client(
        auth=("API_KEY", API_KEY),
        headers={"Accept": "application/json"},
        timeout=30,
    )


def athlete_id(override: str | None = None) -> str:
    return override or ATHLETE_ID


def handle_intervals_response(r: httpx.Response) -> str:
    if r.is_error:
        try:
            detail = r.json().get("error") or r.json()
        except Exception:
            detail = r.text or r.reason_phrase
        raise RuntimeError(f"intervals.icu HTTP {r.status_code}: {detail}")
    return r.text


# Aliases so intervals routers can import get_client / handle_response unchanged
get_client = get_intervals_client
handle_response = handle_intervals_response
