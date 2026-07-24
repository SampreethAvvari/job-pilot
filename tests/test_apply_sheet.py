"""Applications sheet tab: upsert-by-Job-ID roundtrip.
Spec: .superpowers/sdd/task-6-brief.md
"""

from __future__ import annotations

import jobpilot.sheets as sh


def _make_fake_svc(monkeypatch):
    """Fake spreadsheets().values() service backing an in-memory rows list,
    mirroring tests/test_portfolio_graph.py::test_sheet_storage_roundtrip but
    supporting append() (for new rows) alongside get()/update()/clear()."""
    store = {"rows": []}  # list[list[str]], data rows only (no header)

    class FakeValues:
        def get(self, spreadsheetId, range):
            # range is either "Applications!A2:A" (Job ID column only) or
            # "Applications!A2:K" (full rows).
            col_only = range.endswith("!A2:A")
            values = ([r[:1] for r in store["rows"]] if col_only
                      else [list(r) for r in store["rows"]])

            class R:
                def execute(self_):
                    return {"values": values}
            return R()

        def update(self, spreadsheetId, range, valueInputOption, body):
            # range like "Applications!A{row}" (1-based; row 2 == index 0)
            row_num = int(range.split("!A")[1])
            idx = row_num - 2
            store["rows"][idx] = body["values"][0]

            class R:
                def execute(self_):
                    return {}
            return R()

        def append(self, spreadsheetId, range, valueInputOption,
                  insertDataOption, body):
            store["rows"].append(body["values"][0])

            class R:
                def execute(self_):
                    return {}
            return R()

        def clear(self, **k):
            class R:
                def execute(self_):
                    return {}
            return R()

    class FakeSheets:
        def values(self):
            return FakeValues()

        def get(self, spreadsheetId):
            class R:
                def execute(self_):
                    return {"sheets": [{"properties": {"title": "Applications"}}]}
            return R()

        def batchUpdate(self, spreadsheetId, body):
            class R:
                def execute(self_):
                    return {}
            return R()

    monkeypatch.setattr(sh, "_svc", lambda creds: type(
        "S", (), {"spreadsheets": lambda self_: FakeSheets()})())
    return store


def _plan(job_id="job-1", status="queued"):
    return {
        "job_id": job_id,
        "company": "Acme Robotics",
        "title": "AI Engineer",
        "ats": "greenhouse",
        "location_key": "ny",
        "cover_letter_pdf_url": "https://drive/cover.pdf",
        "questions": [{"label": "Why us?", "answer": "Because", "required": True,
                      "char_limit": None, "kind": "text", "screenshot": ""}],
        "status": status,
        "evidence_folder": "https://drive/evidence",
        "notes": ["auto-filled from resume"],
    }


def test_upsert_and_read_roundtrip(monkeypatch):
    _make_fake_svc(monkeypatch)
    sh.upsert_application(None, "sid", _plan(), "2026-07-24 12:00")

    rows = sh.read_applications(None, "sid")
    assert len(rows) == 1
    row = rows[0]
    assert row["Job ID"] == "job-1"
    assert row["Company"] == "Acme Robotics"
    assert row["Title"] == "AI Engineer"
    assert row["ATS"] == "greenhouse"
    assert row["Status"] == "queued"
    assert row["Location"] == "ny"
    assert row["Cover letter"] == "https://drive/cover.pdf"
    assert row["Evidence"] == "https://drive/evidence"
    assert row["Updated"] == "2026-07-24 12:00"
    assert isinstance(row["Questions"], list)
    assert row["Questions"][0]["label"] == "Why us?"
    assert row["Notes"] == ["auto-filled from resume"]


def test_upsert_same_job_id_twice_updates_not_appends(monkeypatch):
    _make_fake_svc(monkeypatch)
    sh.upsert_application(None, "sid", _plan(status="queued"), "2026-07-24 12:00")
    sh.upsert_application(None, "sid", _plan(status="submitted"), "2026-07-24 13:00")

    rows = sh.read_applications(None, "sid")
    assert len(rows) == 1  # updated in place, not a second row
    assert rows[0]["Status"] == "submitted"
    assert rows[0]["Updated"] == "2026-07-24 13:00"


def test_upsert_different_job_ids_produce_two_rows(monkeypatch):
    _make_fake_svc(monkeypatch)
    sh.upsert_application(None, "sid", _plan(job_id="job-1"), "2026-07-24 12:00")
    sh.upsert_application(None, "sid", _plan(job_id="job-2"), "2026-07-24 12:00")

    rows = sh.read_applications(None, "sid")
    assert len(rows) == 2
    assert {r["Job ID"] for r in rows} == {"job-1", "job-2"}


def test_read_applications_degrades_on_malformed_json(monkeypatch):
    store = _make_fake_svc(monkeypatch)
    sh.upsert_application(None, "sid", _plan(), "2026-07-24 12:00")
    # Corrupt the Questions cell (index 8) directly in the fake store.
    store["rows"][0][8] = "not json"

    rows = sh.read_applications(None, "sid")
    assert rows[0]["Questions"] == []
