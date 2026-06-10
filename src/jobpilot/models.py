"""Common posting model shared by every job source."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, field_validator

MAX_DESCRIPTION_CHARS = 8000


class Posting(BaseModel):
    id: str = ""  # assigned by dedup.job_id()
    title: str
    company: str
    location: str = ""
    remote: bool | None = None
    url: str
    source: str
    posted_at: datetime | None = None
    description: str = ""
    salary: str | None = None

    @field_validator("description")
    @classmethod
    def _truncate_description(cls, v: str) -> str:
        return v[:MAX_DESCRIPTION_CHARS]

    @field_validator("posted_at")
    @classmethod
    def _ensure_tz(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v


def posted_age(posted_at: datetime | None, now: datetime | None = None) -> str:
    """Human age of a posting: '45m ago', '3h ago', '2d ago', or em-dash when unknown."""
    if posted_at is None:
        return "—"
    now = now or datetime.now(timezone.utc)
    seconds = (now - posted_at).total_seconds()
    if seconds < 0:
        return "0h ago"
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes}m ago"
    hours = int(seconds // 3600)
    if hours < 24:
        return f"{hours}h ago"
    return f"{int(seconds // 86400)}d ago"
