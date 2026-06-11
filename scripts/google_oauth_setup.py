"""One-time Google OAuth for JobPilot identities.

Default: authorize the primary account (Sheets/Gmail/Drive — the account that
owns the dashboard and sends the digest). Writes token.json and prints the
refresh token for Secret Manager.

--inbox: authorize an EXTRA watched inbox with gmail.readonly ONLY. Merges the
refresh token into inbox_tokens.json (gitignored) and prints the JSON for the
JOBPILOT_INBOX_TOKENS secret. Run once per extra account; pick the right
Google account in the browser each time.

Prereq: an OAuth 'Desktop app' client JSON downloaded from the GCP console,
saved as client_secret.json in the repo root (gitignored). The OAuth consent
screen must be In production, or Google expires refresh tokens after 7 days.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from jobpilot.gauth import READONLY_SCOPES, SCOPES

ROOT = Path(__file__).parent.parent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inbox", action="store_true",
                        help="authorize an extra watched inbox (gmail.readonly only)")
    args = parser.parse_args()

    client_path = ROOT / "client_secret.json"
    if not client_path.exists():
        raise SystemExit("client_secret.json not found in repo root — download it from "
                         "GCP console > APIs & Services > Credentials (Desktop app)")

    if args.inbox:
        flow = InstalledAppFlow.from_client_secrets_file(str(client_path), READONLY_SCOPES)
        creds = flow.run_local_server(port=0, prompt="consent")
        email = (
            build("gmail", "v1", credentials=creds, cache_discovery=False)
            .users().getProfile(userId="me").execute()["emailAddress"]
        )
        tokens_path = ROOT / "inbox_tokens.json"
        tokens = (
            json.loads(tokens_path.read_text(encoding="utf-8"))
            if tokens_path.exists() else {}
        )
        tokens[email] = creds.refresh_token
        tokens_path.write_text(json.dumps(tokens, indent=2), encoding="utf-8")
        print(f"{email} saved to inbox_tokens.json ({len(tokens)} watched inbox(es)).")
        print("\nFor Secret Manager — full value of JOBPILOT_INBOX_TOKENS:")
        print(json.dumps(tokens, indent=2))
        return

    flow = InstalledAppFlow.from_client_secrets_file(str(client_path), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    (ROOT / "token.json").write_text(creds.to_json(), encoding="utf-8")
    print("token.json written (local dev credentials).")
    print("\nFor Secret Manager:")
    print(f"  GOOGLE_OAUTH_REFRESH_TOKEN = {creds.refresh_token}")
    print(f"  GOOGLE_OAUTH_CLIENT_JSON   = contents of {client_path.name}")
    info = json.loads(client_path.read_text(encoding="utf-8"))
    cid = (info.get("installed") or info.get("web"))["client_id"]
    print(f"  (client_id: {cid})")


if __name__ == "__main__":
    main()
