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
