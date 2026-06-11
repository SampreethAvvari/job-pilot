"""Google Sheets dashboard: the database and the UI in one place."""

from __future__ import annotations

from datetime import datetime

from googleapiclient.discovery import build

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
    ["Jobs found", "=COUNTA(Jobs!B2:B)"],
    ["Applied", '=COUNTIF(Jobs!O2:O,"Applied")+COUNTIF(Jobs!O2:O,"Outreach sent")'
                '+COUNTIF(Jobs!O2:O,"Response")+COUNTIF(Jobs!O2:O,"Interview")'
                '+COUNTIF(Jobs!O2:O,"Offer")'],
    ["Responses", '=COUNTIF(Jobs!O2:O,"Response")+COUNTIF(Jobs!O2:O,"Interview")'
                  '+COUNTIF(Jobs!O2:O,"Offer")'],
    ["Interviews", '=COUNTIF(Jobs!O2:O,"Interview")+COUNTIF(Jobs!O2:O,"Offer")'],
    ["Response rate", "=IFERROR(B4/B3,0)"],
    ["Found this week", '=COUNTIF(Jobs!A2:A,">="&TEXT(TODAY()-7,"yyyy-mm-dd"))'],
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


def known_ids(creds, spreadsheet_id: str) -> set[str]:
    """Dedup keys recomputed from Title+Company — NOT the stored Job ID column.

    Stored ids written before BL-20 hashed location into the key, so matching
    against them would re-add every already-seen job under the new scheme.
    """
    from jobpilot import dedup

    resp = (
        _svc(creds)
        .spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range="Jobs!C2:D")
        .execute()
    )
    return {
        dedup.key(company=row[1], title=row[0])
        for row in resp.get("values", [])
        if len(row) >= 2
    }


def append_jobs(creds, spreadsheet_id: str, scored: list[Scored], now: datetime) -> None:
    if not scored:
        return
    _svc(creds).spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range="Jobs!A1",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": [to_row(s, now) for s in scored]},
    ).execute()


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
