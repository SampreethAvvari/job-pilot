"""One-time Google OAuth: authorize JobPilot as the digest/dashboard account.

Prereq: an OAuth 'Desktop app' client JSON downloaded from the GCP console,
saved as client_secret.json in the repo root (gitignored).

Run:  python scripts/google_oauth_setup.py
A browser opens — sign in as the account that should own the Sheet and send
the digest (spa9659@nyu.edu). Writes token.json (local dev) and prints the
refresh token for Secret Manager.
"""

from __future__ import annotations

import json
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

from jobpilot.gauth import SCOPES

ROOT = Path(__file__).parent.parent


def main() -> None:
    client_path = ROOT / "client_secret.json"
    if not client_path.exists():
        raise SystemExit("client_secret.json not found in repo root — download it from "
                         "GCP console > APIs & Services > Credentials (Desktop app)")
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
