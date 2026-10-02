import httpx
import pytest

import client_trainingpeaks as tp


@pytest.mark.parametrize(
    "raw",
    [
        "abc123",
        "Production_tpAuth=abc123",
        '"Production_tpAuth=abc123"',
        "OptanonConsent=x=1&y=2; Production_tpAuth=abc123; _gcl_au=1.1.2",
    ],
)
def test_auth_cookie_accepts_value_pair_or_whole_header(raw):
    assert tp.auth_cookie(raw) == "Production_tpAuth=abc123"


def test_auth_cookie_rejects_header_without_tp_cookie():
    with pytest.raises(RuntimeError, match="no Production_tpAuth"):
        tp.auth_cookie("OptanonConsent=x; _gcl_au=1")


def test_auth_cookie_missing(monkeypatch):
    monkeypatch.delenv("TP_AUTH_COOKIE", raising=False)
    with pytest.raises(RuntimeError, match="TP_AUTH_COOKIE is not set"):
        tp.auth_cookie()


@pytest.fixture
def token_endpoint(monkeypatch):
    """Route the cookie→token exchange to a fake endpoint and reset the cache."""
    calls = {"n": 0}
    responses = []

    def handler(request):
        calls["n"] += 1
        assert request.headers["Cookie"] == "Production_tpAuth=abc123"
        return responses.pop(0)

    real_client = httpx.Client
    monkeypatch.setattr(tp.httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setenv("TP_AUTH_COOKIE", "Production_tpAuth=abc123")
    monkeypatch.setattr(tp, "_token", None)
    monkeypatch.setattr(tp, "_token_expires_at", 0)
    return calls, responses


def token_response(token, expires_in=3600):
    return httpx.Response(200, json={"success": True, "token": {"access_token": token, "expires_in": expires_in}})


def test_token_is_cached_until_expiry(token_endpoint):
    calls, responses = token_endpoint
    responses.append(token_response("t1"))
    assert tp._access_token() == "t1"
    assert tp._access_token() == "t1"
    assert calls["n"] == 1


def test_expired_token_is_refreshed(token_endpoint, monkeypatch):
    calls, responses = token_endpoint
    responses += [token_response("t1", expires_in=30), token_response("t2")]
    assert tp._access_token() == "t1"  # expires_in 30 < the 60 s safety margin
    assert tp._access_token() == "t2"
    assert calls["n"] == 2


def test_rejected_cookie_explains_how_to_fix(token_endpoint):
    _, responses = token_endpoint
    # TrainingPeaks answers a bad cookie with a 500, not a 401.
    responses.append(httpx.Response(500, json={"message": "An error has occurred."}))
    with pytest.raises(RuntimeError, match="login failed \\(HTTP 500\\).*fresh Production_tpAuth"):
        tp._access_token()


def test_401_retries_once_with_fresh_token(monkeypatch):
    tokens = iter(["fresh"])
    monkeypatch.setattr(tp, "_access_token", lambda: "stale")
    monkeypatch.setattr(tp, "_refresh_token", lambda: next(tokens))
    seen = []

    def handler(request):
        seen.append(request.headers["Authorization"])
        return httpx.Response(401 if len(seen) == 1 else 200, json={})

    with httpx.Client(auth=tp._TrainingPeaksAuth(), transport=httpx.MockTransport(handler)) as c:
        assert c.get("https://tpapi.trainingpeaks.com/x").status_code == 200
    assert seen == ["Bearer stale", "Bearer fresh"]
