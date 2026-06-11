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
READONLY_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
LOCAL_INBOX_TOKENS = Path("inbox_tokens.json")


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


def inbox_credentials() -> dict[str, Credentials]:
    """Extra watched inboxes as {email: gmail.readonly creds}; {} when unconfigured.

    Tokens: JOBPILOT_INBOX_TOKENS env (Secret Manager) or local inbox_tokens.json,
    JSON of {email: refresh_token}. These accounts never get compose/Sheets/Drive.
    """
    raw = os.environ.get("JOBPILOT_INBOX_TOKENS")
    if not raw and LOCAL_INBOX_TOKENS.exists():
        raw = LOCAL_INBOX_TOKENS.read_text(encoding="utf-8")
    if not raw:
        return {}
    client_json = os.environ.get("GOOGLE_OAUTH_CLIENT_JSON")
    if not client_json:
        client_json = Path("client_secret.json").read_text(encoding="utf-8")
    client = json.loads(client_json)
    client = client.get("installed") or client.get("web") or client
    return {
        email: Credentials(
            token=None,
            refresh_token=refresh,
            client_id=client["client_id"],
            client_secret=client["client_secret"],
            token_uri=TOKEN_URI,
            scopes=READONLY_SCOPES,
        )
        for email, refresh in json.loads(raw).items()
    }
