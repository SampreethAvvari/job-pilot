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
