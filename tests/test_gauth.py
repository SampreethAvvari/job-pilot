import json

from jobpilot.gauth import inbox_credentials

CLIENT = json.dumps({"installed": {"client_id": "cid", "client_secret": "cs"}})


def test_inbox_credentials_from_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_JSON", CLIENT)
    monkeypatch.setenv(
        "JOBPILOT_INBOX_TOKENS",
        json.dumps({"a@gmail.com": "rt-a", "b@gmail.com": "rt-b"}),
    )
    creds = inbox_credentials()
    assert set(creds) == {"a@gmail.com", "b@gmail.com"}
    assert creds["a@gmail.com"].refresh_token == "rt-a"
    assert creds["a@gmail.com"].scopes == ["https://www.googleapis.com/auth/gmail.readonly"]


def test_inbox_credentials_absent(monkeypatch, tmp_path):
    monkeypatch.delenv("JOBPILOT_INBOX_TOKENS", raising=False)
    monkeypatch.chdir(tmp_path)  # no local inbox_tokens.json
    assert inbox_credentials() == {}
