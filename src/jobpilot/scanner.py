"""Gmail reply scanner: match inbox replies to tracked applications, update Status.

Manual edits always win — the scanner only moves status forward (never downgrades)
and never touches rows the user marked Offer or Rejected.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Callable, Literal

from googleapiclient.discovery import build
from pydantic import BaseModel

from jobpilot import sheets
from jobpilot.config import Config

TRACKED_STATUSES = {"Applied", "Outreach sent", "Response", "Interview"}
_ORDER = ["New", "Applied", "Outreach sent", "Response", "Interview", "Offer"]
_CLASS_TO_STATUS = {
    "rejected": "Rejected",
    "interview": "Interview",
    "next_steps": "Response",
    "other": None,  # record the reply, leave status alone
}
MAX_MESSAGES = 50


class _Match(BaseModel):
    job_id: str
    message_index: int
    classification: Literal["rejected", "interview", "next_steps", "other"]


class _MatchBatch(BaseModel):
    matches: list[_Match]


def _forward_only(current: str, proposed: str | None) -> str | None:
    if proposed is None:
        return None
    if proposed == "Rejected":
        return proposed
    if current not in _ORDER or _ORDER.index(proposed) > _ORDER.index(current):
        return proposed
    return None


def fetch_messages(creds, max_messages: int = MAX_MESSAGES) -> list[dict]:
    svc = build("gmail", "v1", credentials=creds, cache_discovery=False)
    listing = (
        svc.users()
        .messages()
        .list(userId="me", q="in:inbox newer_than:3d -category:promotions", maxResults=max_messages)
        .execute()
    )
    out = []
    for ref in listing.get("messages", []):
        msg = (
            svc.users()
            .messages()
            .get(userId="me", id=ref["id"], format="metadata",
                 metadataHeaders=["From", "Subject"])
            .execute()
        )
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        out.append(
            {
                "from": headers.get("From", ""),
                "subject": headers.get("Subject", ""),
                "snippet": msg.get("snippet", ""),
            }
        )
    return out


def classify(tracked: list[dict], messages: list[dict], llm: Callable[[str], str]) -> list[_Match]:
    """One LLM call matching messages to tracked applications. Pure given llm."""
    if not tracked or not messages:
        return []
    jobs_desc = [
        {"job_id": r["Job ID"], "company": r["Company"], "title": r["Title"]} for r in tracked
    ]
    msgs_desc = [
        {"message_index": i, "from": m["from"], "subject": m["subject"], "snippet": m["snippet"]}
        for i, m in enumerate(messages)
    ]
    prompt = (
        "You match job-application reply emails to tracked applications.\n"
        f"TRACKED APPLICATIONS (JSON): {json.dumps(jobs_desc, ensure_ascii=False)}\n"
        f"RECENT EMAILS (JSON): {json.dumps(msgs_desc, ensure_ascii=False)}\n"
        "Return matches ONLY when an email is clearly about one of the tracked applications "
        "(recruiter reply, ATS notification, interview invite, rejection). Ignore newsletters, "
        "job alerts, and digests (including JobPilot's own). Classify each match: "
        "rejected | interview | next_steps | other.\n"
        'JSON schema: {"matches": [{"job_id", "message_index", "classification"}]}'
    )
    try:
        return _MatchBatch.model_validate_json(llm(prompt)).matches
    except Exception:
        return []


def scan(creds, spreadsheet_id: str, cfg: Config, llm: Callable[[str], str],
         now: datetime) -> list[str]:
    """Run the scanner; returns notes for the digest. Never raises."""
    try:
        rows = sheets.read_rows(creds, spreadsheet_id)
        tracked = [r for r in rows if r["Status"] in TRACKED_STATUSES]
        if not tracked:
            return ["scanner: no tracked applications yet"]
        messages = fetch_messages(creds)
        matches = classify(tracked, messages, llm)
        by_id = {r["Job ID"]: r for r in tracked}
        updates: list[tuple[int, str, str]] = []
        notes = []
        for m in matches:
            row = by_id.get(m.job_id)
            if row is None:
                continue
            updates.append((row["_row"], "Last reply", now.strftime("%Y-%m-%d")))
            updates.append((row["_row"], "Reply class", m.classification))
            new_status = _forward_only(row["Status"], _CLASS_TO_STATUS[m.classification])
            if new_status:
                updates.append((row["_row"], "Status", new_status))
                notes.append(f"scanner: {row['Company']} — {m.classification} → {new_status}")
        sheets.update_cells(creds, spreadsheet_id, updates)
        if not notes:
            notes = [f"scanner: {len(messages)} emails checked, no application replies"]
        return notes
    except Exception as exc:  # noqa: BLE001 — scanner must never break the run
        return [f"scanner: FAILED ({type(exc).__name__}: {exc})"]
