"""Move aged out, low fit, and dismissed Jobs rows to the Archive tab.

Archive preserves Title+Company, so dedup keeps recognizing these jobs and a
swept row can never re enter the console. Rows the owner acted on (applied,
any reply, any advanced status) are never touched. Runs nightly as part of
the full pipeline (see pipeline.run) and doubles as the one time migration
tool for the pre-redesign backlog via `python -m jobpilot --archive-sweep`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jobpilot.sheets import HEADERS, LAST_COL, _svc, col_letter

_IDX = {name: i for i, name in enumerate(HEADERS)}
_PROTECTED = {"Applied", "Outreach sent", "Response", "Interview", "Offer"}
_JOB_ID_COL = col_letter(_IDX["Job ID"])


def _parse(ts: str, fmt: str) -> datetime | None:
    try:
        return datetime.strptime(ts.strip(), fmt).replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        return None


def _cell(row: list[str], name: str) -> str:
    i = _IDX[name]
    return row[i].strip() if i < len(row) and row[i] else ""


def select_archivable(rows: list[list[str]], now: datetime, min_fit: int,
                      max_age_days: int) -> list[tuple[int, str]]:
    """Pick Jobs rows to move to Archive; return (0-based row index, reason).

    A row with a _PROTECTED status, an Applied date, or a Last reply is never
    touched, regardless of age or fit — those are the rows the owner has
    already acted on, and that guard wins over every reason below. Otherwise,
    in order: "Dismissed" -> dismissed, "Rejected" -> auto rejected (the
    sponsorship auto-reject written at write time), any other status besides
    blank/"New" is left alone (conservative default for a status this sweep
    doesn't recognize, e.g. "Low fit", which only ever appears in Archive).
    A "manual" sourced row has neither a real Fit score nor a Posted date, so
    it is exempt from both checks and is only swept once its Date found ages
    past max_age_days. Everything else is judged on Fit (unparseable ->
    unscored, below min_fit -> low fit) and then Posted (missing -> undated,
    older than max_age_days -> stale).
    """
    cutoff = now - timedelta(days=max_age_days)
    out: list[tuple[int, str]] = []
    for i, row in enumerate(rows):
        status = _cell(row, "Status")
        if status in _PROTECTED or _cell(row, "Applied date") or _cell(row, "Last reply"):
            continue
        if status == "Dismissed":
            out.append((i, "dismissed"))
            continue
        if status == "Rejected":
            out.append((i, "auto rejected"))
            continue
        if status not in ("", "New"):
            continue
        if _cell(row, "Source") == "manual":
            found = _parse(_cell(row, "Date found"), "%Y-%m-%d")
            if found and found < cutoff:
                out.append((i, "manual aged out"))
            continue
        fit_raw = _cell(row, "Fit")
        try:
            fit = int(fit_raw)
        except ValueError:
            out.append((i, "unscored"))
            continue
        if fit < min_fit:
            out.append((i, "low fit"))
            continue
        posted = _parse(_cell(row, "Posted"), "%Y-%m-%d %H:%M")
        if posted is None:
            out.append((i, "undated"))
        elif posted < cutoff:
            out.append((i, "stale"))
    return out


def _delete_ranges(indexes: list[int]) -> list[tuple[int, int]]:
    """Coalesce 0-based Jobs data-row indexes into contiguous deleteDimension
    (startIndex, endIndex) ranges, highest first.

    A data index's deleteDimension row (0-based, header included) is index+1;
    endIndex is exclusive, so a contiguous run from a to b becomes
    (a + 1, b + 2). Highest-first ordering means deleting one range never
    shifts the row numbers a range still to come refers to. This is what
    keeps a ~4,300-row migration to a handful of deleteDimension requests in
    one batchUpdate instead of one request per row (a real server-side
    timeout/failure risk at that size).
    """
    ranges: list[tuple[int, int]] = []
    for i in sorted(indexes):
        if ranges and i == ranges[-1][1] - 1:
            ranges[-1] = (ranges[-1][0], i + 2)
        else:
            ranges.append((i + 1, i + 2))
    return list(reversed(ranges))


def sweep(creds, spreadsheet_id: str, cfg, now: datetime) -> list[str]:
    """Move archivable Jobs rows to Archive, then delete them from Jobs.

    Deletion is the dangerous half against the owner's live data, so it is
    the last and most guarded step: rows are appended to Archive first, then
    re-verified by Job ID immediately before the delete request goes out. A
    concurrent append to Jobs can't shift the indexes read here, but a
    concurrent manual edit could — any mismatch aborts the whole delete batch
    rather than risk removing the wrong row. An aborted delete leaves a
    duplicate copy sitting in Archive until the next sweep succeeds, which is
    harmless: known_ids() unions Jobs and Archive, so a duplicate there never
    resurfaces a job as "new". The delete itself is one batchUpdate of
    coalesced ranges (see _delete_ranges), not one request per row.
    """
    svc = _svc(creds)
    resp = svc.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=f"Jobs!A2:{LAST_COL}").execute()
    rows = resp.get("values", [])
    picks = select_archivable(rows, now, cfg.scoring.threshold,
                              cfg.caps.board_freshness_days)
    if not picks:
        return ["archive sweep: nothing to move"]

    moved = [rows[i] + [""] * (len(HEADERS) - len(rows[i])) for i, _ in picks]
    svc.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id, range="Archive!A1",
        valueInputOption="USER_ENTERED", insertDataOption="INSERT_ROWS",
        body={"values": moved},
    ).execute()

    # Re-verify ids straight before deleting: a concurrent append cannot shift
    # existing row indexes, but a concurrent manual edit could.
    check = svc.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"Jobs!{_JOB_ID_COL}2:{_JOB_ID_COL}").execute().get("values", [])
    stale_check = [
        i for i, _ in picks
        if i >= len(check) or (check[i][0] if check[i] else "") != _cell(rows[i], "Job ID")
    ]
    if stale_check:
        return [f"archive sweep: aborted delete, sheet changed under us "
                f"({len(stale_check)} mismatches); rows copied to Archive, "
                f"next sweep will retry"]

    # Resolved from spreadsheet meta, never assumed: Jobs is sheetId 0 only on
    # a brand new dashboard (ensure_dashboard), and nothing guarantees that
    # stays true forever (tabs can be reordered/recreated by hand).
    meta = svc.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    jobs_sheet_id = next(s["properties"]["sheetId"] for s in meta["sheets"]
                         if s["properties"]["title"] == "Jobs")
    requests = [
        {"deleteDimension": {"range": {
            "sheetId": jobs_sheet_id, "dimension": "ROWS",
            "startIndex": start, "endIndex": end}}}
        for start, end in _delete_ranges([i for i, _ in picks])
    ]
    svc.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id, body={"requests": requests}).execute()

    reasons: dict[str, int] = {}
    for _, r in picks:
        reasons[r] = reasons.get(r, 0) + 1
    detail = ", ".join(f"{v} {k}" for k, v in sorted(reasons.items()))
    return [f"archive sweep: moved {len(picks)} rows ({detail})"]
