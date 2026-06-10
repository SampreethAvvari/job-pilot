from datetime import datetime, timedelta, timezone

from jobpilot.models import MAX_DESCRIPTION_CHARS, Posting, posted_age

NOW = datetime(2026, 6, 10, 12, 0, 0, tzinfo=timezone.utc)


def test_age_minutes():
    assert posted_age(NOW - timedelta(minutes=45), NOW) == "45m ago"


def test_age_hours():
    assert posted_age(NOW - timedelta(hours=3, minutes=10), NOW) == "3h ago"


def test_age_days():
    assert posted_age(NOW - timedelta(days=2, hours=5), NOW) == "2d ago"


def test_age_unknown():
    assert posted_age(None, NOW) == "—"


def test_age_future_clamps():
    assert posted_age(NOW + timedelta(hours=1), NOW) == "0h ago"


def test_description_truncated():
    p = Posting(title="t", company="c", url="u", source="s", description="x" * 10000)
    assert len(p.description) == MAX_DESCRIPTION_CHARS


def test_naive_posted_at_becomes_utc():
    p = Posting(title="t", company="c", url="u", source="s", posted_at=datetime(2026, 6, 10))
    assert p.posted_at.tzinfo is not None
