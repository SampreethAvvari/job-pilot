# Console Cards + Freshness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Only fresh (14 day), high fit (75+) jobs reach the console; everything else flows to an Archive tab that preserves dedup memory; every tailored resume derives from the single AIE master; the console is rebuilt as a light premium card UI on the existing Sheet data layer.

**Architecture:** Pipeline gates move to write time (freshness at fetch, fit split at append, nightly sweep for aging). The UI keeps all API routes and lib readers, gains a token based light design system, shared primitives, one jobs store, and card layouts per tab.

**Tech Stack:** Python 3.12 + pytest (pipeline), Next.js 16 App Router + React 19 + Tailwind v4 CSS-first (console), Google Sheets API, Vertex AI Gemini (unchanged).

**Spec:** `docs/superpowers/specs/2026-07-23-console-cards-freshness-design.md`

## Global Constraints

- Work happens on branch `redesign/console-cards-freshness`. Commit per task locally. NEVER push, merge, deploy, or update secrets: those steps are owner gated in Task 18.
- The repo is PUBLIC. Never write personal data (real resume text, emails, phone numbers, file ids) into tracked files. Real resume content goes only under `private/` (gitignored) and Secret Manager.
- Sheet HEADERS (28 columns A..AB) are a contract mirrored in `src/jobpilot/sheets.py:12` and `ui/src/lib/types.ts:4`. Do not add, remove, or reorder columns.
- Fit threshold is 75 everywhere and comes from one knob per layer: `cfg.scoring.threshold` (pipeline) and `MIN_FIT` in `ui/src/lib/company-match.ts` (console). Never hardcode 75 elsewhere.
- All user facing copy: no em dashes, no en dashes, no hyphens used as dashes. Plain direct wording. Placeholders use a middot (·), never a dash.
- UI tasks (6 through 16): the implementer MUST load the `frontend-design:frontend-design` skill before writing components, and use only the tokens and primitives defined in Tasks 6 and 7 (no inline hex colors, no arbitrary px paddings).
- Python verification: `python -m pytest tests/ -q` from repo root (139 tests pass today; keep them green). UI verification: `npm run build` and `npm run lint` inside `ui/`.
- Commits are authored as the repo user (SampreethAvvari). No co-author trailers.

---

### Task 1: Pipeline freshness gate (14 day boards, drop undated)

**Files:**
- Modify: `src/jobpilot/config.py:63` (board_freshness_days)
- Modify: `src/jobpilot/pipeline.py:95-127` (quality_filter + note)
- Modify: `src/jobpilot/sources/greenhouse.py:30` (first_published only)
- Test: `tests/test_pipeline.py`, `tests/test_sources.py`

**Interfaces:**
- Consumes: `Posting` model (`src/jobpilot/models.py`), `RUN_STATS` dict (`src/jobpilot/sources/common.py`).
- Produces: `quality_filter(postings, cfg, now)` same signature, new behavior: drops `posted_at is None` and records `RUN_STATS["dropped_undated"]` and `RUN_STATS["dropped_stale"]` as ints.

- [ ] **Step 1: Write failing tests** (append to `tests/test_pipeline.py`; follow the existing Posting fixture style in that file: read the top of the file first and reuse its helper for building postings)

```python
def _posting(source="adzuna", days_old=1, undated=False, **kw):
    from datetime import datetime, timedelta, timezone
    from jobpilot.models import Posting
    now = datetime(2026, 7, 23, tzinfo=timezone.utc)
    return Posting(
        id="", title=kw.get("title", "AI Engineer"), company=kw.get("company", "Acme"),
        location=kw.get("location", "New York, NY"), url="https://x.example/j",
        source=source, description=kw.get("description", "build llm products"),
        posted_at=None if undated else now - timedelta(days=days_old),
    )


def test_quality_filter_drops_undated_postings(base_cfg):
    from datetime import datetime, timezone
    from jobpilot.pipeline import quality_filter
    from jobpilot.sources import common
    now = datetime(2026, 7, 23, tzinfo=timezone.utc)
    common.RUN_STATS.clear()
    kept = quality_filter([_posting(undated=True), _posting(days_old=1)], base_cfg, now)
    assert len(kept) == 1 and kept[0].posted_at is not None
    assert common.RUN_STATS["dropped_undated"] == 1


def test_quality_filter_board_window_is_14_days(base_cfg):
    from datetime import datetime, timezone
    from jobpilot.pipeline import quality_filter
    now = datetime(2026, 7, 23, tzinfo=timezone.utc)
    fresh_board = _posting(source="greenhouse", days_old=10)
    stale_board = _posting(source="greenhouse", days_old=20)
    kept = quality_filter([fresh_board, stale_board], base_cfg, now)
    assert kept == [fresh_board]
```

If `tests/test_pipeline.py` has no `base_cfg` fixture, add one mirroring how existing tests build a `Config` (look for `Config(` in the test file or `tests/fixtures/`).

- [ ] **Step 2: Run tests, verify they fail**

Run: `python -m pytest tests/test_pipeline.py -q -k "undated or board_window"`
Expected: 2 failures (undated postings currently kept; board window currently 60).

- [ ] **Step 3: Implement**

`src/jobpilot/config.py`: change line 63 (comment updated too):

```python
    # Board sources list a job only while it is open, but the console promises a
    # fresh list, so boards get 14 days and aggregators keep 7.
    board_freshness_days: int = 14
```

`src/jobpilot/pipeline.py` `quality_filter` loop, replace the freshness check (lines 104-107) with:

```python
    from jobpilot.sources import common as sources_common
    for p in postings:
        limit = board_cutoff if p.source in ATS_SOURCES else cutoff
        if p.posted_at is None:
            # No trustworthy date, no entry: the job never reaches dedup memory,
            # so a later run that does get a date can still admit it.
            sources_common.RUN_STATS["dropped_undated"] = (
                sources_common.RUN_STATS.get("dropped_undated", 0) + 1)
            continue
        if p.posted_at < limit:
            sources_common.RUN_STATS["dropped_stale"] = (
                sources_common.RUN_STATS.get("dropped_stale", 0) + 1)
            continue
```

(Place the import at module top with the other imports, not inside the loop.) Update `_apply_quality_filter`'s note to include the drop counts:

```python
    fresh = quality_filter(postings, cfg, now)
    stats = sources_common.RUN_STATS
    notes.append(
        f"freshness/seniority filter: kept {len(fresh)} of {len(postings)} "
        f"(windows {cfg.caps.freshness_days}d/{cfg.caps.board_freshness_days}d board, "
        f"dropped undated {stats.get('dropped_undated', 0)}, "
        f"stale {stats.get('dropped_stale', 0)})"
    )
```

`src/jobpilot/sources/greenhouse.py` line 30: use `first_published` only (an edited req must not look new). Change

```python
        posted = parse_dt(j.get("first_published") or j.get("updated_at"))
```

to

```python
        posted = parse_dt(j.get("first_published"))
```

(Match the exact existing expression when editing; the intent is: no `updated_at` fallback.)

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest tests/ -q`
Expected: all pass. If an existing test asserted undated postings are kept or asserted the 60 day window, update that test to the new contract (the spec supersedes it).

- [ ] **Step 5: Commit**

```bash
git add src/jobpilot/config.py src/jobpilot/pipeline.py src/jobpilot/sources/greenhouse.py tests/
git commit -m "feat(pipeline): 14 day board window, drop undated postings with run stats"
```

---

### Task 2: Archive tab, known_ids union, fit 75 write split

**Files:**
- Modify: `src/jobpilot/sheets.py` (ensure_archive_tab, known_ids, append_jobs)
- Modify: `src/jobpilot/pipeline.py:152` area (ensure call)
- Test: `tests/test_sheets_archive.py` (new)

**Interfaces:**
- Consumes: `Scored` (`scorer.py`), `to_row(s, now)` (`sheets.py:50`), `dedup.key(company, title)`.
- Produces:
  - `sheets.ensure_archive_tab(creds, spreadsheet_id) -> None` (idempotent, follows `ensure_reports_tab` pattern at `sheets.py:203`).
  - `sheets.known_ids(creds, spreadsheet_id) -> set[str]` now unions `Jobs!C2:D` and `Archive!C2:D`.
  - `sheets.append_jobs(creds, spreadsheet_id, scored, now, min_fit) -> tuple[int, int]` returns `(n_jobs, n_archived)`. Rows with `fit_score >= min_fit` go to Jobs; scored rows below go to Archive with Status `Low fit`; `fit_score is None` rows are NOT written at all.

- [ ] **Step 1: Write failing tests** (`tests/test_sheets_archive.py`)

```python
"""Archive tab write split and dedup union."""
from datetime import datetime, timezone

from jobpilot import sheets
from jobpilot.models import Posting
from jobpilot.scorer import Scored

NOW = datetime(2026, 7, 23, tzinfo=timezone.utc)


def _scored(fit, title="AI Engineer", company="Acme"):
    p = Posting(id="abc123", title=title, company=company, location="NY",
                url="https://x.example", source="greenhouse", description="d",
                posted_at=NOW)
    s = Scored(posting=p)
    s.fit_score = fit
    return s


class FakeValues:
    def __init__(self, store):
        self.store = store

    def append(self, spreadsheetId, range, valueInputOption, insertDataOption, body):
        self.store.setdefault(range.split("!")[0], []).extend(body["values"])
        return self

    def get(self, spreadsheetId, range):
        self._range = range
        return self

    def execute(self):
        tab = getattr(self, "_range", "Jobs!C2:D").split("!")[0]
        return {"values": self.store.get(f"{tab}!C2:D", [])}


def test_append_jobs_splits_at_min_fit(monkeypatch):
    store = {}
    fake = FakeValues(store)
    monkeypatch.setattr(sheets, "_svc", lambda creds: type(
        "S", (), {"spreadsheets": lambda self: type(
            "P", (), {"values": lambda self: fake})()})())
    n_jobs, n_archived = sheets.append_jobs(None, "sid", [
        _scored(90), _scored(74), _scored(None)], NOW, min_fit=75)
    assert (n_jobs, n_archived) == (1, 1)
    assert len(store["Jobs"]) == 1 and store["Jobs"][0][10] == 90
    assert len(store["Archive"]) == 1 and store["Archive"][0][14] == "Low fit"


def test_known_ids_unions_jobs_and_archive(monkeypatch):
    calls = []

    class FakeGet:
        def __init__(self, values_by_range):
            self.values_by_range = values_by_range

        def get(self, spreadsheetId, range):
            calls.append(range)
            self._r = range
            return self

        def execute(self):
            return {"values": self.values_by_range.get(self._r, [])}

    fake = FakeGet({"Jobs!C2:D": [["AI Engineer", "Acme"]],
                    "Archive!C2:D": [["Data Engineer", "Beta"]]})
    monkeypatch.setattr(sheets, "_svc", lambda creds: type(
        "S", (), {"spreadsheets": lambda self: type(
            "P", (), {"values": lambda self: fake})()})())
    ids = sheets.known_ids(None, "sid")
    assert len(ids) == 2 and "Jobs!C2:D" in calls and "Archive!C2:D" in calls
```

Adjust the fakes to the smallest shape that satisfies `sheets.py` call chains; if `Scored(posting=p)` requires more fields, mirror how `tests/test_scorer.py` builds `Scored`.

- [ ] **Step 2: Run tests, verify they fail**

Run: `python -m pytest tests/test_sheets_archive.py -q`
Expected: FAIL (`append_jobs` lacks `min_fit`, no Archive union).

- [ ] **Step 3: Implement in `sheets.py`**

```python
def ensure_archive_tab(creds, spreadsheet_id: str) -> None:
    """Archive holds aged out, low fit, and dismissed rows. Same columns as Jobs
    so dedup can recompute keys from Title+Company there too."""
    svc = _svc(creds)
    meta = svc.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    titles = {s["properties"]["title"] for s in meta["sheets"]}
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
```

`known_ids`: read both tabs (Archive read wrapped in try/except `HttpError` returning `[]`, so a hand deleted tab degrades instead of crashing; import `from googleapiclient.errors import HttpError`):

```python
def known_ids(creds, spreadsheet_id: str) -> set[str]:
    from jobpilot import dedup

    svc = _svc(creds)

    def _pairs(tab: str) -> list[list[str]]:
        try:
            resp = svc.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id, range=f"{tab}!C2:D").execute()
        except HttpError:
            return []
        return resp.get("values", [])

    return {
        dedup.key(company=row[1], title=row[0])
        for row in _pairs("Jobs") + _pairs("Archive")
        if len(row) >= 2
    }
```

`append_jobs` split (keep the docstring norms of the file):

```python
def append_jobs(creds, spreadsheet_id: str, scored: list[Scored], now: datetime,
                min_fit: int) -> tuple[int, int]:
    """Write fit >= min_fit to Jobs, scored-below rows to Archive as Low fit.
    Unscored rows (fit None) are not written; they retry next run because they
    never enter dedup memory."""
    jobs_rows, archive_rows = [], []
    for s in scored:
        if s.fit_score is None:
            continue
        row = to_row(s, now)
        if s.fit_score >= min_fit:
            jobs_rows.append(row)
        else:
            row[14] = "Low fit"
            row[15] = f"below write threshold {min_fit}"
            archive_rows.append(row)
    svc = _svc(creds)
    for tab, rows in (("Jobs", jobs_rows), ("Archive", archive_rows)):
        if rows:
            svc.spreadsheets().values().append(
                spreadsheetId=spreadsheet_id, range=f"{tab}!A1",
                valueInputOption="USER_ENTERED", insertDataOption="INSERT_ROWS",
                body={"values": rows},
            ).execute()
    return len(jobs_rows), len(archive_rows)
```

`pipeline.py` `run()`: after `sid = sheets.ensure_dashboard(...)` add `sheets.ensure_archive_tab(creds, sid)`. Update the append call site (line 171):

```python
    n_jobs, n_archived = sheets.append_jobs(creds, sid, scored, now,
                                            min_fit=cfg.scoring.threshold)
    notes.append(f"write gate: {n_jobs} to Jobs, {n_archived} archived low fit")
```

Auto reject interplay: sponsorship "unlikely" rows (`to_row` sets Status `Rejected`) should not occupy the Jobs tab either; route them to Archive regardless of fit inside the loop:

```python
        if s.sponsorship_signal == "unlikely" or s.fit_score < min_fit:
            ...archive_rows.append(row)  # keep Status Rejected for sponsorship rows
```

(Only override `row[14]/row[15]` to `Low fit` for the fit case; sponsorship rows keep their `Rejected` status and audit note.)

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest tests/ -q`
Expected: all pass; fix any existing `append_jobs` call sites/tests to the new signature (search: `grep -rn "append_jobs" src/ tests/`).

- [ ] **Step 5: Commit**

```bash
git add src/jobpilot/sheets.py src/jobpilot/pipeline.py tests/test_sheets_archive.py tests/
git commit -m "feat(sheets): Archive tab, dedup union, fit 75 write split"
```

---

### Task 3: Archiver sweep (nightly aging + one time migration path)

**Files:**
- Create: `src/jobpilot/archiver.py`
- Modify: `src/jobpilot/pipeline.py` (wire into full runs), `src/jobpilot/__main__.py` (flag)
- Test: `tests/test_archiver.py` (new)

**Interfaces:**
- Consumes: `sheets._svc`, `sheets.HEADERS`, `cfg.scoring.threshold`, `cfg.caps.board_freshness_days` (14, reused as the visibility window).
- Produces:
  - `archiver.select_archivable(rows: list[list[str]], now: datetime, min_fit: int, max_age_days: int) -> list[tuple[int, str]]` pure function returning (0 based data row index, reason).
  - `archiver.sweep(creds, spreadsheet_id: str, cfg, now) -> list[str]` notes list; moves selected rows to Archive and deletes them from Jobs bottom up, re verifying Job ID before deletion.

- [ ] **Step 1: Write failing tests** (`tests/test_archiver.py`)

```python
from datetime import datetime, timezone

from jobpilot.archiver import select_archivable

NOW = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)
H = {"Date found": 0, "Job ID": 1, "Title": 2, "Company": 3, "Posted": 6,
     "Source": 9, "Fit": 10, "Status": 14, "Applied date": 16, "Last reply": 17}


def _row(status="New", fit="90", posted="2026-07-20 08:00", found="2026-07-20",
         source="greenhouse", applied="", reply=""):
    row = [""] * 28
    row[H["Date found"]], row[H["Job ID"]] = found, "cafe0123deadbeef"
    row[H["Title"]], row[H["Company"]] = "AI Engineer", "Acme"
    row[H["Posted"]], row[H["Source"]], row[H["Fit"]] = posted, source, fit
    row[H["Status"]], row[H["Applied date"]], row[H["Last reply"]] = status, applied, reply
    return row


def test_keeps_fresh_high_fit_new_rows():
    assert select_archivable([_row()], NOW, 75, 14) == []


def test_archives_stale_low_fit_undated_dismissed():
    rows = [
        _row(posted="2026-06-01 08:00"),          # stale
        _row(fit="70"),                            # low fit
        _row(fit="�"),                             # unparseable, counts unscored
        _row(posted=""),                           # undated
        _row(status="Dismissed"),                  # x-ed out
        _row(status="Rejected"),                   # sponsorship auto reject
    ]
    got = select_archivable(rows, NOW, 75, 14)
    assert [i for i, _ in got] == [0, 1, 2, 3, 4, 5]
    assert dict(got)[0] == "stale" and dict(got)[4] == "dismissed"


def test_never_touches_applied_or_replied_rows():
    rows = [
        _row(status="Applied", posted="2026-05-01 08:00", fit="40"),
        _row(status="Interview", posted=""),
        _row(status="Rejected", applied="2026-07-01"),
        _row(status="New", reply="2026-07-02 09:00", fit="10"),
    ]
    assert select_archivable(rows, NOW, 75, 14) == []


def test_manual_rows_exempt_from_fit_and_date_until_aged():
    fresh = _row(source="manual", fit="—", posted="", found="2026-07-20")
    aged = _row(source="manual", fit="—", posted="", found="2026-06-20")
    got = select_archivable([fresh, aged], NOW, 75, 14)
    assert got == [(1, "manual aged out")]
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `python -m pytest tests/test_archiver.py -q`
Expected: `ModuleNotFoundError: jobpilot.archiver`.

- [ ] **Step 3: Implement `src/jobpilot/archiver.py`**

```python
"""Move aged out, low fit, and dismissed Jobs rows to the Archive tab.

Archive preserves Title+Company, so dedup keeps recognizing these jobs and a
swept row can never re enter the console. Rows the owner acted on (applied,
any reply, any advanced status) are never touched.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jobpilot.sheets import HEADERS, LAST_COL, _svc

_IDX = {name: i for i, name in enumerate(HEADERS)}
_PROTECTED = {"Applied", "Outreach sent", "Response", "Interview", "Offer"}


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


def sweep(creds, spreadsheet_id: str, cfg, now: datetime) -> list[str]:
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

    # Re verify ids straight before deleting: a concurrent append cannot shift
    # existing row indexes, but a concurrent manual edit could.
    check = svc.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range="Jobs!B2:B").execute().get("values", [])
    stale_check = [
        i for i, _ in picks
        if i >= len(check) or (check[i][0] if check[i] else "") != _cell(rows[i], "Job ID")
    ]
    if stale_check:
        return [f"archive sweep: aborted delete, sheet changed under us "
                f"({len(stale_check)} mismatches); rows copied to Archive, "
                f"next sweep will retry"]

    jobs_sheet_id = 0  # Jobs is sheetId 0 (created first, sheets.py ensure_dashboard)
    requests = [
        {"deleteDimension": {"range": {
            "sheetId": jobs_sheet_id, "dimension": "ROWS",
            "startIndex": i + 1, "endIndex": i + 2}}}
        for i, _ in sorted(picks, key=lambda t: t[0], reverse=True)
    ]
    svc.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id, body={"requests": requests}).execute()

    reasons: dict[str, int] = {}
    for _, r in picks:
        reasons[r] = reasons.get(r, 0) + 1
    detail = ", ".join(f"{v} {k}" for k, v in sorted(reasons.items()))
    return [f"archive sweep: moved {len(picks)} rows ({detail})"]
```

Note on the duplicate risk: rows are appended to Archive before the delete verification, so an aborted delete leaves the row in both tabs until the next sweep succeeds; dedup is a set union, so this is harmless. The next successful sweep re moves the Jobs copy; Archive may hold a duplicate row, which is acceptable (Archive is memory, not a view).
Resolve `jobs_sheet_id` properly: read the spreadsheet meta once and find the sheetId whose title is `Jobs` instead of assuming 0:

```python
    meta = svc.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    jobs_sheet_id = next(s["properties"]["sheetId"] for s in meta["sheets"]
                         if s["properties"]["title"] == "Jobs")
```

Wire into `pipeline.py` `run()` right after the inbox watch block and BEFORE the `if fast:` return (sweep runs on full runs only):

```python
    if not fast:
        from jobpilot import archiver
        notes.extend(archiver.sweep(creds, sid, cfg, now))
```

Add the CLI flag in `src/jobpilot/__main__.py` following the existing flag pattern there (read the file first; it already has flags like `--tailor-job`):

```python
    parser.add_argument("--archive-sweep", action="store_true",
                        help="run only the archive sweep against the sheet")
```

and in the dispatch section:

```python
    if args.archive_sweep:
        from jobpilot import archiver, sheets
        from jobpilot.gauth import credentials
        creds = credentials()
        sid = os.environ.get("JOBPILOT_SPREADSHEET_ID") or cfg.sheet.spreadsheet_id
        sheets.ensure_archive_tab(creds, sid)
        for note in archiver.sweep(creds, sid, cfg, datetime.now(timezone.utc)):
            print(note)
        return
```

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/jobpilot/archiver.py src/jobpilot/pipeline.py src/jobpilot/__main__.py tests/test_archiver.py
git commit -m "feat(archiver): sweep stale, low fit, dismissed rows to Archive"
```

---

### Task 4: Thresholds to 75 and Stats repair

**Files:**
- Modify: `src/jobpilot/config.py:39,45`
- Modify: `src/jobpilot/sheets.py:36-47` (STATS_ROWS) + new `refresh_stats`
- Modify: `src/jobpilot/pipeline.py` (call refresh_stats in full runs)
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `Scoring.threshold` default 75, `Tailoring.auto_threshold` default 75, `sheets.refresh_stats(creds, spreadsheet_id) -> None` idempotently rewriting `Stats!A1`.

- [ ] **Step 1: Write failing test** (append to `tests/test_config.py`)

```python
def test_default_thresholds_are_75():
    from jobpilot.config import Scoring, Tailoring
    assert Scoring().threshold == 75
    assert Tailoring().auto_threshold == 75
```

- [ ] **Step 2: Run, verify fails**: `python -m pytest tests/test_config.py -q` (60 != 75).

- [ ] **Step 3: Implement**

`config.py`: `threshold: int = 75`, `auto_threshold: int = 75` (keep comments, update numbers). `sheets.py` STATS_ROWS: lifetime counts include Archive, active counts stay Jobs only:

```python
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


def refresh_stats(creds, spreadsheet_id: str) -> None:
    """Rewrite the Stats formulas; the live tab has decayed to literal zeros."""
    _svc(creds).spreadsheets().values().update(
        spreadsheetId=spreadsheet_id, range="Stats!A1",
        valueInputOption="USER_ENTERED", body={"values": STATS_ROWS},
    ).execute()
```

`pipeline.py` full run (next to the archiver wiring): `sheets.refresh_stats(creds, sid)`.

- [ ] **Step 4: Full suite**: `python -m pytest tests/ -q`. Existing tests asserting 60 thresholds must be updated to 75 (they encode the old default, spec supersedes).

- [ ] **Step 5: Commit**

```bash
git add src/jobpilot/config.py src/jobpilot/sheets.py src/jobpilot/pipeline.py tests/
git commit -m "feat(config): fit thresholds to 75; repair and archive-count stats"
```

---

### Task 5: Single AIE master resume base

**Files:**
- Modify: `src/jobpilot/tailor.py:58-65,123-127` (base selection), `src/jobpilot/rebuild.py` (AIE only guard)
- Modify (untracked, private): `private/Sampreeth_Avvari_AIE.tex` on the owner machine
- Test: `tests/test_tailor.py`

**Interfaces:**
- Produces: `_resume_tex() -> str` (no variant parameter) reading env `RESUME_TEX_AIE` else `RESUME_DIR / "resume_AIE.tex"`. `tailor_row` uses the AIE base and `KEYWORDS["AIE"]` for every job while still labeling reports with the scorer's variant string.

- [ ] **Step 1: Write failing test** (append to `tests/test_tailor.py`, reuse its fixtures)

```python
def test_tailor_base_is_always_aie(monkeypatch):
    from jobpilot import tailor
    monkeypatch.setenv("RESUME_TEX_AIE", "AIE MASTER CONTENT")
    monkeypatch.setenv("RESUME_TEX_FDE", "FDE CONTENT")
    prompt = tailor._build_prompt("Acme", "Platform Engineer", "jd text", "FDE")
    assert "AIE MASTER CONTENT" in prompt and "FDE CONTENT" not in prompt
```

- [ ] **Step 2: Run, verify fails**: `python -m pytest tests/test_tailor.py -q -k aie`.

- [ ] **Step 3: Implement**

`tailor.py` `_resume_tex`: ignore the caller's variant for base selection (keep the parameter so call sites stay stable, document why):

```python
def _resume_tex(variant: str) -> str:
    """Every tailored resume derives from the single AIE master (owner decision,
    2026-07-23 spec). The variant argument survives only as a report label."""
    env = os.environ.get("RESUME_TEX_AIE")
    if env:
        return env
    return (RESUME_DIR / VARIANT_FILES["AIE"]).read_text(encoding="utf-8")
```

In `tailor_row` (line 127 area) keep `variant = row.get("Resume variant") or "FDE"` for labels, but change the keywords lookup (line 161) to `KEYWORDS["AIE"]`. In `rebuild.py`, guard non AIE variants at the top of `rebuild_master`:

```python
    if variant != "AIE":
        return f"rebuild skipped: single master mode, only AIE is maintained (got {variant})"
```

- [ ] **Step 4: Full suite**: `python -m pytest tests/ -q`.

- [ ] **Step 5: Owner machine, private files (NOT committed):** copy the master into the private base and compile gate it. From repo root:

```powershell
Copy-Item "..\..\resume-latex\resume_AIE_reallinks.tex" private\resume_AIE_source.tex
# Merge: private/Sampreeth_Avvari_AIE.tex gets the reallinks CONTENT while keeping
# the pipeline compatible preamble input (_preamble). The reallinks file inputs
# `preamble` from resume-latex; port the AIE only overrides (helvet, linkblue,
# bltag macro, itemize spacing) into the document prologue after \input{_preamble}.
```

Then verify (pipeline uses pdflatex; `scripts/ats_check.py` gates 1 page + keywords):

```powershell
python scripts/ats_check.py private/Sampreeth_Avvari_AIE.tex --variant AIE
```

(Read `scripts/ats_check.py` first for its real CLI; if it takes a PDF, compile with the same routine as `latexpdf.py` first.) Expected: 1 page, keyword coverage >= 85 percent. This step produces no tracked changes; the Secret Manager update happens in Task 18.

- [ ] **Step 6: Commit (code only)**

```bash
git add src/jobpilot/tailor.py src/jobpilot/rebuild.py tests/test_tailor.py
git commit -m "feat(tailor): single AIE master base for every tailored resume"
```

---

### Task 6: UI foundation, light premium tokens + shell

**Files:**
- Modify: `ui/src/app/globals.css` (full rewrite), `ui/src/app/layout.tsx`, `ui/src/components/nav.tsx`
- Create: `ui/src/components/mobile-nav.tsx`

**Interfaces:**
- Produces: CSS tokens and classes every later task uses: `--bg #FBFBFD`, `--surface #FFFFFF`, `--ink #1D1D1F`, `--ink-70/55/35/10` rgba tiers, `--blue #0066CC`, `--blue-hover #0055AA`, `--emerald #059669`, `--emerald-soft #D1FAE5`, `--violet #7C3AED`, `--violet-soft #EDE9FE`, `--amber #B45309`, `--amber-soft #FEF3C7`, `--rose #BE123C`, `--rose-soft #FFE4E6`, shadows `--shadow-sm/md/lg`, radii `--r-md 12px`, `--r-lg 16px`. Classes `.card`, `.eyebrow`, `.btn`, `.btn-primary`, `.btn-ghost`, `.btn-danger`, `.pill`, `.pill-{new,applied,outreach,response,interview,offer,rejected,dismissed}`, `.input`. Fonts: `--font-archivo` (display), `--font-inter` (body), `--font-plex-mono` (numeric).
- Consumes: nothing (first UI task).

- [ ] **Step 1: Load the frontend-design skill**, then rewrite `ui/src/app/globals.css`:

```css
@import "tailwindcss";

:root {
  --bg: #fbfbfd;
  --surface: #ffffff;
  --surface-2: #f4f5f8;
  --ink: #1d1d1f;
  --ink-70: rgba(29, 29, 31, 0.72);
  --ink-55: rgba(29, 29, 31, 0.55);
  --ink-35: rgba(29, 29, 31, 0.36);
  --ink-10: rgba(29, 29, 31, 0.1);
  --line: rgba(29, 29, 31, 0.08);
  --blue: #0066cc;
  --blue-hover: #0055aa;
  --blue-soft: #e8f1fb;
  --emerald: #059669;
  --emerald-soft: #d1fae5;
  --violet: #7c3aed;
  --violet-soft: #ede9fe;
  --amber: #b45309;
  --amber-soft: #fef3c7;
  --rose: #be123c;
  --rose-soft: #ffe4e6;
  --shadow-sm: 0 1px 2px rgba(29, 29, 31, 0.06);
  --shadow-md: 0 1px 2px rgba(29, 29, 31, 0.05), 0 6px 18px rgba(29, 29, 31, 0.07);
  --shadow-lg: 0 2px 6px rgba(29, 29, 31, 0.06), 0 18px 44px rgba(29, 29, 31, 0.12);
  --r-md: 12px;
  --r-lg: 16px;
}

@theme inline {
  --font-sans: var(--font-inter);
  --font-display: var(--font-archivo);
  --font-mono: var(--font-plex-mono);
}

html { color-scheme: light; }

body {
  background: var(--bg);
  color: var(--ink);
  font-family: var(--font-inter), system-ui, sans-serif;
  font-size: 14px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}

.card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-sm);
  transition: box-shadow 160ms ease, transform 160ms ease, border-color 160ms ease;
}
.card-hover:hover { box-shadow: var(--shadow-md); border-color: var(--ink-10); }

.eyebrow {
  font-family: var(--font-archivo), sans-serif;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ink-55);
}

.btn {
  display: inline-flex; align-items: center; gap: 6px;
  height: 34px; padding: 0 14px;
  border-radius: 10px; font-size: 13px; font-weight: 550;
  border: 1px solid transparent; cursor: pointer;
  transition: background 140ms ease, border-color 140ms ease, color 140ms ease;
}
.btn-sm { height: 28px; padding: 0 10px; font-size: 12px; border-radius: 8px; }
.btn-primary { background: var(--blue); color: #fff; }
.btn-primary:hover { background: var(--blue-hover); }
.btn-ghost { background: transparent; color: var(--ink-70); border-color: var(--line); }
.btn-ghost:hover { background: var(--surface-2); color: var(--ink); }
.btn-danger { background: transparent; color: var(--rose); border-color: transparent; }
.btn-danger:hover { background: var(--rose-soft); }

.input {
  height: 34px; padding: 0 12px; font-size: 13px;
  background: var(--surface); color: var(--ink);
  border: 1px solid var(--line); border-radius: 10px;
}
.input:focus { outline: 2px solid var(--blue-soft); border-color: var(--blue); }

.pill {
  display: inline-flex; align-items: center; gap: 5px;
  height: 22px; padding: 0 9px; border-radius: 999px;
  font-size: 11.5px; font-weight: 550;
}
.pill-new { background: var(--blue-soft); color: var(--blue); }
.pill-applied { background: var(--violet-soft); color: var(--violet); }
.pill-outreach { background: var(--violet-soft); color: var(--violet); }
.pill-response { background: var(--amber-soft); color: var(--amber); }
.pill-interview { background: var(--emerald-soft); color: var(--emerald); }
.pill-offer { background: var(--emerald-soft); color: var(--emerald); }
.pill-rejected { background: var(--surface-2); color: var(--ink-55); }
.pill-dismissed { background: var(--surface-2); color: var(--ink-55); }

.navlink {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 12px; border-radius: 10px;
  font-size: 13px; color: var(--ink-70);
}
.navlink:hover { background: var(--surface-2); color: var(--ink); }
.navlink.active { background: var(--blue-soft); color: var(--blue); font-weight: 600; }

.rise { animation: rise 240ms ease both; }
@keyframes rise { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; } }
.blink { animation: blink 1.1s ease-in-out infinite; }
@keyframes blink { 50% { opacity: 0.45; } }
```

Delete every dark token, the grain overlay, `.panel`, `.console-table`, `.btn-amber`, and the old pill set. Anything still referencing them will surface as visibly unstyled during Tasks 9 to 16, and the Task 17 grep gate catches leftovers.

- [ ] **Step 2: `layout.tsx`**: add Inter to the font imports (keep Archivo + IBM Plex Mono):

```tsx
import { Archivo, IBM_Plex_Mono, Inter } from "next/font/google";
const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
```

Add `inter.variable` to the `<html>` className. Keep the sidebar for `md:` and up (restyle: `border-r border-[var(--line)] bg-[var(--surface)]`), keep the sticky header (white, `border-b border-[var(--line)]`, no backdrop blur needed on light), and mount `<MobileNav />` after `<main>`.

- [ ] **Step 3: Create `ui/src/components/mobile-nav.tsx`** (bottom tab bar below `md`; 5 primary tabs + More sheet is overkill, use scrollable row):

```tsx
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/", label: "Home" },
  { href: "/jobs", label: "Jobs" },
  { href: "/applied", label: "Applied" },
  { href: "/companies", label: "Companies" },
  { href: "/replies", label: "Replies" },
  { href: "/outreach", label: "Outreach" },
  { href: "/assistant", label: "Assistant" },
];

export default function MobileNav() {
  const path = usePathname();
  return (
    <nav className="fixed inset-x-0 bottom-0 z-40 flex gap-1 overflow-x-auto border-t bg-[var(--surface)] px-2 py-2 md:hidden"
         style={{ borderColor: "var(--line)" }}>
      {TABS.map((t) => {
        const active = t.href === "/" ? path === "/" : path.startsWith(t.href);
        return (
          <Link key={t.href} href={t.href}
                className={`navlink whitespace-nowrap ${active ? "active" : ""}`}>
            {t.label}
          </Link>
        );
      })}
    </nav>
  );
}
```

Give `<main>` bottom padding (`pb-20 md:pb-6`) so the bar never covers content.

- [ ] **Step 4: Restyle `nav.tsx`** to the new `.navlink` (it already uses it; verify the applied badge reads `background: var(--blue-soft); color: var(--blue)`), swap glyphs for clean text labels with a small mono glyph prefix if it looks good under frontend-design judgment.

- [ ] **Step 5: Verify**: `cd ui && npm run build && npm run lint`. Expected: compiles; pages will look partially unstyled until their tasks land (old class names render as plain text blocks, acceptable mid branch). Run `npm run dev` and confirm the shell, fonts, sidebar, and mobile bar render light and aligned.

- [ ] **Step 6: Commit**

```bash
git add ui/src/app/globals.css ui/src/app/layout.tsx ui/src/components/nav.tsx ui/src/components/mobile-nav.tsx
git commit -m "feat(ui): light premium token system, Inter body, mobile bottom nav"
```

---

### Task 7: Shared primitives (components/ui)

**Files:**
- Create: `ui/src/components/ui/button.tsx`, `card.tsx`, `modal.tsx`, `badge.tsx`, `fit-ring.tsx`, `skeleton.tsx`, `empty-state.tsx`, `toast.tsx`, `filter-bar.tsx`
- Modify: `ui/src/components/status.tsx` (map pills to new classes; `Dismissed` gets `pill-dismissed`, fixing the old bug where it rendered as `pill-new`)

**Interfaces (later tasks import exactly these):**
- `Button({ variant?: "primary"|"ghost"|"danger", size?: "md"|"sm", busy?: boolean, ...buttonProps })`
- `Card({ className?, children, onClick? })` renders `.card` div
- `Modal({ open, onClose, width?, children })` single portal implementation, Esc closes, click outside closes
- `Badge({ tone: "blue"|"emerald"|"violet"|"amber"|"rose"|"neutral", children })`
- `FitRing({ fit: number|null, size?: number })` SVG ring, emerald >= 85, blue >= 75, amber below, faint dash for null
- `Skeleton({ className })`, `EmptyState({ title, hint?, action? })`
- `useToast()` + `<ToastHost/>`: `toast({ message, actionLabel?, onAction?, ttlMs? })`
- `FilterBar({ children })` horizontal wrap row; plus `Segmented({ value, onChange, options: {value,label}[] })`

- [ ] **Step 1: Implement all nine files.** Complete code for the two nontrivial ones; the rest follow the same idiom (typed props, token classes, no inline hex):

`fit-ring.tsx`:

```tsx
"use client";

export default function FitRing({ fit, size = 44 }: { fit: number | null; size?: number }) {
  const r = (size - 6) / 2;
  const c = 2 * Math.PI * r;
  const pct = fit === null ? 0 : Math.max(0, Math.min(100, fit));
  const tone = fit === null ? "var(--ink-10)"
    : fit >= 85 ? "var(--emerald)" : fit >= 75 ? "var(--blue)" : "var(--amber)";
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}
         title={fit === null ? "not scored" : `fit ${fit}`}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none"
                stroke="var(--ink-10)" strokeWidth={4} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={tone}
                strokeWidth={4} strokeLinecap="round"
                strokeDasharray={`${(pct / 100) * c} ${c}`} />
      </svg>
      <span className="absolute inset-0 grid place-items-center font-semibold"
            style={{ fontFamily: "var(--font-plex-mono)", fontSize: size * 0.3, color: tone }}>
        {fit === null ? "·" : fit}
      </span>
    </div>
  );
}
```

`toast.tsx` (context + host; one toast at a time is enough):

```tsx
"use client";

import { createContext, useCallback, useContext, useRef, useState } from "react";

type Toast = { message: string; actionLabel?: string; onAction?: () => void; ttlMs?: number };
const ToastCtx = createContext<(t: Toast) => void>(() => {});
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toast, setToast] = useState<Toast | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const show = useCallback((t: Toast) => {
    if (timer.current) clearTimeout(timer.current);
    setToast(t);
    timer.current = setTimeout(() => setToast(null), t.ttlMs ?? 6000);
  }, []);
  return (
    <ToastCtx.Provider value={show}>
      {children}
      {toast && (
        <div className="card rise fixed bottom-20 left-1/2 z-50 flex -translate-x-1/2 items-center gap-3 px-4 py-3 md:bottom-6"
             style={{ boxShadow: "var(--shadow-lg)" }}>
          <span className="text-[13px]">{toast.message}</span>
          {toast.actionLabel && (
            <button className="btn btn-sm btn-ghost font-semibold" style={{ color: "var(--blue)" }}
                    onClick={() => { toast.onAction?.(); setToast(null); }}>
              {toast.actionLabel}
            </button>
          )}
        </div>
      )}
    </ToastCtx.Provider>
  );
}
```

`modal.tsx` must be the single portal implementation (createPortal to document.body, fixed overlay `rgba(29,29,31,0.32)`, `.card` panel with `--shadow-lg`, `width: min(<width>, 94vw)`, Esc listener). `button.tsx` maps variants to `.btn .btn-primary|ghost|danger` and `busy` renders a `.blink` dot plus disabled. `badge.tsx` maps tones to the soft token pairs. `skeleton.tsx` renders `animate-pulse rounded-md` with `background: var(--surface-2)`. `empty-state.tsx` renders a centered `.card` with title, hint, and optional action node. `filter-bar.tsx` renders `flex flex-wrap items-center gap-2`; `Segmented` renders a `.card` row of `.btn-sm` buttons where the active one gets `background: var(--blue-soft); color: var(--blue)`.

Mount `<ToastProvider>` inside `layout.tsx` wrapping `{children}`.

- [ ] **Step 2: Update `status.tsx`**: `statusPillClass` maps every status to its own pill class (`Dismissed` to `pill-dismissed`, `Outreach sent` to `pill-outreach`); keep `FitMeter` exported but mark it legacy (Task 9 removes its last usage; delete it in Task 16 cleanup).

- [ ] **Step 3: Verify**: `cd ui && npm run build && npm run lint`. Expected: clean build (primitives compile even while unused).

- [ ] **Step 4: Commit**

```bash
git add ui/src/components/ui/ ui/src/components/status.tsx ui/src/app/layout.tsx
git commit -m "feat(ui): shared primitives: button, card, modal, fit ring, toast, filters"
```

---

### Task 8: Jobs store and lib consolidation (fit 75, effective recency)

**Files:**
- Create: `ui/src/components/jobs-store.tsx`
- Modify: `ui/src/lib/company-match.ts` (MIN_FIT 75, effectiveRecency, manual pass rule), `ui/src/lib/types.ts` (remove RESUME_VARIANTS), `ui/src/app/page.tsx:8-9,37-40` (use shared sets + 75 gate)
- Test: none (no UI test infra); verification is build + behavior in Task 9

**Interfaces:**
- Produces:
  - `JobsProvider({ initial, children })` + `useJobs()` returning `{ jobs, refresh(), mutate(row, local, sheet), busyTailor: Set<number>, busyDraft: Set<number>, markBusy(kind, row), pollUntil(row, col, predicate) }`. `mutate` is optimistic with revert on POST failure (port the exact logic from `jobs-table.tsx:159-167` and `pushUpdate` from `:15-22`).
  - `company-match.ts`: `MIN_FIT = 75`; `passesFit(j: Job, minFit: number): boolean` returning `j.fit === null ? j.source === "manual" : j.fit >= minFit`; `effectiveRecency(j: Job): number` returning `postedTs(j.posted) ?? (j.source === "manual" ? Date.parse(j.dateFound) : 0)`; `isRemaining` switches to `passesFit(j, MIN_FIT)`.
- Consumes: `Job` type, `/api/jobs`, `/api/jobs/update`.

- [ ] **Step 1: Implement `company-match.ts` changes** (exact):

```ts
/** Console wide relevance gate: below 75 is archived server side; the UI
 *  enforces the same floor so legacy rows behave until migration runs. */
export const MIN_FIT = 75;

/** Unscored rows pass only when the owner added them by hand. */
export function passesFit(j: Job, minFit: number): boolean {
  if (j.fit === null) return j.source === "manual";
  return j.fit >= minFit;
}

/** Sort key: real posted time when known; manual rows fall back to the day
 *  the owner added them; anything else sinks. */
export function effectiveRecency(j: Job): number {
  const p = postedTs(j.posted);
  if (p !== null) return p;
  if (j.source === "manual") {
    const t = Date.parse(j.dateFound);
    return Number.isNaN(t) ? 0 : t;
  }
  return 0;
}
```

Update `isRemaining` to `passesFit(j, MIN_FIT)` in place of its inline fit check.

- [ ] **Step 2: Create `ui/src/lib/update.ts`** holding the one true `pushUpdate` (ported from `jobs-table.tsx:15-22`); the store and, later, replies-view (Task 13) import it:

```ts
export async function pushUpdate(row: number, updates: Record<string, string>) {
  const res = await fetch("/api/jobs/update", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ row, updates }),
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({})))?.error || "update failed");
}
```

(Match the exact behavior of the current copy when porting; if it differs from this sketch, the current copy wins.) Then implement `jobs-store.tsx` ("use client"; context provider; `refresh` fetches `/api/jobs` and replaces state; one `setInterval(refresh, 60000)`; `pollUntil(row, col, predicate)` re-fetches every 15s up to 4 minutes for tailor/draft flows, ported from `jobs-table.tsx:60-89`; `mutate` exactly ports the optimistic pattern and calls `pushUpdate`). Export a `useJobsOptional()` that returns null outside the provider so `nav.tsx` can reuse it without breaking on non job pages; keep nav's own fetch as fallback.

- [ ] **Step 3: `types.ts`**: delete `RESUME_VARIANTS` (single master now; the role filter stays on `ROLES`). Fix the stale header comment while in the file (says A..S, is A..AB). Search usages: `grep -rn "RESUME_VARIANTS" ui/src` and remove the jobs table resume filter usage (that component is rebuilt in Task 9 anyway; keep the tree compiling by removing the import/filter in the same commit).

- [ ] **Step 4: `app/page.tsx`**: replace the local `ADVANCED`/`RESPONDED` sets with imports from `lib/status-sets.ts`; change the top matches gate from `fit >= 60` to `passesFit(j, MIN_FIT)` and sort by `effectiveRecency` desc as tiebreak after fit.

- [ ] **Step 5: Verify**: `cd ui && npm run build && npm run lint` clean.

- [ ] **Step 6: Commit**

```bash
git add ui/src/components/jobs-store.tsx ui/src/lib/ ui/src/app/page.tsx
git commit -m "feat(ui): shared jobs store; fit gate 75; effective recency sort key"
```

---

### Task 9: Job cards (read layer of the centerpiece)

**Files:**
- Create: `ui/src/components/job-card.tsx`
- Create: `ui/src/components/jobs-view.tsx` (grid + filter bar, replaces jobs-table rendering; interactions land in Task 10)
- Modify: `ui/src/app/jobs/page.tsx`, `ui/src/app/applied/page.tsx`, `ui/src/app/companies/[name]/page.tsx` (render `<JobsView>` inside `<JobsProvider>`)

**Interfaces:**
- Consumes: `useJobs()`, `passesFit`, `effectiveRecency`, `liveAge`, primitives from Task 7.
- Produces: `JobCard({ job, mode, onDismiss, onApply, onTailor, onDraft, onAsk, onStatus })` and `JobsView({ mode, defaultStatus?, initialJobs, resumeLinks?, companyFilter? })`. Task 10 fills the handlers; this task wires layout, filters, sort, and empty/loading states with handlers as props.

- [ ] **Step 1: Load frontend-design skill, implement `job-card.tsx`.** Structure (complete the JSX with token classes only):

```tsx
"use client";

import FitRing from "./ui/fit-ring";
import { StatusPill } from "./status";
import { liveAge } from "@/lib/company-match";
import type { Job } from "@/lib/types";

export default function JobCard({ job, mode, onDismiss, onApply, onTailor, onDraft, onAsk, onStatus, busyTailor, busyDraft }: JobCardProps) {
  const fresh = /* posted within 24h via postedTs */ false;
  return (
    <article className="card card-hover rise relative flex flex-col gap-3 p-5">
      <button aria-label="dismiss this job forever" onClick={() => onDismiss(job)}
              className="absolute right-3 top-3 grid h-7 w-7 place-items-center rounded-full text-[15px]"
              style={{ color: "var(--ink-35)" }}>
        ✕
      </button>
      <header className="flex items-start gap-3 pr-8">
        <FitRing fit={job.fit} />
        <div className="min-w-0">
          <p className="eyebrow">{job.company}</p>
          <h3 className="truncate font-semibold" style={{ fontFamily: "var(--font-archivo)", fontSize: 16 }}>
            {job.title}
          </h3>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[12px]" style={{ color: "var(--ink-55)" }}>
            <span>{liveAge(job.posted) || "seen " + job.dateFound}</span>
            {fresh && <span className="pill pill-new">new</span>}
            <span>{job.location}</span>
            {job.remote === "yes" && <span>remote</span>}
            <span>{job.source}</span>
          </p>
        </div>
      </header>
      {job.why && <p className="text-[13px] leading-relaxed" style={{ color: "var(--ink-70)" }}>{job.why}</p>}
      {/* docs row: tailored resume link, cover letter, ATS badge when present */}
      {/* footer: Apply primary button, Tailor / Draft / Ask ghost buttons, status pill or menu */}
    </article>
  );
}
```

Card requirements: dismiss ✕ only when `!isApplied(job.status)`; sponsorship shows a small amber Badge when `job.sponsorship === "unlikely"` is not possible (those are archived) but "unclear" gets a neutral badge; the docs row reuses `AtsBadge` from `ats-report.tsx` unchanged; hovering the card raises it (`.card-hover`).

- [ ] **Step 2: Implement `jobs-view.tsx`.** Port the `visible` memo logic from `jobs-table.tsx:119-157` with these changes: default `minFit = MIN_FIT` (75) in open mode; fit options `[0, 60, 70, 75, 80, 90]`; `postedWithin` options `[24, 72, 168, 336, 0]` labeled `24h / 3d / 7d / 14d / all`, default `336`; default sort `effectiveRecency` desc (label "recent"), options recent / best fit / newest found; remove the resume variant filter; keep search, status, source, role, size filters on `FilterBar` + `Segmented` + `.input`. Grid: `grid gap-4 sm:grid-cols-2 xl:grid-cols-3`. Empty state via `EmptyState` ("No jobs match. Fresh postings land every 30 minutes."). Loading skeletons: 6 `Skeleton` cards when `jobs.length === 0 && !loaded`.

- [ ] **Step 3: Wire pages.** Each server page keeps its data fetch and renders:

```tsx
<JobsProvider initial={jobs}>
  <JobsView mode="open" resumeLinks={links} />
</JobsProvider>
```

`/companies/[name]` passes `companyFilter={params.name}` and `JobsView` applies the existing alias match from `company-match.ts` (`jobsForCompany`). `/applied` uses `mode="applied"` (sort by `appliedDate || dateFound` desc, no fit floor, statuses from APPLIED_SET plus Rejected filter option, exactly the semantics ported from `jobs-table.tsx`).

- [ ] **Step 4: Verify**: `npm run build && npm run lint`; `npm run dev`, open `/jobs`: cards render, filters filter, sort orders by real posted age, X and Apply render (handlers stubbed as props defaulting to no ops this task). Old `jobs-table.tsx` is now unimported; leave the file, Task 16 deletes it.

- [ ] **Step 5: Commit**

```bash
git add ui/src/components/job-card.tsx ui/src/components/jobs-view.tsx ui/src/app/jobs/ ui/src/app/applied/ ui/src/app/companies/
git commit -m "feat(ui): job cards grid with fresh-first defaults (75 fit, 14 days, posted sort)"
```

---

### Task 10: Job card interactions (dismiss undo, apply, tailor, draft, ask, status)

**Files:**
- Modify: `ui/src/components/jobs-view.tsx`, `ui/src/components/job-card.tsx`
- Consult (port from): `ui/src/components/jobs-table.tsx:60-112,159-188,341-431,452-495`

**Interfaces:**
- Consumes: `useJobs().mutate/pollUntil/markBusy`, `useToast`, `Modal`, `/api/tailor`, `/api/outreach`, `AssistantDrawer`.
- Produces: fully interactive Jobs/Applied/company views; `jobs-table.tsx` has zero remaining importers.

- [ ] **Step 1: Dismiss with undo.** In `jobs-view.tsx`:

```tsx
const toast = useToast();
function dismiss(job: Job) {
  const prev = job.status;
  mutate(job.row, { status: "Dismissed" }, { Status: "Dismissed", Notes: "dismissed: not relevant" });
  toast({
    message: `Dismissed ${job.company}. It will not come back.`,
    actionLabel: "Undo",
    onAction: () => mutate(job.row, { status: prev }, { Status: prev, Notes: "" }),
  });
}
```

Dismissed cards leave the grid instantly (the `visible` memo already excludes Dismissed in "all"/"New" views).

- [ ] **Step 2: Apply flow.** Port `openPosting` + focus listener + confirm modal from `jobs-table.tsx:102-112,452-495` into `jobs-view.tsx` using `Modal` + `Button`. On confirm: `mutate(row, { status: "Applied", appliedDate: today }, { Status: "Applied", "Applied date": today })`. Modal copy: title "Did you apply to {company}?", buttons "Yes, applied" (primary) / "Not yet" (ghost).

- [ ] **Step 3: Tailor and Draft.** Port `analyze`/`draftOutreach` (`jobs-table.tsx:341-382`): POST then `markBusy("tailor", row)` and `pollUntil(row, "tailoredResume", changed)`; busy state renders the card's Tailor button with `busy` prop (blink). Draft same via `/api/outreach` and `draft` column. Failure values starting `FAILED:` render a rose Badge with the reason on hover and a retry button (existing semantics).

- [ ] **Step 4: Ask drawer + status menu.** 💬 opens `AssistantDrawer` keyed by job id (reuse component untouched). Status: compact `<select className="input btn-sm">` with all STATUSES (ports `setStatusManual` including the applied date stamp).

- [ ] **Step 5: Verify end to end on dev server** against the live Sheet: dismiss a junk row, undo it, dismiss again (stays gone after manual refresh); apply flow stamps status + date; tailor on one already tailored row (poll resolves on value change); ask drawer opens with JD. Then `npm run build && npm run lint`.

- [ ] **Step 6: Commit**

```bash
git add ui/src/components/
git commit -m "feat(ui): card actions: dismiss with undo, apply confirm, tailor, draft, ask"
```

---

### Task 11: Dashboard rebuild

**Files:**
- Modify: `ui/src/app/page.tsx`

**Interfaces:** consumes primitives, `passesFit`, `effectiveRecency`, `JobCard` (compact variant via props it already has), `readJobs`, `latestReports`.

- [ ] **Step 1:** Rebuild sections: (a) stat tiles as `.card` (Applied, Responses, Interviews, Response rate, Found this week) using `Card` + `eyebrow` + Archivo number; (b) "Fresh matches" rail: jobs `passesFit && effectiveRecency within 72h`, sorted `effectiveRecency` desc, top 6 rendered as `JobCard` in the grid (wrap the section in `JobsProvider initial` so cards can dismiss/apply from the dashboard too); (c) "Latest replies" `.card` list (port the existing divide-y list, restyle with pills).
- [ ] **Step 2:** Error handling: wrap Sheet reads in try/catch and render `EmptyState` with the error hint instead of throwing (dashboard already catches; keep that and restyle).
- [ ] **Step 3:** Verify dev render + build + lint.
- [ ] **Step 4:** Commit: `git add ui/src/app/page.tsx && git commit -m "feat(ui): dashboard tiles and fresh matches rail"`.

---

### Task 12: Companies as cards

**Files:**
- Modify: `ui/src/components/companies-table.tsx` (rename export to CompaniesView, file to `companies-view.tsx`), `ui/src/app/companies/page.tsx`

**Interfaces:** consumes `Company`, `CompanyJobMeta`, primitives; keeps `/api/companies` contract exactly.

- [ ] **Step 1:** Rename file + component (`git mv ui/src/components/companies-table.tsx ui/src/components/companies-view.tsx`). Keep all state/logic (visible/quiet split, sorts, fresh filter, add/remove) and replace the two `<table>`s with card grids: company card = name (links to drill down), health dot (`background: var(--emerald)` active / `--rose` error / `--ink-35` unsupported / `--amber` else, port `statusColor` L9), newest job live age (emerald text when within 24h), remaining count as a big Archivo number, remove button (`btn-danger btn-sm`, keep `window.confirm`). Quiet companies collapse into a `<details>` with a `.card` summary row ("N quiet companies, still polled").
- [ ] **Step 2:** "+ Watch company" form: `.card` with two `.input`s + `Button` primary; keep POST + refetch logic identical.
- [ ] **Step 3:** Verify dev render (add/remove a test company, confirm drill down link) + build + lint.
- [ ] **Step 4:** Commit: `git add -A ui/src/components ui/src/app/companies && git commit -m "feat(ui): company cards with health, freshness, remaining counts"`.

---

### Task 13: Replies as inbox cards

**Files:**
- Modify: `ui/src/components/replies-table.tsx` (to `replies-view.tsx`), `ui/src/app/replies/page.tsx`

- [ ] **Step 1:** `git mv` to `replies-view.tsx`; keep `CLASS_OPTIONS`, `correction()`, `reclassify()` logic byte for byte (they encode pipeline semantics). Render a single column card list: each card = company + role (link), reply date (mono, `--ink-55`), `StatusPill`, class `<select className="input btn-sm">`. `not_a_reply` still removes the card optimistically. Delete its local `pushUpdate` and import the shared one from `ui/src/lib/update.ts` (created in Task 8).
- [ ] **Step 2:** Verify: reclassify a row and undo it via the dropdown on dev; build + lint.
- [ ] **Step 3:** Commit: `git add -A ui/src && git commit -m "feat(ui): replies inbox cards with shared update helper"`.

---

### Task 14: Outreach as cards

**Files:**
- Modify: `ui/src/components/outreach-console.tsx`, `ui/src/app/outreach/page.tsx`

- [ ] **Step 1:** Keep every piece of polling/batch logic (L36-84) untouched. Restyle: the draft form and batch form become one `.card` header section (inputs + primary Button, busy states via `busy` prop); the results table becomes a card grid: company name, resume variant Badge, status pill (RUNNING blinks amber, done emerald, failed rose), links row (Draft ✉, Cover, Emails found, Find the person, Quick inboxes) as `btn-ghost btn-sm` anchors.
- [ ] **Step 2:** Verify dev render; build + lint. Do NOT trigger a live batch draft (Apollo/Hunter credits); visual check only, plus one GET poll cycle.
- [ ] **Step 3:** Commit: `git add ui/src/components/outreach-console.tsx ui/src/app/outreach && git commit -m "feat(ui): outreach draft cards"`.

---

### Task 15: Resumes page, single master card

**Files:**
- Modify: `ui/src/app/resumes/page.tsx`, `ui/src/components/resume-card.tsx`

- [ ] **Step 1:** The page renders ONE `ResumeCard` (the AIE master) centered at `max-w-2xl`: the card already fits the new system (it was the card prototype); restyle to tokens, keep Download / ATS report / Source Doc / Regenerate + modal. Title copy: "Master resume · AIE". Add a line under the title: "Every tailored resume starts from this master." If `RESUMES_JSON` still lists retired variants at runtime, filter to `variant === "AIE"` in the page so the console is correct before the env cleanup in Task 18.
- [ ] **Step 2:** Verify dev render + build + lint.
- [ ] **Step 3:** Commit: `git add ui/src/app/resumes ui/src/components/resume-card.tsx && git commit -m "feat(ui): single AIE master resume card"`.

---

### Task 16: Assistant restyle, ATS modal retoken, cleanup sweep

**Files:**
- Modify: `ui/src/components/assistant-chat.tsx`, `ui/src/components/assistant-drawer.tsx`, `ui/src/components/ats-report.tsx`, `ui/src/components/refresh-button.tsx`
- Delete: `ui/src/components/jobs-table.tsx`
- Modify: `ui/src/components/status.tsx` (drop FitMeter)

- [ ] **Step 1: Assistant**: keep ALL logic; restyle bubbles (user: `--blue-soft` bg right aligned; model: `.card` left with a 2px `--blue` left border), inputs to `.input`, buttons to `Button`, drawer panel to `.card` with `--shadow-lg`. `ats-report.tsx`: replace hardcoded `#11161c`/`#0e1318` chrome with `Modal` + tokens; score bar colors map to emerald/blue/amber/rose tokens. `refresh-button.tsx`: `Button` ghost with busy blink.
- [ ] **Step 2: Cleanup sweep**: `git rm ui/src/components/jobs-table.tsx`; remove `FitMeter`; then grep gates:

```bash
cd ui
grep -rn "panel\|console-table\|btn-amber\|--ink-2\|#0a0d10\|#0e1318\|#11161c\|ffb000" src/ && echo "LEFTOVERS FOUND" || echo clean
grep -rn "RESUME_VARIANTS\|jobs-table" src/ && echo "LEFTOVERS FOUND" || echo clean
```

Expected: `clean` twice (the grep exits nonzero when nothing matches).

- [ ] **Step 3:** Verify every route on dev (/, /jobs, /applied, /companies, /companies/openai, /replies, /resumes, /outreach, /assistant): light theme everywhere, no dark remnants, no console errors. `npm run build && npm run lint`.
- [ ] **Step 4:** Commit: `git add -A ui/src && git commit -m "feat(ui): assistant and reports on tokens; remove dark remnants and dead code"`.

---

### Task 17: Integration QA gate (stop point for owner review)

**Files:** none created; this is verification.

- [ ] **Step 1: Python**: `python -m pytest tests/ -q` (all green) and `python -m jobpilot --dry-run` (dry run works offline with stub scoring; confirm the freshness note shows the 14d/7d windows and dropped counts).
- [ ] **Step 2: UI**: `cd ui && npm run build && npm run lint` clean; `npm run dev` and walk the click through checklist: jobs default view shows only fit >= 75 posted within 14 days sorted newest posted; X dismiss + undo toast; apply confirm stamps date; each tab renders cards, mobile width shows the bottom bar, no horizontal page scroll at 360px.
- [ ] **Step 3: Data spot check**: run the freshness audit script against the live Sheet and confirm the counts still describe reality (script exists from the design session; re run against the Jobs tab).
- [ ] **Step 4: STOP.** Present localhost to the owner. Nothing is pushed, merged, or deployed until explicit approval. Collect feedback; loop fixes as new commits; only then Task 18.

---

### Task 18: Owner gated rollout (requires explicit go ahead per step)

- [ ] **Step 1: Push branch + merge to master** (auto deploys pipeline job + UI service via WIF):

```bash
git push -u origin redesign/console-cards-freshness
# merge via PR or fast forward per owner preference
```

- [ ] **Step 2: Secrets** (owner runs or approves each):

```bash
# profile.yaml: set scoring.threshold: 75, tailoring.auto_threshold: 75 in private/profile.yaml, then
gcloud secrets versions add JOBPILOT_PROFILE --data-file=private/profile.yaml --project=jobpilot-sva
# new AIE master (after Task 5 compile gate passed)
gcloud secrets versions add RESUME_TEX_AIE --data-file=private/Sampreeth_Avvari_AIE.tex --project=jobpilot-sva
```

- [ ] **Step 3: UI service env**: shrink `RESUMES_JSON` and `RESUME_LINKS` to the single AIE entry (Cloud Run console or `gcloud run services update jobpilot-ui --update-env-vars ...`).
- [ ] **Step 4: One time migration**: `gcloud run jobs execute jobpilot --region us-central1 --args=--archive-sweep --wait` then verify in the Sheet: Jobs tab shrinks to roughly the fresh high fit set plus applied history; Archive holds the backlog; console loads fast and shows only fresh cards.
- [ ] **Step 5: Scheduler verify** (freshness reliability): `gcloud scheduler jobs describe jobpilot-hourly --location us-central1` and confirm the `--sources` arg includes all seven board sources plus adzuna and the free aggregators (docs disagree on this; fix the arg if the deployed list is the short one).
- [ ] **Step 6: Watch one scheduled full run** end to end (logs + Sheet) and confirm: new rows only fit >= 75 within 14 days, sweep note in the digest, stats tab shows real numbers.

---

## Self review

- Spec coverage: freshness gate (T1), write split + Archive + dedup union (T2), sweep + migration (T3), thresholds + stats (T4), single AIE master (T5 + T18), tokens/shell (T6), primitives (T7), store + gates + recency (T8), jobs cards + X + apply (T9 + T10), dashboard (T11), companies (T12), replies (T13), outreach (T14), resumes (T15), assistant + cleanup (T16), verification (T17), rollout + scheduler check (T18). Spec section 7 edge cases: mojibake fit (T3 unscored branch), manual adds (T3 + T8), undo after sweep (toast ttl 6s, sweep cadence hours, no code needed), concurrent sweep (T3 id verify), deleted Archive tab (T2 HttpError fallback).
- Placeholders: none; every code step shows code, every command shows expected outcome.
- Type consistency: `append_jobs(..., min_fit) -> (int, int)` used in T2 pipeline wiring; `passesFit/effectiveRecency` defined T8, consumed T9/T11; `pushUpdate` moves to `lib/update.ts` in T13 and the store imports it (T8 note); primitives named identically across T7 and consumers.
