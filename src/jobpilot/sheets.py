"""Google Sheets dashboard: the database and the UI in one place."""

from __future__ import annotations

from datetime import datetime

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from jobpilot.models import posted_age
from jobpilot.scorer import Scored

HEADERS = [
    "Date found", "Job ID", "Title", "Company", "Location", "Remote", "Posted",
    "Posted age", "URL", "Source", "Fit", "Why", "Sponsorship", "Resume variant",
    "Status", "Notes", "Applied date", "Last reply", "Reply class",
    "Tailored resume", "Cover letter", "JD keywords", "JD excerpt",
    "Contact", "Draft", "Find people", "Role", "Resume ATS",
]


def col_letter(idx: int) -> str:
    """0-based column index -> A1 letters (0->A, 25->Z, 26->AA)."""
    letters = ""
    idx += 1
    while idx:
        idx, rem = divmod(idx - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


LAST_COL = col_letter(len(HEADERS) - 1)
STATUS_VALUES = [
    "New", "Applied", "Outreach sent", "Response", "Interview", "Offer", "Rejected",
    "Dismissed",
]
STATS_ROWS = [
    ["Metric", "Value"],
    ["Jobs found", "=COUNTA(Jobs!B2:B)+COUNTA(Archive!B2:B)"],
    ["Applied", '=COUNTIF(Jobs!O2:O,"Applied")+COUNTIF(Jobs!O2:O,"Outreach sent")'
                '+COUNTIF(Jobs!O2:O,"Response")+COUNTIF(Jobs!O2:O,"Interview")'
                '+COUNTIF(Jobs!O2:O,"Offer")'],
    ["Responses", '=COUNTIF(Jobs!O2:O,"Response")+COUNTIF(Jobs!O2:O,"Interview")'
                  '+COUNTIF(Jobs!O2:O,"Offer")'],
    ["Interviews", '=COUNTIF(Jobs!O2:O,"Interview")+COUNTIF(Jobs!O2:O,"Offer")'],
    ["Response rate", "=IFERROR(B4/B3,0)"],
    ["Found this week", '=COUNTIF(Jobs!A2:A,">="&TEXT(TODAY()-7,"yyyy-mm-dd"))'
                        '+COUNTIF(Archive!A2:A,">="&TEXT(TODAY()-7,"yyyy-mm-dd"))'],
]


def to_row(s: Scored, now: datetime) -> list:
    p = s.posting
    # Sponsorship-unlikely jobs are auto-rejected: recorded for audit, never shown.
    auto_reject = s.sponsorship_signal == "unlikely"
    return [
        now.strftime("%Y-%m-%d"),
        p.id,
        p.title,
        p.company,
        p.location,
        {True: "yes", False: "no", None: ""}[p.remote],
        p.posted_at.strftime("%Y-%m-%d %H:%M") if p.posted_at else "",
        posted_age(p.posted_at, now),
        p.url,
        p.source,
        s.fit_score if s.fit_score is not None else "—",
        s.why,
        s.sponsorship_signal,
        s.resume_variant,
        "Rejected" if auto_reject else "New",
        "auto-rejected: sponsorship unlikely" if auto_reject else "",
        "",  # Applied date (UI)
        "",  # Last reply (inbox-watch)
        "",  # Reply class (inbox-watch)
        "",  # Tailored resume (tailor)
        "",  # Cover letter (tailor)
        "",  # JD keywords (tailor)
        p.description[:5000],  # JD excerpt — enables on-demand tailoring later
        "",  # Contact (outreach)
        "",  # Draft (outreach)
        "",  # Find people (outreach)
        s.role_category,
        "",  # Resume ATS (judge score for the tailored resume)
    ]


def _svc(creds):
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def ensure_headers(creds, spreadsheet_id: str) -> None:
    """Idempotently (re)write the header row so new columns appear on old sheets."""
    _svc(creds).spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range="Jobs!A1",
        valueInputOption="RAW",
        body={"values": [HEADERS]},
    ).execute()


def ensure_dashboard(creds, spreadsheet_id: str) -> str:
    """Return a ready spreadsheet id, creating the JobPilot dashboard if needed."""
    svc = _svc(creds)
    if spreadsheet_id:
        ensure_headers(creds, spreadsheet_id)
        return spreadsheet_id
    doc = svc.spreadsheets().create(
        body={
            "properties": {"title": "JobPilot"},
            "sheets": [
                {"properties": {"title": "Jobs", "sheetId": 0}},
                {"properties": {"title": "Stats", "sheetId": 1}},
                {"properties": {"title": "Feedback", "sheetId": 2}},
            ],
        }
    ).execute()
    sid = doc["spreadsheetId"]
    svc.spreadsheets().values().batchUpdate(
        spreadsheetId=sid,
        body={
            "valueInputOption": "USER_ENTERED",
            "data": [
                {"range": "Jobs!A1", "values": [HEADERS]},
                {"range": "Stats!A1", "values": STATS_ROWS},
                {"range": "Feedback!A1", "values": [["Date", "Feedback"]]},
            ],
        },
    ).execute()
    svc.spreadsheets().batchUpdate(
        spreadsheetId=sid,
        body={
            "requests": [
                {  # Status dropdown on column O
                    "setDataValidation": {
                        "range": {
                            "sheetId": 0, "startRowIndex": 1, "endRowIndex": 5000,
                            "startColumnIndex": 14, "endColumnIndex": 15,
                        },
                        "rule": {
                            "condition": {
                                "type": "ONE_OF_LIST",
                                "values": [
                                    {"userEnteredValue": v} for v in STATUS_VALUES
                                ],
                            },
                            "showCustomUi": True,
                            "strict": False,
                        },
                    }
                },
                {  # bold frozen header row
                    "updateSheetProperties": {
                        "properties": {
                            "sheetId": 0,
                            "gridProperties": {"frozenRowCount": 1},
                        },
                        "fields": "gridProperties.frozenRowCount",
                    }
                },
            ]
        },
    ).execute()
    return sid


def refresh_stats(creds, spreadsheet_id: str) -> None:
    """Rewrite the Stats formulas; the live tab has decayed to literal zeros."""
    _svc(creds).spreadsheets().values().update(
        spreadsheetId=spreadsheet_id, range="Stats!A1",
        valueInputOption="USER_ENTERED", body={"values": STATS_ROWS},
    ).execute()


def ensure_archive_tab(creds, spreadsheet_id: str) -> None:
    """Archive holds aged out, low fit, and dismissed rows. Same HEADERS as
    Jobs, so dedup can recompute keys from Title+Company there too."""
    svc = _svc(creds)
    meta = svc.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    titles = [s["properties"]["title"] for s in meta["sheets"]]
    if "Archive" in titles:
        return
    svc.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": [{"addSheet": {"properties": {"title": "Archive"}}}]},
    ).execute()
    svc.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id, range="Archive!A1",
        valueInputOption="RAW", body={"values": [HEADERS]},
    ).execute()


def known_ids(creds, spreadsheet_id: str) -> set[str]:
    """Dedup keys recomputed from Title+Company — NOT the stored Job ID column.

    Stored ids written before BL-20 hashed location into the key, so matching
    against them would re-add every already-seen job under the new scheme.

    Unions Jobs and Archive, so a job that aged out or scored below the write
    threshold is still remembered and never comes back as "new."
    """
    from jobpilot import dedup

    svc = _svc(creds)

    def _pairs(tab: str) -> list[list[str]]:
        resp = svc.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range=f"{tab}!C2:D").execute()
        return resp.get("values", [])

    jobs_pairs = _pairs("Jobs")  # a real failure here is a real error: let it raise
    try:
        archive_pairs = _pairs("Archive")
    except HttpError:
        archive_pairs = []  # a hand-deleted tab degrades instead of crashing the run

    return {
        dedup.key(company=row[1], title=row[0])
        for row in jobs_pairs + archive_pairs
        if len(row) >= 2
    }


def route_jobs(scored: list[Scored], min_fit: int) -> tuple[list[Scored], list[Scored]]:
    """Split scored jobs the way the sheet writes them: (to Jobs, to Archive).

    Sponsorship "unlikely" auto-rejects route to Archive regardless of fit
    score (checked first, so a high fit score never saves one); everything
    else scoring below min_fit also routes to Archive. Unscored jobs
    (fit_score is None) appear in neither list, so they retry next run
    instead of getting stuck as a dead dedup key.

    This is the single source of truth for the Jobs/Archive split: both
    append_jobs (what gets written) and pipeline.run (n_matches and the
    digest shortlist) call it, so the digest can never describe a job that
    isn't actually in the Jobs tab.
    """
    to_jobs, to_archive = [], []
    for s in scored:
        if s.fit_score is None:
            continue
        if s.sponsorship_signal == "unlikely" or s.fit_score < min_fit:
            to_archive.append(s)
        else:
            to_jobs.append(s)
    return to_jobs, to_archive


def append_jobs(creds, spreadsheet_id: str, scored: list[Scored], now: datetime,
                min_fit: int) -> tuple[int, int]:
    """Write scored rows the way route_jobs splits them: the Jobs-bound jobs to
    Jobs, the Archive-bound jobs to Archive. Archived rows keep the Status
    "Rejected" / Notes "auto-rejected: sponsorship unlikely" that to_row
    already set for sponsorship auto-rejects; genuine low-fit rows get
    relabeled Status "Low fit" instead. Unscored rows (fit_score is None)
    never reach either list, so they retry next run, since a row that's
    never written never enters dedup memory.

    Returns (n_jobs, n_archived).
    """
    to_jobs, to_archive = route_jobs(scored, min_fit)
    jobs_rows = [to_row(s, now) for s in to_jobs]
    archive_rows = []
    for s in to_archive:
        row = to_row(s, now)
        if s.sponsorship_signal != "unlikely":
            row[14] = "Low fit"
            row[15] = f"below write threshold {min_fit}"
        archive_rows.append(row)
    if not jobs_rows and not archive_rows:
        return 0, 0
    svc = _svc(creds)
    for tab, rows in (("Jobs", jobs_rows), ("Archive", archive_rows)):
        if rows:
            svc.spreadsheets().values().append(
                spreadsheetId=spreadsheet_id, range=f"{tab}!A1",
                valueInputOption="USER_ENTERED", insertDataOption="INSERT_ROWS",
                body={"values": rows},
            ).execute()
    return len(jobs_rows), len(archive_rows)


def url_for(spreadsheet_id: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"


def ensure_reports_tab(creds, spreadsheet_id: str) -> None:
    svc = _svc(creds)
    meta = svc.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    titles = [s["properties"]["title"] for s in meta["sheets"]]
    if "Reports" in titles:
        return
    svc.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": [{"addSheet": {"properties": {"title": "Reports"}}}]},
    ).execute()
    svc.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id, range="Reports!A1", valueInputOption="RAW",
        body={"values": [["Timestamp", "Kind", "Key", "Score", "Report JSON"]]},
    ).execute()


def append_report(creds, spreadsheet_id: str, kind: str, key: str,
                  score: float, report_json: str, timestamp: str) -> None:
    ensure_reports_tab(creds, spreadsheet_id)
    _svc(creds).spreadsheets().values().append(
        spreadsheetId=spreadsheet_id, range="Reports!A1",
        valueInputOption="RAW", insertDataOption="INSERT_ROWS",
        body={"values": [[timestamp, kind, key, score, report_json[:49000]]]},
    ).execute()


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


COMPANIES_HEADERS = [
    "Company", "Careers URL", "ATS", "Slug", "Status", "Last checked",
    "Jobs (last fetch)", "Notes",
]


def ensure_companies_tab(creds, spreadsheet_id: str) -> None:
    svc = _svc(creds)
    meta = svc.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    titles = [s["properties"]["title"] for s in meta["sheets"]]
    if "Companies" in titles:
        return
    svc.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": [{"addSheet": {"properties": {"title": "Companies"}}}]},
    ).execute()
    svc.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id, range="Companies!A1", valueInputOption="RAW",
        body={"values": [COMPANIES_HEADERS]},
    ).execute()


def read_companies(creds, spreadsheet_id: str) -> list[dict]:
    """Companies tab rows as dicts keyed by header, with 1-based row numbers."""
    ensure_companies_tab(creds, spreadsheet_id)
    resp = (
        _svc(creds)
        .spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range="Companies!A2:H")
        .execute()
    )
    rows = []
    for i, values in enumerate(resp.get("values", []), start=2):
        padded = values + [""] * (len(COMPANIES_HEADERS) - len(values))
        rows.append({"_row": i, **dict(zip(COMPANIES_HEADERS, padded))})
    return rows


def update_company_rows(creds, spreadsheet_id: str,
                        updates: list[tuple[int, list[str]]]) -> None:
    """Batch-write C..H (ATS, Slug, Status, Last checked, Jobs, Notes) per row."""
    if not updates:
        return
    data = [{"range": f"Companies!C{row}", "values": [vals]} for row, vals in updates]
    _svc(creds).spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"valueInputOption": "RAW", "data": data},
    ).execute()


OUTREACH_HEADERS = [
    "Searched at", "Company", "Domain", "Resume variant", "Variant reason",
    "Subject", "Guessed emails", "Draft", "Resume", "Cover letter", "Status", "Notes",
    "Emails found",
]


def ensure_outreach_tab(creds, spreadsheet_id: str) -> None:
    svc = _svc(creds)
    meta = svc.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    titles = [s["properties"]["title"] for s in meta["sheets"]]
    if "Outreach" in titles:
        return
    svc.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": [{"addSheet": {"properties": {"title": "Outreach"}}}]},
    ).execute()
    svc.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id, range="Outreach!A1", valueInputOption="RAW",
        body={"values": [OUTREACH_HEADERS]},
    ).execute()


def append_outreach_row(creds, spreadsheet_id: str, row: list) -> None:
    ensure_outreach_tab(creds, spreadsheet_id)
    _svc(creds).spreadsheets().values().append(
        spreadsheetId=spreadsheet_id, range="Outreach!A1",
        valueInputOption="USER_ENTERED", insertDataOption="INSERT_ROWS",
        body={"values": [row]},
    ).execute()


def read_outreach(creds, spreadsheet_id: str) -> list[dict]:
    """Outreach tab rows as dicts keyed by header, with 1-based row numbers."""
    ensure_outreach_tab(creds, spreadsheet_id)
    resp = (
        _svc(creds)
        .spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range="Outreach!A2:M")
        .execute()
    )
    rows = []
    for i, values in enumerate(resp.get("values", []), start=2):
        padded = values + [""] * (len(OUTREACH_HEADERS) - len(values))
        rows.append({"_row": i, **dict(zip(OUTREACH_HEADERS, padded))})
    return rows


KNOWLEDGE_HEADERS = ["Source", "Updated", "Content"]
EXTRAS_HINT = ("Edit this row freely — facts the auto sources miss "
               "(LinkedIn highlights, awards, talks). Refresh never touches it.")


def ensure_knowledge_tab(creds, spreadsheet_id: str) -> None:
    svc = _svc(creds)
    meta = svc.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    titles = [s["properties"]["title"] for s in meta["sheets"]]
    if "Knowledge" in titles:
        return
    svc.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": [{"addSheet": {"properties": {"title": "Knowledge"}}}]},
    ).execute()
    svc.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id, range="Knowledge!A1", valueInputOption="RAW",
        body={"values": [KNOWLEDGE_HEADERS, ["extras", "", EXTRAS_HINT]]},
    ).execute()


def read_knowledge(creds, spreadsheet_id: str) -> list[list[str]]:
    """Knowledge rows as [source, updated, content]."""
    ensure_knowledge_tab(creds, spreadsheet_id)
    resp = (
        _svc(creds)
        .spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range="Knowledge!A2:C")
        .execute()
    )
    return [row + [""] * (3 - len(row)) for row in resp.get("values", [])]


def write_knowledge(creds, spreadsheet_id: str, sections: dict[str, str],
                    now_str: str) -> None:
    """Replace the auto-built rows; user-owned rows (e.g. extras) survive."""
    existing = read_knowledge(creds, spreadsheet_id)
    kept = [r for r in existing if r[0] and r[0] not in sections]
    values = [[name, now_str, content[:45000]]
              for name, content in sections.items() if content] + kept
    svc = _svc(creds)
    svc.spreadsheets().values().clear(
        spreadsheetId=spreadsheet_id, range="Knowledge!A2:C1000").execute()
    if values:
        svc.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id, range="Knowledge!A2",
            valueInputOption="RAW", body={"values": values},
        ).execute()


def read_rows(creds, spreadsheet_id: str) -> list[dict]:
    """All job rows as dicts keyed by header, with 1-based sheet row numbers."""
    resp = (
        _svc(creds)
        .spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=f"Jobs!A2:{LAST_COL}")
        .execute()
    )
    rows = []
    for i, values in enumerate(resp.get("values", []), start=2):
        padded = values + [""] * (len(HEADERS) - len(values))
        rows.append({"_row": i, **dict(zip(HEADERS, padded))})
    return rows


def update_cells(creds, spreadsheet_id: str, updates: list[tuple[int, str, str]]) -> None:
    """Batch update cells given (sheet_row, header_name, value) triples."""
    if not updates:
        return
    data = []
    for row, header, value in updates:
        col = col_letter(HEADERS.index(header))
        data.append({"range": f"Jobs!{col}{row}", "values": [[value]]})
    _svc(creds).spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"valueInputOption": "USER_ENTERED", "data": data},
    ).execute()
