"""Outreach drafts: find recruiter contacts, draft a personalized email into Gmail.

NOTHING IS EVER SENT — drafts only. The user reviews and sends from Gmail.
"""

from __future__ import annotations

import base64
from datetime import datetime
from email.mime.text import MIMEText
from pathlib import Path
from typing import Callable

import httpx
from googleapiclient.discovery import build
from pydantic import BaseModel

from jobpilot import sheets
from jobpilot.apollo import find_contacts, linkedin_people_search_url
from jobpilot.config import Config

PROMPT = Path(__file__).parent / "prompts" / "outreach_v1.txt"
MAX_PER_RUN = 10


class Draft(BaseModel):
    subject: str
    body: str


def _gmail(creds):
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def create_gmail_draft(creds, to: str, subject: str, body: str) -> str:
    """Create the draft; return a Gmail compose URL for the dashboard."""
    msg = MIMEText(body)
    if to:
        msg["To"] = to
    msg["Subject"] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    draft = _gmail(creds).users().drafts().create(
        userId="me", body={"message": {"raw": raw}}
    ).execute()
    message_id = draft.get("message", {}).get("id", "")
    return f"https://mail.google.com/mail/u/0/#drafts?compose={message_id}"


def draft_outreach(row: dict, cfg: Config, llm: Callable[[str], str],
                   contact: dict | None) -> Draft:
    template = PROMPT.read_text(encoding="utf-8")
    prompt = template.format(
        profile_summary=cfg.profile.summary,
        company=row["Company"],
        title=row["Title"],
        description=(row.get("JD excerpt") or "")[:2500],
        contact_name=(contact or {}).get("name", ""),
        contact_title=(contact or {}).get("title", ""),
    )
    last: Exception | None = None
    for _ in range(2):
        try:
            return Draft.model_validate_json(llm(prompt))
        except Exception as exc:
            last = exc
    raise RuntimeError(f"outreach draft failed: {last}")


def outreach_row(creds, spreadsheet_id: str, row: dict, cfg: Config,
                 llm: Callable[[str], str], client: httpx.Client) -> str:
    company = row["Company"]
    try:
        contacts = find_contacts(company, client)
        contact = contacts[0] if contacts else None
        draft = draft_outreach(row, cfg, llm, contact)
        link = create_gmail_draft(
            creds, (contact or {}).get("email", ""), draft.subject, draft.body
        )
        contact_label = (
            f"{contact['name']} ({contact['title']})" + (f" <{contact['email']}>" if contact.get("email") else "")
            if contact else "no contact found — use Find people"
        )
        sheets.update_cells(creds, spreadsheet_id, [
            (row["_row"], "Contact", contact_label),
            (row["_row"], "Draft", link),
            (row["_row"], "Find people", linkedin_people_search_url(company)),
        ])
        return f"outreach drafted: {company} — {row['Title']}"
    except Exception as exc:  # noqa: BLE001
        return f"outreach FAILED for {company}: {type(exc).__name__}: {exc}"


def auto_outreach(creds, spreadsheet_id: str, cfg: Config, llm: Callable[[str], str],
                  now: datetime) -> list[str]:
    """Draft outreach for newly Applied jobs that have no draft yet."""
    rows = sheets.read_rows(creds, spreadsheet_id)
    todo = [
        r for r in rows
        if r.get("Status") == "Applied" and not r.get("Draft")
    ][:MAX_PER_RUN]
    if not todo:
        return ["outreach: nothing newly applied"]
    client = httpx.Client(timeout=30)
    return [outreach_row(creds, spreadsheet_id, r, cfg, llm, client) for r in todo]
