import os
import time

import httpx
from dotenv import load_dotenv, set_key

ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(ENV_PATH)

BASE_URL = "https://www.strava.com/api/v3"
TOKEN_URL = "https://www.strava.com/oauth/token"


def _refresh_token() -> str:
    with httpx.Client() as c:
        r = c.post(TOKEN_URL, data={
            "client_id": os.getenv("STRAVA_CLIENT_ID"),
            "client_secret": os.getenv("STRAVA_CLIENT_SECRET"),
            "refresh_token": os.getenv("STRAVA_REFRESH_TOKEN"),
            "grant_type": "refresh_token",
        })
    if r.is_error:
        raise RuntimeError(f"Strava token refresh failed: {r.status_code} {r.text}")

    data = r.json()
    access_token = data["access_token"]
    set_key(ENV_PATH, "STRAVA_ACCESS_TOKEN", access_token)
    set_key(ENV_PATH, "STRAVA_REFRESH_TOKEN", data["refresh_token"])
    set_key(ENV_PATH, "STRAVA_TOKEN_EXPIRES_AT", str(data["expires_at"]))
    os.environ["STRAVA_ACCESS_TOKEN"] = access_token
    os.environ["STRAVA_REFRESH_TOKEN"] = data["refresh_token"]
    os.environ["STRAVA_TOKEN_EXPIRES_AT"] = str(data["expires_at"])
    return access_token


def _access_token() -> str:
    if time.time() >= int(os.getenv("STRAVA_TOKEN_EXPIRES_AT", "0")):
        return _refresh_token()
    return os.getenv("STRAVA_ACCESS_TOKEN")


def get_strava_client() -> httpx.Client:
    return httpx.Client(
        headers={"Authorization": f"Bearer {_access_token()}", "Accept": "application/json"},
        timeout=30,
    )


def handle_strava_response(r: httpx.Response) -> str:
    if r.is_error:
        try:
            detail = r.json().get("message") or r.json()
        except Exception:
            detail = r.text or r.reason_phrase
        raise RuntimeError(f"Strava HTTP {r.status_code}: {detail}")
    return r.text


# Aliases so strava routers can import get_client / handle_response unchanged
get_client = get_strava_client
handle_response = handle_strava_response
