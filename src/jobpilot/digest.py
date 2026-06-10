"""Morning digest: one HTML email summarizing today's matches."""

from __future__ import annotations

import base64
from datetime import datetime
from email.mime.text import MIMEText

from googleapiclient.discovery import build

from jobpilot.config import Config
from jobpilot.models import posted_age
from jobpilot.scorer import Scored


def build_html(
    scored: list[Scored], sheet_url: str, now: datetime, threshold: int, notes: list[str]
) -> str:
    ranked = sorted(scored, key=lambda s: s.fit_score or -1, reverse=True)
    shortlist = [s for s in ranked if (s.fit_score or 0) >= threshold]
    rest = len(ranked) - len(shortlist)

    rows = []
    for s in shortlist:
        p = s.posting
        rows.append(
            f"<tr><td><b>{s.fit_score}</b></td>"
            f'<td><a href="{p.url}">{p.title}</a></td>'
            f"<td>{p.company}</td><td>{p.location}</td>"
            f"<td>{posted_age(p.posted_at, now)}</td>"
            f"<td>{s.sponsorship_signal}</td><td>{s.resume_variant}</td>"
            f"<td>{s.why}</td></tr>"
        )
    table = (
        "<table border='1' cellpadding='6' cellspacing='0' "
        "style='border-collapse:collapse;font-family:sans-serif;font-size:13px'>"
        "<tr><th>Fit</th><th>Role</th><th>Company</th><th>Location</th><th>Posted</th>"
        "<th>Sponsor</th><th>Resume</th><th>Why</th></tr>" + "".join(rows) + "</table>"
        if rows
        else "<p>No jobs above threshold today.</p>"
    )
    notes_html = "".join(f"<li>{n}</li>" for n in notes)
    return (
        f"<h2>JobPilot — {now.strftime('%a %b %d')}</h2>"
        f"<p><b>{len(shortlist)}</b> matches ≥ {threshold} "
        f"({rest} more below threshold, all logged).</p>"
        f"{table}"
        f'<p><a href="{sheet_url}">Open the dashboard</a> — set Status as you apply.</p>'
        f"<h4>Run notes</h4><ul>{notes_html}</ul>"
    )


def send(creds, cfg: Config, html: str, now: datetime, n_matches: int) -> None:
    msg = MIMEText(html, "html")
    msg["To"] = cfg.digest.to
    msg["Subject"] = f"JobPilot digest — {now.strftime('%b %d')}: {n_matches} matches"
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    build("gmail", "v1", credentials=creds, cache_discovery=False).users().messages().send(
        userId="me", body={"raw": raw}
    ).execute()
