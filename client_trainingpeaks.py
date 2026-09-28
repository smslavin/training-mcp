import os
import time

import httpx
from dotenv import load_dotenv

ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(ENV_PATH)

BASE_URL = "https://tpapi.trainingpeaks.com"
AUTH_COOKIE_NAME = "Production_tpAuth"
EXPIRED_COOKIE_HELP = (
    f"Copy a fresh {AUTH_COOKIE_NAME} cookie from app.trainingpeaks.com into "
    "TP_AUTH_COOKIE in .env (see README → TrainingPeaks)."
)

# TrainingPeaks has no public athlete API. This is the private API its web app
# uses: the login cookie buys a one-hour bearer token from /users/v3/token.
_token: str | None = None
_token_expires_at: float = 0
_user_id: str | None = None


def auth_cookie(raw: str | None = None) -> str:
    """Return the `Production_tpAuth=...` pair from TP_AUTH_COOKIE.

    Accepts the bare value, the single pair, or a whole Cookie header pasted
    from dev tools; tracking cookies in a pasted header are dropped.
    """
    raw = (raw if raw is not None else os.getenv("TP_AUTH_COOKIE") or "").strip().strip("'\"")
    if not raw:
        raise RuntimeError(f"TP_AUTH_COOKIE is not set. {EXPIRED_COOKIE_HELP}")
    for part in raw.split(";"):
        part = part.strip()
        if part.startswith(f"{AUTH_COOKIE_NAME}="):
            return part
    if "=" in raw:
        raise RuntimeError(f"TP_AUTH_COOKIE has no {AUTH_COOKIE_NAME} cookie. {EXPIRED_COOKIE_HELP}")
    return f"{AUTH_COOKIE_NAME}={raw}"


def _refresh_token() -> str:
    global _token, _token_expires_at
    with httpx.Client(timeout=30) as c:
        r = c.get(f"{BASE_URL}/users/v3/token", headers={"Cookie": auth_cookie()})
    # An expired or garbled cookie comes back as a 500, not a 401.
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    token = (body.get("token") or {}) if r.is_success else {}
    if not token.get("access_token"):
        raise RuntimeError(f"TrainingPeaks login failed (HTTP {r.status_code}). {EXPIRED_COOKIE_HELP}")
    _token = token["access_token"]
    # Refresh a minute early so a token never expires mid-request.
    _token_expires_at = time.time() + int(token.get("expires_in", 3600)) - 60
    return _token


def _access_token() -> str:
    if _token is None or time.time() >= _token_expires_at:
        return _refresh_token()
    return _token


class _TrainingPeaksAuth(httpx.Auth):
    def auth_flow(self, request):
        request.headers["Authorization"] = f"Bearer {_access_token()}"
        response = yield request
        if response.status_code == 401:
            request.headers["Authorization"] = f"Bearer {_refresh_token()}"
            yield request


def get_tp_client() -> httpx.Client:
    return httpx.Client(
        base_url=BASE_URL,
        auth=_TrainingPeaksAuth(),
        headers={"Accept": "application/json"},
        timeout=60,
    )


def handle_tp_response(r: httpx.Response) -> str:
    if r.is_error:
        try:
            detail = r.json().get("message") or r.json()
        except Exception:
            detail = r.text or r.reason_phrase
        raise RuntimeError(f"TrainingPeaks HTTP {r.status_code}: {detail}")
    return r.text


def tp_user_id() -> str:
    global _user_id
    if _user_id is None:
        with get_tp_client() as c:
            r = c.get("/users/v3/user")
        handle_tp_response(r)
        body = r.json()
        _user_id = str(body.get("user", body)["userId"])
    return _user_id


# Aliases so trainingpeaks routers can import get_client / handle_response unchanged
get_client = get_tp_client
handle_response = handle_tp_response
