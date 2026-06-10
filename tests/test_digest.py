from datetime import datetime, timedelta, timezone

from jobpilot.digest import build_html
from jobpilot.models import Posting
from jobpilot.scorer import Scored
from jobpilot.sheets import HEADERS, to_row

NOW = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)


def make_scored(fit, title="ML Engineer", hours_ago=5):
    return Scored(
        posting=Posting(
            id="abc", title=title, company="Acme", location="NYC",
            url="https://x.co/j", source="greenhouse",
            posted_at=NOW - timedelta(hours=hours_ago),
        ),
        fit_score=fit, why="Good fit", sponsorship_signal="likely", resume_variant="FDE",
    )


def test_digest_contains_shortlist_age_and_sheet_link():
    html = build_html(
        [make_scored(90), make_scored(30, title="Junior QA")],
        "https://docs.google.com/spreadsheets/d/X", NOW, 60, ["greenhouse: 2 jobs"],
    )
    assert "ML Engineer" in html and "Junior QA" not in html
    assert "5h ago" in html
    assert "spreadsheets/d/X" in html
    assert "greenhouse: 2 jobs" in html
    assert "<b>1</b> matches" in html


def test_digest_empty_shortlist():
    html = build_html([make_scored(10)], "https://s", NOW, 60, [])
    assert "No jobs above threshold" in html


def test_row_serialization_matches_headers():
    row = to_row(make_scored(88), NOW)
    assert len(row) == len(HEADERS)
    assert row[HEADERS.index("Posted age")] == "5h ago"
    assert row[HEADERS.index("Fit")] == 88
    assert row[HEADERS.index("Status")] == "New"


def test_unscored_row_renders_dash():
    s = make_scored(None)
    assert to_row(s, NOW)[HEADERS.index("Fit")] == "—"


def test_sponsorship_unlikely_auto_rejected():
    s = make_scored(90)
    s.sponsorship_signal = "unlikely"
    row = to_row(s, NOW)
    assert row[HEADERS.index("Status")] == "Rejected"
    assert "sponsorship" in row[HEADERS.index("Notes")]


def test_col_letter_past_z():
    from jobpilot.sheets import col_letter
    assert col_letter(0) == "A"
    assert col_letter(25) == "Z"
    assert col_letter(26) == "AA"
    assert col_letter(27) == "AB"
