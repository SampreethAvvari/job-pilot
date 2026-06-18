"""Outreach drafts: find recruiter contacts, draft a personalized email into Gmail.

NOTHING IS EVER SENT — drafts only. The user reviews and sends from Gmail.
"""

from __future__ import annotations

import base64
import re
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Callable

import httpx
from googleapiclient.discovery import build
from pydantic import BaseModel

from jobpilot import sheets
from jobpilot.apollo import find_contacts, linkedin_people_search_url
from jobpilot.config import Config, Profile

PROMPT = Path(__file__).parent / "prompts" / "outreach_v1.txt"
MAX_PER_RUN = 10


class Draft(BaseModel):
    subject: str
    body: str


def _gmail(creds):
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


_CLOSING = re.compile(
    r"^(thanks|thank you|best|best regards|kind regards|warm regards|regards|"
    r"sincerely|cheers)[,.!]?$", re.IGNORECASE)


def strip_closing(body: str, name: str) -> str:
    """Drop the LLM's own sign-off so the appended signature is the only one."""
    lines = body.rstrip().splitlines()
    while lines and (not lines[-1].strip() or _CLOSING.match(lines[-1].strip())
                     or lines[-1].strip() == name):
        lines.pop()
    return "\n".join(lines).rstrip()


def signature(profile: Profile) -> str:
    """Deterministic signature block — never left to the LLM."""
    links = [(label, url) for label, url in (
        ("Portfolio", profile.portfolio),
        ("LinkedIn", profile.linkedin),
        ("GitHub", profile.github),
    ) if url]
    lines = ["Best,", profile.name]
    lines.extend(f"{label}: {url}" for label, url in links)
    return "\n".join(lines)


def _drive_pdf_bytes(creds, url: str) -> bytes | None:
    """Bytes of a Drive PDF given its /file/d/<id>/view URL; None when unavailable."""
    m = re.search(r"/d/([\w-]+)", url or "")
    if not m:
        return None
    try:
        drive = build("drive", "v3", credentials=creds, cache_discovery=False)
        return drive.files().get_media(fileId=m.group(1)).execute()
    except Exception:  # noqa: BLE001 — attachment is best-effort
        return None


def create_gmail_draft(creds, to: str, subject: str, body: str,
                       attachment: tuple[str, bytes] | None = None,
                       attachments: list[tuple[str, bytes]] | None = None) -> str:
    """Create the draft (optionally with PDFs attached); return a Gmail URL.

    `attachment` (single) is kept for back-compat; `attachments` (list) lets a draft
    carry several files, e.g. a resume and a cover letter.
    """
    files = list(attachments or [])
    if attachment:
        files.append(attachment)
    if files:
        msg = MIMEMultipart()
        msg.attach(MIMEText(body))
        for fname, data in files:
            part = MIMEApplication(data, _subtype="pdf")
            part.add_header("Content-Disposition", "attachment", filename=fname)
            msg.attach(part)
    else:
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
        name=cfg.profile.name,
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
        if not contact or not contact.get("email"):
            # HARD RULE: no recipient email -> no draft, ever.
            sheets.update_cells(creds, spreadsheet_id, [
                (row["_row"], "Contact", "no recruiter email found — draft skipped"),
                (row["_row"], "Find people", linkedin_people_search_url(company)),
            ])
            return f"outreach skipped for {company}: no recruiter email found"
        draft = draft_outreach(row, cfg, llm, contact)
        body = f"{strip_closing(draft.body, cfg.profile.name)}\n\n{signature(cfg.profile)}\n"
        attachment = None
        pdf = _drive_pdf_bytes(creds, row.get("Tailored resume", ""))
        if pdf:
            fname = re.sub(r"[^A-Za-z0-9]+", "_", cfg.profile.name) + "_Resume.pdf"
            attachment = (fname, pdf)
        link = create_gmail_draft(creds, contact["email"], draft.subject, body,
                                  attachment)
        sheets.update_cells(creds, spreadsheet_id, [
            (row["_row"], "Contact",
             f"{contact['name']} ({contact['title']}) <{contact['email']}>"),
            (row["_row"], "Draft", link),
            (row["_row"], "Find people", linkedin_people_search_url(company)),
        ])
        return f"outreach drafted: {company} — {row['Title']} -> {contact['email']}"
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
