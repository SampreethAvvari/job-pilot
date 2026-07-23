"""Archiver: select_archivable pure-function contract, plus sweep() move/delete
I/O (docs/superpowers/plans/2026-07-23-console-cards-freshness.md)."""

from __future__ import annotations

from datetime import datetime, timezone

from jobpilot import archiver
from jobpilot.archiver import select_archivable
from tests.test_sources import make_cfg

NOW = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)
H = {"Date found": 0, "Job ID": 1, "Title": 2, "Company": 3, "Posted": 6,
     "Source": 9, "Fit": 10, "Status": 14, "Applied date": 16, "Last reply": 17}


def _row(status="New", fit="90", posted="2026-07-20 08:00", found="2026-07-20",
        source="greenhouse", applied="", reply="", job_id="cafe0123deadbeef"):
    row = [""] * 28
    row[H["Date found"]], row[H["Job ID"]] = found, job_id
    row[H["Title"]], row[H["Company"]] = "AI Engineer", "Acme"
    row[H["Posted"]], row[H["Source"]], row[H["Fit"]] = posted, source, fit
    row[H["Status"]], row[H["Applied date"]], row[H["Last reply"]] = status, applied, reply
    return row


# ---------- select_archivable (pure) ----------


def test_keeps_fresh_high_fit_new_rows():
    assert select_archivable([_row()], NOW, 75, 14) == []


def test_archives_stale_low_fit_undated_dismissed():
    rows = [
        _row(posted="2026-06-01 08:00"),           # stale
        _row(fit="70"),                             # low fit
        _row(fit="�"),                          # unparseable, counts unscored
        _row(posted=""),                            # undated
        _row(status="Dismissed"),                   # x-ed out
        _row(status="Rejected"),                    # sponsorship auto reject
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
    fresh = _row(source="manual", fit="�", posted="", found="2026-07-20")
    aged = _row(source="manual", fit="�", posted="", found="2026-06-20")
    got = select_archivable([fresh, aged], NOW, 75, 14)
    assert got == [(1, "manual aged out")]


# ---------- select_archivable edge cases (empty tab, full _PROTECTED set,
# unknown-status conservative default) ----------


def test_select_archivable_empty_rows_returns_empty():
    assert select_archivable([], NOW, 75, 14) == []


def test_all_protected_statuses_are_never_archived_even_when_stale_and_low_fit():
    # Every _PROTECTED member, each row otherwise maximally archivable (very
    # stale + fit 1) — none may be swept once the owner has acted on the job.
    rows = [_row(status=s, posted="2026-01-01 08:00", fit="1")
            for s in ("Applied", "Outreach sent", "Response", "Interview", "Offer")]
    assert select_archivable(rows, NOW, 75, 14) == []


def test_unknown_status_is_left_alone_conservative_default():
    # "Low fit" (Archive-only status) and any other status this sweep doesn't
    # recognize must be skipped, not archived — conservative default.
    row = _row(status="Low fit", posted="2026-01-01 08:00", fit="1")
    assert select_archivable([row], NOW, 75, 14) == []


# ---------- _delete_ranges (pure) ----------


def test_delete_ranges_single_row():
    assert archiver._delete_ranges([5]) == [(6, 7)]


def test_delete_ranges_one_long_contiguous_run_becomes_one_range():
    assert archiver._delete_ranges([0, 1, 2, 3, 4]) == [(1, 6)]


def test_delete_ranges_mixed_runs_and_singletons_emit_descending():
    # The reviewer's own example: a contiguous run [1,2,3] plus a singleton
    # [7] coalesce to two ranges, highest first.
    assert archiver._delete_ranges([1, 2, 3, 7]) == [(8, 9), (2, 5)]


def test_delete_ranges_empty_list():
    assert archiver._delete_ranges([]) == []


def test_delete_ranges_sorts_unsorted_input():
    # sweep() always hands this ascending picks (select_archivable iterates
    # rows in order), but the pure function shouldn't rely on that.
    assert archiver._delete_ranges([7, 1, 3, 2]) == [(8, 9), (2, 5)]


# ---------- sweep (I/O) ----------


class _Result:
    def __init__(self, payload):
        self.payload = payload

    def execute(self):
        return self.payload


class _FakeValues:
    """Stub for svc.spreadsheets().values(): get() replays a canned sequence in
    call order (1st = initial Jobs read, 2nd = Job ID re-verify read); append()
    records what sweep() sent to Archive."""

    def __init__(self, get_sequence, appended, get_calls):
        self._get_sequence = list(get_sequence)
        self._appended = appended
        self._get_calls = get_calls

    def get(self, spreadsheetId, range):
        self._get_calls.append(range)
        return _Result(self._get_sequence.pop(0))

    def append(self, spreadsheetId, range, valueInputOption, insertDataOption, body):
        self._appended.append((range, body["values"]))
        return _Result({})


class _FakeSweepSvc:
    """Stub for the service sweep() builds via _svc(creds): spreadsheets().get()
    for the sheetId meta lookup (Jobs may not be sheetId 0 — that's the point),
    .values() for read/append, .batchUpdate() for the row deletes."""

    def __init__(self, get_sequence, jobs_sheet_id=42):
        self.appended: list = []
        self.batch_requests = None
        self.get_calls: list = []
        self._values = _FakeValues(get_sequence, self.appended, self.get_calls)
        self._jobs_sheet_id = jobs_sheet_id

    def spreadsheets(self):
        return self

    def values(self):
        return self._values

    def get(self, spreadsheetId):
        return _Result({"sheets": [
            {"properties": {"title": "Stats", "sheetId": 1}},
            {"properties": {"title": "Jobs", "sheetId": self._jobs_sheet_id}},
            {"properties": {"title": "Archive", "sheetId": 2}},
        ]})

    def batchUpdate(self, spreadsheetId, body):
        self.batch_requests = body["requests"]
        return _Result({})


def _cfg75():
    # sweep() reads min_fit/max_age from cfg.scoring.threshold /
    # cfg.caps.board_freshness_days — board_freshness_days already defaults to
    # 14; only threshold needs bumping to match the select_archivable tests above.
    cfg = make_cfg()
    cfg.scoring.threshold = 75
    return cfg


def test_sweep_empty_jobs_tab_returns_nothing_to_move(monkeypatch):
    fake = _FakeSweepSvc(get_sequence=[{"values": []}])
    monkeypatch.setattr(archiver, "_svc", lambda creds: fake)
    notes = archiver.sweep(None, "sid", _cfg75(), NOW)
    assert notes == ["archive sweep: nothing to move"]
    assert fake.appended == [] and fake.batch_requests is None


def test_sweep_nothing_to_move_leaves_sheet_untouched(monkeypatch):
    fake = _FakeSweepSvc(get_sequence=[{"values": [_row()]}])
    monkeypatch.setattr(archiver, "_svc", lambda creds: fake)
    notes = archiver.sweep(None, "sid", _cfg75(), NOW)
    assert notes == ["archive sweep: nothing to move"]
    assert fake.appended == [] and fake.batch_requests is None


def test_sweep_moves_and_deletes_coalesced_ranges_using_real_jobs_sheet_id(monkeypatch):
    rows = [
        _row(job_id="keep-0"),                              # 0: kept, fresh
        _row(status="Dismissed", job_id="row-1"),           # 1: archived (dismissed)
        _row(posted="2026-06-01 08:00", job_id="row-2"),    # 2: archived (stale) — contiguous with 1
        _row(job_id="keep-3"),                              # 3: kept, fresh
        _row(status="Dismissed", job_id="row-4"),           # 4: archived (dismissed) — singleton
    ]
    check = [[r[H["Job ID"]]] for r in rows]  # unchanged ids: recheck matches
    fake = _FakeSweepSvc(get_sequence=[{"values": rows}, {"values": check}],
                        jobs_sheet_id=987654)  # deliberately not 0
    monkeypatch.setattr(archiver, "_svc", lambda creds: fake)

    notes = archiver.sweep(None, "sid", _cfg75(), NOW)

    assert notes == ["archive sweep: moved 3 rows (2 dismissed, 1 stale)"]
    assert fake.appended[0][0] == "Archive!A1"
    assert [v[H["Job ID"]] for v in fake.appended[0][1]] == ["row-1", "row-2", "row-4"]
    # indexes 1,2 are contiguous -> one coalesced range; index 4 stays its own
    # range; both descending (index 4's range first); sheetId from meta, never 0.
    assert fake.batch_requests == [
        {"deleteDimension": {"range": {
            "sheetId": 987654, "dimension": "ROWS", "startIndex": 5, "endIndex": 6}}},
        {"deleteDimension": {"range": {
            "sheetId": 987654, "dimension": "ROWS", "startIndex": 2, "endIndex": 4}}},
    ]
    # recheck column is derived from the header map (col_letter(_IDX["Job ID"])),
    # not hand-typed — this locks in that it still resolves to "B".
    assert fake.get_calls == ["Jobs!A2:AB", "Jobs!B2:B"]


def test_sweep_aborts_delete_on_concurrent_edit_but_keeps_archive_copy(monkeypatch):
    rows = [_row(status="Dismissed", job_id="original-id")]
    check = [["a-different-id"]]  # hand-edited between the read and the delete
    fake = _FakeSweepSvc(get_sequence=[{"values": rows}, {"values": check}])
    monkeypatch.setattr(archiver, "_svc", lambda creds: fake)

    notes = archiver.sweep(None, "sid", _cfg75(), NOW)

    assert len(notes) == 1
    assert "aborted delete" in notes[0] and "1 mismatches" in notes[0]
    assert len(fake.appended) == 1  # Archive copy already made before the abort
    assert fake.batch_requests is None  # delete never sent


def test_sweep_aborts_delete_when_recheck_is_shorter_than_picks(monkeypatch):
    # Concurrent row deletion (not just an edit) makes the recheck list come
    # back shorter than the original read — the i >= len(check) branch.
    rows = [_row(status="Dismissed", job_id="only-row")]
    check: list = []
    fake = _FakeSweepSvc(get_sequence=[{"values": rows}, {"values": check}])
    monkeypatch.setattr(archiver, "_svc", lambda creds: fake)

    notes = archiver.sweep(None, "sid", _cfg75(), NOW)

    assert "aborted delete" in notes[0]
    assert fake.batch_requests is None


def test_sweep_pads_short_rows_to_full_width_before_archiving(monkeypatch):
    # Sheets API trims trailing blank cells — a row that never had Notes-onward
    # filled in comes back shorter than the 28 HEADERS columns.
    short_row = ["2026-06-01", "short-id", "AI Engineer", "Acme", "", "", "",
                "", "", "greenhouse", "90", "", "", "", "Dismissed"]
    assert len(short_row) < 28
    check = [["short-id"]]
    fake = _FakeSweepSvc(get_sequence=[{"values": [short_row]}, {"values": check}])
    monkeypatch.setattr(archiver, "_svc", lambda creds: fake)

    archiver.sweep(None, "sid", _cfg75(), NOW)

    assert len(fake.appended[0][1][0]) == 28
    assert fake.batch_requests is not None  # full round-trip: delete still proceeds
