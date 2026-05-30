"""
One-time OAuth authorization script for Strava.

Run this script to authorize the app and store tokens in .env:

    conda activate training-mcp
    python auth_strava.py

A browser window will open asking you to authorize the app. After
authorizing, tokens are saved to .env automatically.
"""

import os
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import httpx
from dotenv import load_dotenv, set_key

ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(ENV_PATH)

CLIENT_ID = os.getenv("STRAVA_CLIENT_ID")
CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET")
PORT = 8765
REDIRECT_URI = f"http://localhost:{PORT}/callback"
AUTH_URL = (
    f"https://www.strava.com/oauth/authorize"
    f"?client_id={CLIENT_ID}"
    f"&redirect_uri={REDIRECT_URI}"
    f"&response_type=code"
    f"&scope=activity:read_all,activity:write"
)
TOKEN_URL = "https://www.strava.com/oauth/token"

auth_code = None


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        params = parse_qs(urlparse(self.path).query)
        auth_code = params.get("code", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<h1>Authorized! You can close this window.</h1>")

    def log_message(self, *args):
        pass  # suppress request logs


def run():
    server = HTTPServer(("localhost", PORT), CallbackHandler)
    print("Opening browser for Strava authorization...")
    webbrowser.open(AUTH_URL)
    server.handle_request()  # handle one request then stop

    if not auth_code:
        print("Authorization failed: no code received.")
        return

    print("Exchanging code for tokens...")
    with httpx.Client() as c:
        r = c.post(TOKEN_URL, data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code": auth_code,
            "grant_type": "authorization_code",
        })

    if r.is_error:
        print(f"Token exchange failed: {r.status_code} {r.text}")
        return

    data = r.json()
    set_key(ENV_PATH, "STRAVA_ACCESS_TOKEN", data["access_token"])
    set_key(ENV_PATH, "STRAVA_REFRESH_TOKEN", data["refresh_token"])
    set_key(ENV_PATH, "STRAVA_TOKEN_EXPIRES_AT", str(data["expires_at"]))
    print("Tokens saved to .env. You're ready to run the server.")


if __name__ == "__main__":
    run()
