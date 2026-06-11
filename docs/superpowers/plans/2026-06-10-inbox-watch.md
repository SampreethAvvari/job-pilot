# Inbox Watch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Watch three Gmail inboxes hourly, alert immediately (one email per finding) when a company sends a genuine next-step response, and keep the dashboard Sheet's statuses moving — superseding the old single-inbox scanner.

**Architecture:** New `src/jobpilot/inboxwatch.py` module (fetch → dedup via `InboxWatch` sheet tab → one Gemini classification call per account → alert + forward-only status updates), wired into both the hourly `--fast` and 4x/day full pipeline runs plus a standalone `--inbox-watch` CLI flag. Extra-account credentials come from a `JOBPILOT_INBOX_TOKENS` secret with `gmail.readonly` scope only. `scanner.py` is deleted; its forward-only logic and tests move into the new module.

**Tech Stack:** Python 3.12, google-api-python-client (Gmail/Sheets), google-genai (Vertex Gemini, JSON-schema responses), pydantic v2, pytest.

**Spec:** `docs/superpowers/specs/2026-06-10-inbox-watch-design.md`

**Repo conventions:** commits authored as SampreethAvvari (no co-author trailers). Run commands from the repo root (`job-pilot/`). Tests: `python -m pytest tests/ -q`. Lint: `python -m ruff check src tests scripts`.

---

### Task 1: Config — `InboxWatchCfg`

**Files:**
- Modify: `src/jobpilot/config.py` (add class after `DigestCfg`, field on `Config`)
- Modify: `profile.yaml` (template section)
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test** — append to `tests/test_config.py`:

```python
def test_inbox_watch_defaults():
    cfg = load_template()
    assert cfg.inbox_watch.enabled is True
    assert cfg.inbox_watch.lookback_days == 2
    assert cfg.inbox_watch.max_messages == 50
```

(If `tests/test_config.py` has no `load_template` helper, read the file first and reuse however it loads `profile.yaml`; adapt the test to the existing pattern.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -q`
Expected: FAIL — `Config` has no attribute `inbox_watch`.

- [ ] **Step 3: Implement** — in `src/jobpilot/config.py`, after `class DigestCfg`:

```python
class InboxWatchCfg(_Strict):
    """Multi-account reply detection (see docs/superpowers/specs/2026-06-10-inbox-watch-design.md)."""
    enabled: bool = True
    lookback_days: int = 2
    max_messages: int = 50
```

and on `Config`, after `digest: DigestCfg`:

```python
    inbox_watch: InboxWatchCfg = InboxWatchCfg()
```

In `profile.yaml`, after the `digest:` block:

```yaml
inbox_watch:        # hourly multi-inbox reply detection + alerts
  enabled: true
  lookback_days: 2  # how far back each check looks
  max_messages: 50  # per inbox per check
```

- [ ] **Step 4: Run tests** — `python -m pytest tests/test_config.py -q` → PASS

- [ ] **Step 5: Commit**

```bash
git add src/jobpilot/config.py profile.yaml tests/test_config.py
git commit -m "feat(config): inbox_watch section"
```

---

### Task 2: Parameterize the Gemini LLM response schema

The scanner bug: `make_gemini_llm` hardcodes `response_schema=_ScoreBatch`, so the old scanner's `matches` JSON could never validate — Gemini was schema-forced into `scores`. Fix by accepting a schema.

**Files:**
- Modify: `src/jobpilot/scorer.py:43-68`

- [ ] **Step 1: Implement** (no new test — existing scorer tests cover the default path; the new path is covered by Task 5's integration through `FindingBatch`):

```python
def make_gemini_llm(cfg: Config, schema: type[BaseModel] | None = None) -> LlmFn:
    """Gemini client: Vertex AI when GOOGLE_CLOUD_PROJECT is set, else AI Studio key.

    schema constrains the JSON response; defaults to the scoring contract.
    """
    from google import genai

    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if project:
        client = genai.Client(
            vertexai=True,
            project=project,
            location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
        )
    else:
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    def llm(prompt: str) -> str:
        resp = client.models.generate_content(
            model=cfg.scoring.model,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": schema or _ScoreBatch,
            },
        )
        return resp.text

    return llm
```

- [ ] **Step 2: Run full tests** — `python -m pytest tests/ -q` → PASS (no behavior change for existing callers)

- [ ] **Step 3: Commit**

```bash
git add src/jobpilot/scorer.py
git commit -m "fix(scorer): make_gemini_llm accepts a response schema (scanner could never parse matches)"
```

---

### Task 3: gauth — `inbox_credentials()`

**Files:**
- Modify: `src/jobpilot/gauth.py`
- Test: `tests/test_gauth.py` (new)

- [ ] **Step 1: Write the failing test** — create `tests/test_gauth.py`:

```python
import json

from jobpilot.gauth import inbox_credentials

CLIENT = json.dumps({"installed": {"client_id": "cid", "client_secret": "cs"}})


def test_inbox_credentials_from_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_JSON", CLIENT)
    monkeypatch.setenv("JOBPILOT_INBOX_TOKENS", json.dumps({"a@gmail.com": "rt-a", "b@gmail.com": "rt-b"}))
    creds = inbox_credentials()
    assert set(creds) == {"a@gmail.com", "b@gmail.com"}
    assert creds["a@gmail.com"].refresh_token == "rt-a"
    assert creds["a@gmail.com"].scopes == ["https://www.googleapis.com/auth/gmail.readonly"]


def test_inbox_credentials_absent(monkeypatch, tmp_path):
    monkeypatch.delenv("JOBPILOT_INBOX_TOKENS", raising=False)
    monkeypatch.chdir(tmp_path)  # no local inbox_tokens.json
    assert inbox_credentials() == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_gauth.py -q`
Expected: FAIL — ImportError, `inbox_credentials` not defined.

- [ ] **Step 3: Implement** — in `src/jobpilot/gauth.py`, after `LOCAL_TOKEN = Path("token.json")`:

```python
READONLY_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
LOCAL_INBOX_TOKENS = Path("inbox_tokens.json")
```

and after `credentials()`:

```python
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
```

Also add `inbox_tokens.json` to `.gitignore` (next to `token.json` / `client_secret.json` entries).

- [ ] **Step 4: Run tests** — `python -m pytest tests/test_gauth.py -q` → PASS

- [ ] **Step 5: Commit**

```bash
git add src/jobpilot/gauth.py tests/test_gauth.py .gitignore
git commit -m "feat(gauth): readonly credentials for extra watched inboxes"
```

---

### Task 4: sheets — `InboxWatch` tab helpers

**Files:**
- Modify: `src/jobpilot/sheets.py` (append after `append_report`; mirror the Reports-tab pattern — these are thin API wrappers, untested like their siblings)

- [ ] **Step 1: Implement**

```python
INBOXWATCH_HEADERS = [
    "Checked at", "Key", "Account", "From", "Subject", "Class", "Company", "Alerted",
]


def ensure_inboxwatch_tab(creds, spreadsheet_id: str) -> None:
    svc = _svc(creds)
    meta = svc.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    titles = [s["properties"]["title"] for s in meta["sheets"]]
    if "InboxWatch" in titles:
        return
    svc.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": [{"addSheet": {"properties": {"title": "InboxWatch"}}}]},
    ).execute()
    svc.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id, range="InboxWatch!A1", valueInputOption="RAW",
        body={"values": [INBOXWATCH_HEADERS]},
    ).execute()


def inboxwatch_keys(creds, spreadsheet_id: str) -> set[str]:
    """Dedup set: '{account}:{message_id}' for every message ever judged."""
    ensure_inboxwatch_tab(creds, spreadsheet_id)
    resp = (
        _svc(creds)
        .spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range="InboxWatch!B2:B")
        .execute()
    )
    return {row[0] for row in resp.get("values", []) if row}


def append_inboxwatch_rows(creds, spreadsheet_id: str, rows: list[list]) -> None:
    if not rows:
        return
    _svc(creds).spreadsheets().values().append(
        spreadsheetId=spreadsheet_id, range="InboxWatch!A1",
        valueInputOption="RAW", insertDataOption="INSERT_ROWS",
        body={"values": rows},
    ).execute()
```

- [ ] **Step 2: Run tests + lint** — `python -m pytest tests/ -q && python -m ruff check src` → PASS

- [ ] **Step 3: Commit**

```bash
git add src/jobpilot/sheets.py
git commit -m "feat(sheets): InboxWatch audit/dedup tab helpers"
```

---

### Task 5: inboxwatch.py — models, classification, status mapping

**Files:**
- Create: `src/jobpilot/inboxwatch.py`
- Test: `tests/test_inboxwatch.py` (new)

- [ ] **Step 1: Write the failing tests** — create `tests/test_inboxwatch.py`:

```python
import json

from jobpilot.inboxwatch import Finding, classify, forward_only, status_for

MESSAGES = [
    {"id": "m1", "from": "recruiter@acme.com", "subject": "Interview availability",
     "snippet": "s", "body": "Are you free Tuesday for a phone screen?"},
    {"id": "m2", "from": "no-reply@ats.io", "subject": "Application received",
     "snippet": "s", "body": "Thanks for applying to Beta."},
]
TRACKED = [
    {"_row": 2, "Job ID": "abc", "Company": "Acme", "Title": "ML Engineer", "Status": "Applied"},
]


def llm_returning(findings):
    return lambda prompt: json.dumps({"findings": findings})


def test_classify_parses_findings():
    out = classify(MESSAGES, TRACKED, llm_returning([
        {"message_index": 0, "classification": "next_step", "is_interview": True,
         "company": "Acme", "reason": "asks availability", "job_id": "abc"},
        {"message_index": 1, "classification": "automated_ack", "company": "Beta"},
    ]))
    assert out[0].classification == "next_step" and out[0].is_interview
    assert out[1].classification == "automated_ack" and out[1].job_id == ""


def test_classify_garbage_degrades_to_empty():
    assert classify(MESSAGES, TRACKED, lambda p: "nope") == []


def test_classify_empty_messages_skip_llm():
    assert classify([], TRACKED, None) == []


def test_classify_prompt_includes_tracked_and_bodies():
    seen = {}
    def spy(prompt):
        seen["p"] = prompt
        return json.dumps({"findings": []})
    classify(MESSAGES, TRACKED, spy)
    assert "ML Engineer" in seen["p"] and "phone screen" in seen["p"]


def test_forward_only_transitions():
    assert forward_only("Applied", "Interview") == "Interview"
    assert forward_only("Interview", "Response") is None  # never downgrade
    assert forward_only("Applied", "Rejected") == "Rejected"  # terminal always allowed
    assert forward_only("Applied", None) is None


def test_status_for_mapping():
    assert status_for(Finding(message_index=0, classification="rejection")) == "Rejected"
    assert status_for(Finding(message_index=0, classification="next_step",
                              is_interview=True)) == "Interview"
    assert status_for(Finding(message_index=0, classification="next_step")) == "Response"
    assert status_for(Finding(message_index=0, classification="automated_ack")) is None
    assert status_for(Finding(message_index=0, classification="unrelated")) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_inboxwatch.py -q`
Expected: FAIL — `jobpilot.inboxwatch` does not exist.

- [ ] **Step 3: Implement** — create `src/jobpilot/inboxwatch.py`:

```python
"""Multi-account inbox watch: detect genuine next-step replies, alert immediately.

Supersedes the single-inbox scanner. Every watched inbox is judged in full (not
just tracked applications): a real recruiter response, interview/OA invite, or
document request triggers an alert email within the hour. Automated acks and
rejections are recorded in the InboxWatch sheet tab but never alert. Manual
sheet edits always win — status only moves forward.
"""

from __future__ import annotations

import base64
import html
import json
from datetime import datetime
from email.mime.text import MIMEText
from typing import Callable, Literal

from googleapiclient.discovery import build
from pydantic import BaseModel

from jobpilot import sheets
from jobpilot.config import Config

TRACKED_STATUSES = {"Applied", "Outreach sent", "Response", "Interview"}
_ORDER = ["New", "Applied", "Outreach sent", "Response", "Interview", "Offer"]
BODY_CHARS = 1200


class Finding(BaseModel):
    message_index: int
    classification: Literal["next_step", "automated_ack", "rejection", "unrelated"]
    is_interview: bool = False
    company: str = ""
    reason: str = ""
    job_id: str = ""


class FindingBatch(BaseModel):
    findings: list[Finding]


PROMPT = """You triage one job-seeker's inbox. For EVERY email below, decide whether a company
is genuinely moving their job application forward.

Classifications:
- next_step: real progression — a recruiter/hiring manager replying personally, an
  interview or phone-screen invite, a scheduling/availability request or scheduling
  link, an online-assessment (HackerRank/Codility/...) invite, or a request for
  documents, portfolio, or references. Set is_interview=true when it invites or
  schedules an interview, call, or phone screen.
- automated_ack: automated "application received / thanks for applying" confirmations.
- rejection: any rejection, automated or personal.
- unrelated: everything else — newsletters, job alerts/boards, promotions, personal
  mail, and JobPilot's own digests and alerts.

Rules: be conservative — when torn between next_step and automated_ack, choose
automated_ack. Set company to the company's name ("" if unclear). Set reason to one
short sentence quoting the evidence. Set job_id only when the email clearly concerns
one of the tracked applications; otherwise "".

TRACKED APPLICATIONS (JSON): {tracked}
EMAILS (JSON): {emails}

Return JSON: {{"findings": [{{"message_index", "classification", "is_interview",
"company", "reason", "job_id"}}]}}"""


def forward_only(current: str, proposed: str | None) -> str | None:
    if proposed is None:
        return None
    if proposed == "Rejected":
        return proposed
    if current not in _ORDER or _ORDER.index(proposed) > _ORDER.index(current):
        return proposed
    return None


def status_for(f: Finding) -> str | None:
    if f.classification == "rejection":
        return "Rejected"
    if f.classification == "next_step":
        return "Interview" if f.is_interview else "Response"
    return None


def classify(messages: list[dict], tracked: list[dict],
             llm: Callable[[str], str]) -> list[Finding]:
    """One LLM call per inbox batch. Pure given llm; failures degrade to []."""
    if not messages:
        return []
    jobs = [
        {"job_id": r["Job ID"], "company": r["Company"], "title": r["Title"]} for r in tracked
    ]
    emails = [
        {"message_index": i, "from": m["from"], "subject": m["subject"], "body": m["body"]}
        for i, m in enumerate(messages)
    ]
    prompt = PROMPT.format(
        tracked=json.dumps(jobs, ensure_ascii=False),
        emails=json.dumps(emails, ensure_ascii=False),
    )
    try:
        return FindingBatch.model_validate_json(llm(prompt)).findings
    except Exception:
        return []
```

- [ ] **Step 4: Run tests** — `python -m pytest tests/test_inboxwatch.py -q` → PASS

- [ ] **Step 5: Commit**

```bash
git add src/jobpilot/inboxwatch.py tests/test_inboxwatch.py
git commit -m "feat(inboxwatch): finding models, conservative classifier, status mapping"
```

---

### Task 6: inboxwatch.py — Gmail fetch + body extraction

**Files:**
- Modify: `src/jobpilot/inboxwatch.py`
- Test: `tests/test_inboxwatch.py`

- [ ] **Step 1: Write the failing tests** — append:

```python
import base64

from jobpilot.inboxwatch import body_text


def b64(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode()).decode()


def test_body_text_plain():
    payload = {"mimeType": "text/plain", "body": {"data": b64("hello")}}
    assert body_text(payload) == "hello"


def test_body_text_nested_multipart():
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {"mimeType": "text/html", "body": {"data": b64("<b>hi</b>")}},
            {"mimeType": "multipart/mixed",
             "parts": [{"mimeType": "text/plain", "body": {"data": b64("inner text")}}]},
        ],
    }
    assert body_text(payload) == "inner text"


def test_body_text_html_only_returns_empty():
    payload = {"mimeType": "text/html", "body": {"data": b64("<b>hi</b>")}}
    assert body_text(payload) == ""
```

- [ ] **Step 2: Run to verify failure** — `python -m pytest tests/test_inboxwatch.py -q` → FAIL (`body_text` not defined)

- [ ] **Step 3: Implement** — add to `src/jobpilot/inboxwatch.py`:

```python
def body_text(payload: dict) -> str:
    """Best-effort plain-text body from a Gmail payload ('' if none — caller falls
    back to the snippet)."""
    if payload.get("mimeType", "").startswith("text/plain"):
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data + "===").decode("utf-8", errors="replace")
    for part in payload.get("parts", []) or []:
        text = body_text(part)
        if text:
            return text
    return ""


def fetch_messages(creds, lookback_days: int, max_messages: int) -> list[dict]:
    svc = build("gmail", "v1", credentials=creds, cache_discovery=False)
    query = f"in:inbox newer_than:{lookback_days}d -category:promotions -category:social"
    listing = (
        svc.users().messages()
        .list(userId="me", q=query, maxResults=max_messages)
        .execute()
    )
    out = []
    for ref in listing.get("messages", []):
        msg = svc.users().messages().get(userId="me", id=ref["id"], format="full").execute()
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        out.append(
            {
                "id": msg["id"],
                "from": headers.get("From", ""),
                "subject": headers.get("Subject", ""),
                "snippet": msg.get("snippet", ""),
                "body": (body_text(msg.get("payload", {})) or msg.get("snippet", ""))[:BODY_CHARS],
            }
        )
    return out
```

- [ ] **Step 4: Run tests** — `python -m pytest tests/test_inboxwatch.py -q` → PASS

- [ ] **Step 5: Commit**

```bash
git add src/jobpilot/inboxwatch.py tests/test_inboxwatch.py
git commit -m "feat(inboxwatch): gmail fetch with plain-text body extraction"
```

---

### Task 7: inboxwatch.py — alert construction + send

**Files:**
- Modify: `src/jobpilot/inboxwatch.py`
- Test: `tests/test_inboxwatch.py`

- [ ] **Step 1: Write the failing tests** — append:

```python
from jobpilot.inboxwatch import build_alert

MSG = {"id": "18c2a", "from": "Recruiter <r@acme.com>", "subject": "Next steps & <interview>",
       "snippet": "s", "body": "Are you free Tuesday?"}
NEXT_STEP = Finding(message_index=0, classification="next_step", is_interview=True,
                    company="Acme", reason="asks availability")


def test_build_alert_subject_and_link():
    subject, body = build_alert("me@gmail.com", MSG, NEXT_STEP)
    assert subject == "🎯 Acme responded — check me@gmail.com"
    assert "https://mail.google.com/mail/?authuser=me@gmail.com#all/18c2a" in body
    assert "Are you free Tuesday?" in body


def test_build_alert_escapes_html_and_handles_unknown_company():
    anon = Finding(message_index=0, classification="next_step", reason="r")
    subject, body = build_alert("me@gmail.com", MSG, anon)
    assert subject.startswith("🎯 A company responded")
    assert "<interview>" not in body and "&lt;interview&gt;" in body
```

- [ ] **Step 2: Run to verify failure** — `python -m pytest tests/test_inboxwatch.py -q` → FAIL (`build_alert` not defined)

- [ ] **Step 3: Implement** — add:

```python
def build_alert(account: str, msg: dict, finding: Finding) -> tuple[str, str]:
    """(subject, html) for one next_step finding."""
    company = finding.company or "A company"
    link = f"https://mail.google.com/mail/?authuser={account}#all/{msg['id']}"
    subject = f"🎯 {company} responded — check {account}"
    body = (
        f"<h2>{html.escape(company)} moved your application forward</h2>"
        f"<p><b>Inbox:</b> {html.escape(account)}<br>"
        f"<b>From:</b> {html.escape(msg['from'])}<br>"
        f"<b>Subject:</b> {html.escape(msg['subject'])}</p>"
        f"<p><b>Why this matters:</b> {html.escape(finding.reason)}</p>"
        f"<blockquote>{html.escape(msg['body'][:600])}</blockquote>"
        f'<p><a href="{link}">Open this email</a></p>'
    )
    return subject, body


def send_alert(primary_creds, to: str, subject: str, body: str) -> None:
    msg = MIMEText(body, "html")
    msg["To"] = to
    msg["Subject"] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    build("gmail", "v1", credentials=primary_creds, cache_discovery=False).users().messages().send(
        userId="me", body={"raw": raw}
    ).execute()
```

- [ ] **Step 4: Run tests** — `python -m pytest tests/test_inboxwatch.py -q` → PASS

- [ ] **Step 5: Commit**

```bash
git add src/jobpilot/inboxwatch.py tests/test_inboxwatch.py
git commit -m "feat(inboxwatch): per-finding alert email with account deep link"
```

---

### Task 8: inboxwatch.py — `process()` + `watch()` orchestration

**Files:**
- Modify: `src/jobpilot/inboxwatch.py`
- Test: `tests/test_inboxwatch.py`

- [ ] **Step 1: Write the failing tests** — append:

```python
from datetime import datetime, timezone

import jobpilot.inboxwatch as iw
from jobpilot.inboxwatch import process, watch
from tests.test_sources import make_cfg

NOW = datetime(2026, 6, 10, 15, 0, tzinfo=timezone.utc)
BY_ID = {"abc": {"_row": 2, "Job ID": "abc", "Company": "Acme",
                 "Title": "ML Engineer", "Status": "Applied"}}


def findings_pair():
    return [
        Finding(message_index=0, classification="next_step", is_interview=True,
                company="Acme", reason="availability", job_id="abc"),
        Finding(message_index=1, classification="automated_ack", company="Beta"),
    ]


def test_process_alerts_updates_and_logs():
    log_rows, updates, alerts = process("me@gmail.com", MESSAGES, findings_pair(), BY_ID, NOW)
    assert len(alerts) == 1 and "Acme" in alerts[0][0]
    assert (2, "Status", "Interview") in updates
    assert (2, "Reply class", "next_step") in updates
    assert len(log_rows) == 2
    assert log_rows[0][1] == "me@gmail.com:m1" and log_rows[0][7] == "yes"
    assert log_rows[1][5] == "automated_ack" and log_rows[1][7] == ""


def test_process_unjudged_messages_not_logged():
    # LLM omitted message 1 → no log row, so it is re-judged next run
    only_first = [findings_pair()[0]]
    log_rows, _, _ = process("me@gmail.com", MESSAGES, only_first, BY_ID, NOW)
    assert len(log_rows) == 1


def test_process_out_of_range_index_ignored():
    bogus = [Finding(message_index=9, classification="next_step")]
    log_rows, updates, alerts = process("me@gmail.com", MESSAGES, bogus, BY_ID, NOW)
    assert log_rows == [] and updates == [] and alerts == []


class _FakeGmail:
    def users(self):
        return self
    def getProfile(self, userId):
        return self
    def execute(self):
        return {"emailAddress": "primary@nyu.edu"}


def test_watch_isolates_account_failures(monkeypatch):
    monkeypatch.setattr(iw, "build", lambda *a, **k: _FakeGmail())
    monkeypatch.setattr(iw.sheets, "inboxwatch_keys", lambda c, s: set())
    monkeypatch.setattr(iw.sheets, "read_rows", lambda c, s: [])
    monkeypatch.setattr(iw.sheets, "update_cells", lambda c, s, u: None)
    monkeypatch.setattr(iw.sheets, "append_inboxwatch_rows", lambda c, s, r: None)

    def boom(creds, lookback_days, max_messages):
        raise RuntimeError("token expired")

    monkeypatch.setattr(iw, "fetch_messages", boom)
    notes = watch("creds", {"extra@gmail.com": "c2"}, "sid", make_cfg(), None, NOW)
    assert len(notes) == 2 and all("FAILED" in n for n in notes)


def test_watch_dedups_seen_messages_and_alerts(monkeypatch):
    sent = []
    appended = []
    monkeypatch.setattr(iw, "build", lambda *a, **k: _FakeGmail())
    monkeypatch.setattr(iw.sheets, "inboxwatch_keys",
                        lambda c, s: {"primary@nyu.edu:m2"})
    monkeypatch.setattr(iw.sheets, "read_rows", lambda c, s: list(BY_ID.values()))
    monkeypatch.setattr(iw.sheets, "update_cells", lambda c, s, u: None)
    monkeypatch.setattr(iw.sheets, "append_inboxwatch_rows",
                        lambda c, s, r: appended.extend(r))
    monkeypatch.setattr(iw, "fetch_messages", lambda c, d, m: list(MESSAGES))
    monkeypatch.setattr(iw, "send_alert", lambda c, to, s, b: sent.append(s))

    def llm(prompt):
        # only m1 survives dedup → single email at index 0
        assert "m2" not in prompt or "Application received" not in prompt
        return json.dumps({"findings": [
            {"message_index": 0, "classification": "next_step", "is_interview": True,
             "company": "Acme", "reason": "availability", "job_id": "abc"}]})

    notes = watch("creds", {}, "sid", make_cfg(), llm, NOW)
    assert sent == ["🎯 Acme responded — check primary@nyu.edu"]
    assert len(appended) == 1
    assert notes == ["inbox-watch primary@nyu.edu: 1 new emails, 1 alerts"]
```

(`make_cfg` comes from `tests/test_sources.py`, the same helper `test_pipeline.py` uses. Read it first; if it doesn't produce a full `Config` with `digest.to`, adapt by constructing the Config the way that file does.)

- [ ] **Step 2: Run to verify failure** — `python -m pytest tests/test_inboxwatch.py -q` → FAIL (`process`/`watch` not defined)

- [ ] **Step 3: Implement** — add:

```python
def process(
    account: str, messages: list[dict], findings: list[Finding],
    tracked_by_id: dict[str, dict], now: datetime,
) -> tuple[list[list], list[tuple[int, str, str]], list[tuple[str, str]]]:
    """Pure: findings -> (InboxWatch log rows, Jobs-sheet updates, alert (subject, body)s).

    Only judged messages are logged — anything the LLM skipped is retried next run.
    """
    log_rows: list[list] = []
    updates: list[tuple[int, str, str]] = []
    alerts: list[tuple[str, str]] = []
    for f in findings:
        if not 0 <= f.message_index < len(messages):
            continue
        m = messages[f.message_index]
        alerted = ""
        if f.classification == "next_step":
            alerts.append(build_alert(account, m, f))
            alerted = "yes"
        row = tracked_by_id.get(f.job_id) if f.job_id else None
        if row is not None and f.classification != "unrelated":
            updates.append((row["_row"], "Last reply", now.strftime("%Y-%m-%d")))
            updates.append((row["_row"], "Reply class", f.classification))
            new_status = forward_only(row["Status"], status_for(f))
            if new_status:
                updates.append((row["_row"], "Status", new_status))
        log_rows.append([
            now.strftime("%Y-%m-%d %H:%M"), f"{account}:{m['id']}", account,
            m["from"], m["subject"], f.classification, f.company, alerted,
        ])
    return log_rows, updates, alerts


def watch(primary_creds, inbox_creds: dict, spreadsheet_id: str, cfg: Config,
          llm: Callable[[str], str], now: datetime) -> list[str]:
    """Check every watched inbox; returns digest notes. Never raises."""
    if not cfg.inbox_watch.enabled:
        return []
    try:
        primary_email = (
            build("gmail", "v1", credentials=primary_creds, cache_discovery=False)
            .users().getProfile(userId="me").execute()["emailAddress"]
        )
        accounts = {primary_email: primary_creds, **inbox_creds}
        seen = sheets.inboxwatch_keys(primary_creds, spreadsheet_id)
        rows = sheets.read_rows(primary_creds, spreadsheet_id)
        tracked = [r for r in rows if r["Status"] in TRACKED_STATUSES]
        by_id = {r["Job ID"]: r for r in tracked}
    except Exception as exc:  # noqa: BLE001 — watcher must never break the run
        return [f"inbox-watch: FAILED to start ({type(exc).__name__}: {exc})"]

    notes = []
    for account, creds in accounts.items():
        try:
            messages = fetch_messages(
                creds, cfg.inbox_watch.lookback_days, cfg.inbox_watch.max_messages
            )
            fresh = [m for m in messages if f"{account}:{m['id']}" not in seen]
            findings = classify(fresh, tracked, llm)
            log_rows, updates, alerts = process(account, fresh, findings, by_id, now)
            for subject, body in alerts:
                send_alert(primary_creds, cfg.digest.to, subject, body)
            sheets.update_cells(primary_creds, spreadsheet_id, updates)
            sheets.append_inboxwatch_rows(primary_creds, spreadsheet_id, log_rows)
            notes.append(
                f"inbox-watch {account}: {len(fresh)} new emails, {len(alerts)} alerts"
            )
        except Exception as exc:  # noqa: BLE001 — one dark inbox must not kill the others
            notes.append(f"inbox-watch {account}: FAILED ({type(exc).__name__}: {exc})")
    return notes
```

- [ ] **Step 4: Run tests** — `python -m pytest tests/test_inboxwatch.py -q` → PASS

- [ ] **Step 5: Commit**

```bash
git add src/jobpilot/inboxwatch.py tests/test_inboxwatch.py
git commit -m "feat(inboxwatch): watch orchestration — dedup, alerts, forward-only sheet updates"
```

---

### Task 9: Delete the old scanner

**Files:**
- Delete: `src/jobpilot/scanner.py`, `tests/test_scanner.py` (forward-only logic + tests already ported in Tasks 5/8)

- [ ] **Step 1: Delete + verify nothing references scanner**

```bash
git rm src/jobpilot/scanner.py tests/test_scanner.py
grep -rn "scanner" src/ tests/ ui/src/ --include="*.py" --include="*.ts" --include="*.tsx"
```

Expected: the only hit is `src/jobpilot/pipeline.py` (fixed in Task 10). The UI Replies page text mentions "scanner" generically — fine. NOTE: do not commit yet; pipeline.py imports scanner and tests would break. Task 10 commits both together.

---

### Task 10: Pipeline + CLI wiring

**Files:**
- Modify: `src/jobpilot/pipeline.py:96-116`
- Modify: `src/jobpilot/__main__.py`
- Test: `tests/test_pipeline.py` (existing dry-run test must still pass — dry-run never reaches the watcher)

- [ ] **Step 1: Modify `pipeline.run`** — replace the credentialed section (lines 96-116). The import `from jobpilot.scanner import scan` is removed; both fast and full runs invoke the watcher:

```python
    from jobpilot import inboxwatch
    from jobpilot.gauth import credentials, inbox_credentials

    creds = credentials()
    sid = os.environ.get("JOBPILOT_SPREADSHEET_ID") or cfg.sheet.spreadsheet_id
    sid = sheets.ensure_dashboard(creds, sid)
    llm = make_gemini_llm(cfg)
    new = dedup.filter_new(postings, sheets.known_ids(creds, sid))
    notes.append(f"dedup: {len(new)} new of {len(postings)} fetched")
    scored = score(new, cfg, llm)
    sheets.append_jobs(creds, sid, scored, now)
    n_matches = sum(1 for s in scored if (s.fit_score or 0) >= cfg.scoring.threshold)

    watch_llm = make_gemini_llm(cfg, schema=inboxwatch.FindingBatch)
    watch_notes = inboxwatch.watch(creds, inbox_credentials(), sid, cfg, watch_llm, now)
    notes.extend(watch_notes)

    if fast:
        # Console-refresh mode: rows are in the sheet; tailoring/outreach/digest
        # are left to the next scheduled run. Inbox watch already ran (hourly alerts).
        print(f"fast run complete: {len(scored)} new jobs, {n_matches} matches, sheet {sid}")
        for note in watch_notes:
            print(note)
        return scored
```

(The full-run branch continues from `from jobpilot.outreach import auto_outreach` exactly as before — the old `notes.extend(scan(creds, sid, cfg, llm, now))` line is gone.)

- [ ] **Step 2: Add `--inbox-watch` to `src/jobpilot/__main__.py`** — new argument:

```python
    parser.add_argument("--inbox-watch", action="store_true",
                        help="check watched inboxes for replies and alert (skips pipeline)")
```

and after `cfg = Config.load(args.config)`, before the `--rebuild-resume` block:

```python
    if args.inbox_watch:
        import os
        from datetime import datetime, timezone

        from jobpilot import inboxwatch
        from jobpilot.gauth import credentials, inbox_credentials
        from jobpilot.scorer import make_gemini_llm

        creds = credentials()
        sid = os.environ.get("JOBPILOT_SPREADSHEET_ID") or cfg.sheet.spreadsheet_id
        llm = make_gemini_llm(cfg, schema=inboxwatch.FindingBatch)
        for note in inboxwatch.watch(creds, inbox_credentials(), sid, cfg, llm,
                                     datetime.now(timezone.utc)):
            print(note)
        return
```

- [ ] **Step 3: Run all tests + lint**

Run: `python -m pytest tests/ -q && python -m ruff check src tests scripts`
Expected: PASS (dry-run pipeline test unaffected; scanner imports gone).

- [ ] **Step 4: Commit** (includes Task 9's deletions)

```bash
git add -A src/jobpilot tests
git commit -m "feat(pipeline): inbox watch in fast+full runs, --inbox-watch CLI; retire scanner"
```

---

### Task 11: OAuth setup script `--inbox` mode

**Files:**
- Modify: `scripts/google_oauth_setup.py`

- [ ] **Step 1: Rewrite the script** (argparse + new mode; default behavior unchanged):

```python
"""One-time Google OAuth for JobPilot identities.

Default: authorize the primary account (Sheets/Gmail/Drive — the account that
owns the dashboard and sends the digest). Writes token.json and prints the
refresh token for Secret Manager.

--inbox: authorize an EXTRA watched inbox with gmail.readonly ONLY. Merges the
refresh token into inbox_tokens.json (gitignored) and prints the JSON for the
JOBPILOT_INBOX_TOKENS secret. Run once per extra account; pick the right
Google account in the browser each time.

Prereq: an OAuth 'Desktop app' client JSON saved as client_secret.json in the
repo root (gitignored). The OAuth consent screen must be In production, or
Google expires refresh tokens after 7 days.
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
```

- [ ] **Step 2: Lint + sanity** — `python -m ruff check scripts && python scripts/google_oauth_setup.py --help` → help text shows `--inbox`

- [ ] **Step 3: Commit**

```bash
git add scripts/google_oauth_setup.py
git commit -m "feat(setup): --inbox mode authorizes extra watched inboxes (readonly)"
```

---

### Task 12: Docs

**Files:**
- Modify: `docs/gcp-setup.md` (Secret Manager list + scheduler note)
- Modify: `docs/FORK-SETUP.md` (Step 3/4 additions, Appendix B entry)
- Modify: `docs/BUGLOG.md` (scanner schema bug entry)
- Modify: `README.md` (feature list mention, if it enumerates features — read it first)

- [ ] **Step 1: gcp-setup.md** — add to the Secret Manager bullet list:

```markdown
  `JOBPILOT_INBOX_TOKENS` — JSON `{email: refresh_token}` for EXTRA watched
  inboxes (gmail.readonly only; the primary identity is watched automatically);
```

and extend the Cloud Scheduler bullet: hourly runs also perform the inbox
watch (reply detection + alerts) — no extra scheduler needed.

- [ ] **Step 2: FORK-SETUP.md** — in Step 3, after the primary OAuth command:

```markdown
Watching more inboxes (optional): JobPilot can watch extra Gmail accounts for
recruiter replies and email you the moment a company moves you forward. For
each extra account:

​```bash
python scripts/google_oauth_setup.py --inbox   # sign in as THAT account
​```

This only requests gmail.readonly — the extra accounts can never send mail or
touch your Sheet. It merges tokens into inbox_tokens.json and prints the JSON
for the JOBPILOT_INBOX_TOKENS secret (created in Step 4).
```

In Step 4, add `JOBPILOT_INBOX_TOKENS` to the secrets created (optional,
only when watching extra inboxes), e.g.:

```bash
gcloud secrets create JOBPILOT_INBOX_TOKENS --replication-policy automatic
gcloud secrets versions add JOBPILOT_INBOX_TOKENS --data-file inbox_tokens.json
gcloud run jobs update jobpilot --region $REGION \
  --update-secrets JOBPILOT_INBOX_TOKENS=JOBPILOT_INBOX_TOKENS:latest
```

In Appendix B, add a row/entry: **Inbox Watch** — hourly multi-inbox reply
detection; genuine next-step responses (interview/OA/scheduling/document
requests) trigger an immediate alert email with a deep link; automated acks
and rejections are logged in the `InboxWatch` sheet tab; tracked rows move
forward (`Response`/`Interview`/`Rejected`, manual edits win). Configured in
`profile.yaml → inbox_watch`.

- [ ] **Step 3: BUGLOG.md** — append (match the file's existing entry format — read it first):

```markdown
## 2026-06-10 — scanner never matched anything in production
`make_gemini_llm` hardcoded `response_schema=_ScoreBatch`, so the reply
scanner's prompt (expecting `{"matches": ...}`) always got `{"scores": ...}`
back; `_MatchBatch.model_validate_json` failed and classify() silently
returned []. Fixed by parameterizing the schema; the scanner's replacement
(inboxwatch) passes its own `FindingBatch`. Lesson: a shared LLM wrapper with
a baked-in response schema breaks every other caller silently — schema is
per-call-site.
```

- [ ] **Step 4: Commit**

```bash
git add docs README.md
git commit -m "docs: inbox watch setup, secrets, buglog entry for scanner schema bug"
```

---

### Task 13: Verify, push, provision

- [ ] **Step 1: Full suite + lint**

Run: `python -m pytest tests/ -q && python -m ruff check src tests scripts`
Expected: all PASS, no lint errors.

- [ ] **Step 2: Push** (auto-deploys the pipeline via deploy.yml; env/secrets on the job are preserved by source deploys)

```bash
git push origin master
```

- [ ] **Step 3: Provision (gcloud, project jobpilot-sva, region us-central1)** — after the user runs `python scripts/google_oauth_setup.py --inbox` once per extra account (browser consent required, can't be automated):

```bash
gcloud secrets create JOBPILOT_INBOX_TOKENS --replication-policy automatic --project jobpilot-sva
gcloud secrets versions add JOBPILOT_INBOX_TOKENS --data-file inbox_tokens.json --project jobpilot-sva
gcloud run jobs update jobpilot --region us-central1 --project jobpilot-sva \
  --update-secrets JOBPILOT_INBOX_TOKENS=JOBPILOT_INBOX_TOKENS:latest
```

- [ ] **Step 4: Verify consent screen is In production** (Testing-mode refresh tokens die in 7 days):

```bash
gcloud iap oauth-brands list --project jobpilot-sva   # or check console: APIs & Services > OAuth consent screen
```

If it shows Testing, publish to production in the console (no verification needed for these scopes at this user count).

- [ ] **Step 5: End-to-end smoke** — execute the job with the watch flag and check logs:

```bash
gcloud run jobs execute jobpilot --region us-central1 --project jobpilot-sva \
  --args="--inbox-watch" --wait
gcloud logging read 'resource.type="cloud_run_job"' --project jobpilot-sva --limit 20
```

Expected: `inbox-watch <account>: N new emails, M alerts` per account, `InboxWatch` tab appears in the dashboard Sheet.
