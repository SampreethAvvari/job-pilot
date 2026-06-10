"""Google credentials for Sheets/Gmail/Drive as the user (OAuth refresh token).

Local dev: token.json written by scripts/google_oauth_setup.py.
Cloud Run: GOOGLE_OAUTH_CLIENT_JSON + GOOGLE_OAUTH_REFRESH_TOKEN env (Secret Manager).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from google.oauth2.credentials import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.readonly",  # reply-scanner (UI tracking)
    "https://www.googleapis.com/auth/drive.file",
]
TOKEN_URI = "https://oauth2.googleapis.com/token"
LOCAL_TOKEN = Path("token.json")


def credentials() -> Credentials:
    client_json = os.environ.get("GOOGLE_OAUTH_CLIENT_JSON")
    refresh_token = os.environ.get("GOOGLE_OAUTH_REFRESH_TOKEN")
    if client_json and refresh_token:
        client = json.loads(client_json)
        client = client.get("installed") or client.get("web") or client
        return Credentials(
            token=None,
            refresh_token=refresh_token,
            client_id=client["client_id"],
            client_secret=client["client_secret"],
            token_uri=TOKEN_URI,
            scopes=SCOPES,
        )
    if LOCAL_TOKEN.exists():
        return Credentials.from_authorized_user_file(str(LOCAL_TOKEN), SCOPES)
    raise RuntimeError(
        "No Google credentials: set GOOGLE_OAUTH_CLIENT_JSON + GOOGLE_OAUTH_REFRESH_TOKEN "
        "or run scripts/google_oauth_setup.py to create token.json"
    )
