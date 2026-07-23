"""Archive tab write split and dedup union (docs/superpowers/plans/2026-07-23-console-cards-freshness.md)."""
from datetime import datetime, timezone

import pytest
from googleapiclient.errors import HttpError

from jobpilot import sheets
from jobpilot.models import Posting
from jobpilot.scorer import Scored

NOW = datetime(2026, 7, 23, tzinfo=timezone.utc)


def _scored(fit, title="AI Engineer", company="Acme", sponsorship="unknown"):
    p = Posting(id="abc123", title=title, company=company, location="NY",
                url="https://x.example", source="greenhouse", description="d",
                posted_at=NOW)
    s = Scored(posting=p)
    s.fit_score = fit
    s.sponsorship_signal = sponsorship
    return s


def _fake_svc(values_resource):
    """Stub for sheets._svc(creds) whose spreadsheets().values() is values_resource."""

    class _Spreadsheets:
        def values(self):
            return values_resource

    class _Svc:
        def spreadsheets(self):
            return _Spreadsheets()

    return _Svc()


class FakeValues:
    """Stub for svc.spreadsheets().values(): append() records rows per tab;
    get() replays them back keyed by range, mirroring the real Sheets API."""

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


# ---------- append_jobs ----------


def test_append_jobs_splits_at_min_fit(monkeypatch):
    store = {}
    fake = FakeValues(store)
    monkeypatch.setattr(sheets, "_svc", lambda creds: _fake_svc(fake))
    n_jobs, n_archived = sheets.append_jobs(None, "sid", [
        _scored(90), _scored(74), _scored(None)], NOW, min_fit=75)
    assert (n_jobs, n_archived) == (1, 1)
    assert len(store["Jobs"]) == 1 and store["Jobs"][0][10] == 90
    assert len(store["Archive"]) == 1 and store["Archive"][0][14] == "Low fit"
    assert store["Archive"][0][15] == "below write threshold 75"


def test_append_jobs_empty_list_skips_the_service_call(monkeypatch):
    svc_calls = []
    monkeypatch.setattr(
        sheets, "_svc", lambda creds: svc_calls.append(creds) or _fake_svc(FakeValues({})))
    n_jobs, n_archived = sheets.append_jobs(None, "sid", [], NOW, min_fit=75)
    assert (n_jobs, n_archived) == (0, 0)
    assert svc_calls == []  # nothing to write, so no service should even be built


def test_append_jobs_all_unscored_writes_nothing(monkeypatch):
    svc_calls = []
    monkeypatch.setattr(
        sheets, "_svc", lambda creds: svc_calls.append(creds) or _fake_svc(FakeValues({})))
    n_jobs, n_archived = sheets.append_jobs(
        None, "sid", [_scored(None), _scored(None)], NOW, min_fit=75)
    assert (n_jobs, n_archived) == (0, 0)
    assert svc_calls == []  # unscored rows never reach dedup memory; retried next run


def test_append_jobs_sponsorship_unlikely_goes_to_archive_as_rejected(monkeypatch):
    # High fit score, but sponsorship unlikely still routes to Archive and keeps
    # the Status/Notes to_row already set, so it must not be relabeled "Low fit".
    store = {}
    fake = FakeValues(store)
    monkeypatch.setattr(sheets, "_svc", lambda creds: _fake_svc(fake))
    n_jobs, n_archived = sheets.append_jobs(
        None, "sid", [_scored(90, sponsorship="unlikely")], NOW, min_fit=75)
    assert (n_jobs, n_archived) == (0, 1)
    row = store["Archive"][0]
    assert row[14] == "Rejected"
    assert row[15] == "auto-rejected: sponsorship unlikely"


def test_append_jobs_fit_score_equal_to_min_fit_goes_to_jobs(monkeypatch):
    # >= is inclusive: a score exactly at the threshold is a pass, not a miss.
    store = {}
    fake = FakeValues(store)
    monkeypatch.setattr(sheets, "_svc", lambda creds: _fake_svc(fake))
    n_jobs, n_archived = sheets.append_jobs(None, "sid", [_scored(75)], NOW, min_fit=75)
    assert (n_jobs, n_archived) == (1, 0)


def test_append_jobs_mixed_batch_counts_each_bucket_once(monkeypatch):
    store = {}
    fake = FakeValues(store)
    monkeypatch.setattr(sheets, "_svc", lambda creds: _fake_svc(fake))
    scored = [
        _scored(95, title="A"),
        _scored(80, title="B"),
        _scored(60, title="C"),
        _scored(None, title="D"),
        _scored(99, title="E", sponsorship="unlikely"),
    ]
    n_jobs, n_archived = sheets.append_jobs(None, "sid", scored, NOW, min_fit=75)
    assert (n_jobs, n_archived) == (2, 2)  # D never written at all


# ---------- route_jobs (pure) ----------


def test_route_jobs_mixed_batch_high_low_unscored_unlikely_sponsorship():
    high = _scored(90, title="High")
    low = _scored(60, title="Low")
    unscored = _scored(None, title="Unscored")
    unlikely = _scored(99, title="Unlikely", sponsorship="unlikely")
    to_jobs, to_archive = sheets.route_jobs([high, low, unscored, unlikely], min_fit=75)
    assert to_jobs == [high]
    assert to_archive == [low, unlikely]  # unscored appears in neither list


def test_route_jobs_fit_equal_to_min_fit_goes_to_jobs():
    # >= is inclusive: a score exactly at the threshold is a pass, not a miss.
    s = _scored(75)
    assert sheets.route_jobs([s], min_fit=75) == ([s], [])


def test_route_jobs_empty_list():
    assert sheets.route_jobs([], min_fit=75) == ([], [])


def test_route_jobs_all_unscored_returns_empty_both():
    to_jobs, to_archive = sheets.route_jobs([_scored(None), _scored(None)], min_fit=75)
    assert to_jobs == [] and to_archive == []


def test_route_jobs_and_append_jobs_agree_on_split_sizes(monkeypatch):
    # append_jobs must not drift from route_jobs: same inputs, same split sizes,
    # so pipeline.run()'s n_matches/digest (routed separately) always matches
    # what actually lands in the Jobs tab.
    store = {}
    fake = FakeValues(store)
    monkeypatch.setattr(sheets, "_svc", lambda creds: _fake_svc(fake))
    scored = [
        _scored(90, title="A"), _scored(60, title="B"),
        _scored(None, title="C"), _scored(99, title="D", sponsorship="unlikely"),
    ]
    to_jobs, to_archive = sheets.route_jobs(scored, min_fit=75)
    n_jobs, n_archived = sheets.append_jobs(None, "sid", scored, NOW, min_fit=75)
    assert (n_jobs, n_archived) == (len(to_jobs), len(to_archive))


# ---------- known_ids ----------


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
    monkeypatch.setattr(sheets, "_svc", lambda creds: _fake_svc(fake))
    ids = sheets.known_ids(None, "sid")
    assert len(ids) == 2 and "Jobs!C2:D" in calls and "Archive!C2:D" in calls


class _FakeHttpResponse:
    status = 404
    reason = "Not Found"


def _http_error() -> HttpError:
    return HttpError(_FakeHttpResponse(), b'{"error": {"message": "not found"}}')


def test_known_ids_archive_read_failure_degrades_to_jobs_only(monkeypatch):
    class FakeGet:
        def get(self, spreadsheetId, range):
            self._tab = range.split("!")[0]
            return self

        def execute(self):
            if self._tab == "Archive":
                raise _http_error()  # hand-deleted tab: degrade, don't crash the run
            return {"values": [["AI Engineer", "Acme"]]}

    monkeypatch.setattr(sheets, "_svc", lambda creds: _fake_svc(FakeGet()))
    ids = sheets.known_ids(None, "sid")
    assert len(ids) == 1


def test_known_ids_jobs_read_failure_raises(monkeypatch):
    class FakeGet:
        def get(self, spreadsheetId, range):
            self._tab = range.split("!")[0]
            return self

        def execute(self):
            if self._tab == "Jobs":
                raise _http_error()  # a real error, must not be swallowed
            return {"values": []}

    monkeypatch.setattr(sheets, "_svc", lambda creds: _fake_svc(FakeGet()))
    with pytest.raises(HttpError):
        sheets.known_ids(None, "sid")


# ---------- ensure_archive_tab ----------


class _Result:
    def __init__(self, payload):
        self.payload = payload

    def execute(self):
        return self.payload


class FakeArchiveMeta:
    """Stub for svc.spreadsheets(): models get()/batchUpdate()/values().update()
    the way ensure_archive_tab (and ensure_reports_tab before it) call them."""

    def __init__(self, existing_titles):
        self.existing_titles = list(existing_titles)
        self.batch_updates = []
        self.header_writes = []

    def spreadsheets(self):
        return self

    def get(self, spreadsheetId):
        return _Result({"sheets": [{"properties": {"title": t}}
                                    for t in self.existing_titles]})

    def batchUpdate(self, spreadsheetId, body):
        self.batch_updates.append(body)
        return _Result({})

    def values(self):
        return self

    def update(self, spreadsheetId, range, valueInputOption, body):
        self.header_writes.append((range, body))
        return _Result({})


def test_ensure_archive_tab_creates_sheet_and_writes_headers(monkeypatch):
    fake = FakeArchiveMeta(existing_titles=["Jobs", "Stats"])
    monkeypatch.setattr(sheets, "_svc", lambda creds: fake)
    sheets.ensure_archive_tab(None, "sid")
    assert fake.batch_updates[0]["requests"][0]["addSheet"]["properties"]["title"] == "Archive"
    assert fake.header_writes[0][0] == "Archive!A1"
    assert fake.header_writes[0][1]["values"] == [sheets.HEADERS]


def test_ensure_archive_tab_is_idempotent(monkeypatch):
    fake = FakeArchiveMeta(existing_titles=["Jobs", "Archive", "Stats"])
    monkeypatch.setattr(sheets, "_svc", lambda creds: fake)
    sheets.ensure_archive_tab(None, "sid")
    assert fake.batch_updates == []
    assert fake.header_writes == []


# ---------- STATS_ROWS / refresh_stats ----------


def test_stats_rows_lifetime_counts_include_archive_active_counts_dont():
    formulas = dict(sheets.STATS_ROWS[1:])  # drop the ["Metric", "Value"] header
    assert "Archive!B2:B" in formulas["Jobs found"]
    assert "Archive!A2:A" in formulas["Found this week"]
    for metric in ("Applied", "Responses", "Interviews"):
        assert "Archive" not in formulas[metric]


def test_refresh_stats_rewrites_stats_a1(monkeypatch):
    calls = []

    class FakeStatsValues:
        def update(self, spreadsheetId, range, valueInputOption, body):
            calls.append((spreadsheetId, range, valueInputOption, body))
            return self

        def execute(self):
            return {}

    monkeypatch.setattr(sheets, "_svc", lambda creds: _fake_svc(FakeStatsValues()))
    sheets.refresh_stats(None, "sid")
    assert calls == [("sid", "Stats!A1", "USER_ENTERED", {"values": sheets.STATS_ROWS})]
