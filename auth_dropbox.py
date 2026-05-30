"""
One-time OAuth authorization script for Dropbox.

Run this script to authorize the app and store tokens in .env:

    conda activate training-mcp
    python auth_dropbox.py

A browser window will open asking you to authorize. After approving,
tokens are saved to .env automatically.

Running in WSL? The browser can't reach the WSL callback server directly.
Visit the authorization URL printed to the terminal, authorize on Dropbox,
then copy the `code=` value from the redirect URL and run:

    python auth_dropbox.py --code YOUR_CODE_HERE
"""

import argparse
import os
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import httpx
from dotenv import load_dotenv, set_key

ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(ENV_PATH)

APP_KEY = os.getenv("DROPBOX_APP_KEY")
APP_SECRET = os.getenv("DROPBOX_APP_SECRET")
PORT = 8765
REDIRECT_URI = f"http://localhost:{PORT}/callback"
AUTH_URL = (
    f"https://www.dropbox.com/oauth2/authorize"
    f"?client_id={APP_KEY}"
    f"&redirect_uri={REDIRECT_URI}"
    f"&response_type=code"
    f"&token_access_type=offline"
)
TOKEN_URL = "https://api.dropboxapi.com/oauth2/token"

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
        pass


def exchange_code(code: str):
    with httpx.Client() as c:
        r = c.post(TOKEN_URL, data={
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
        }, auth=(APP_KEY, APP_SECRET))

    if r.is_error:
        print(f"Token exchange failed: {r.status_code} {r.text}")
        return

    data = r.json()
    expires_at = int(time.time()) + int(data.get("expires_in", 14400))
    set_key(ENV_PATH, "DROPBOX_ACCESS_TOKEN", data["access_token"])
    set_key(ENV_PATH, "DROPBOX_REFRESH_TOKEN", data["refresh_token"])
    set_key(ENV_PATH, "DROPBOX_TOKEN_EXPIRES_AT", str(expires_at))
    print("Tokens saved to .env. You're ready to run the server.")


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--code", help="Authorization code from redirect URL (WSL workaround)")
    args = parser.parse_args()

    if args.code:
        exchange_code(args.code)
        return

    print(f"\nOpening browser for Dropbox authorization...")
    print(f"If the browser doesn't open, visit this URL manually:\n\n  {AUTH_URL}\n")
    webbrowser.open(AUTH_URL)

    server = HTTPServer(("localhost", PORT), CallbackHandler)
    server.handle_request()

    if not auth_code:
        print("Authorization failed: no code received.")
        return

    print("Exchanging code for tokens...")
    exchange_code(auth_code)


if __name__ == "__main__":
    run()
