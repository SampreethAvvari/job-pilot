"""Job identity and dedup against the dashboard plus within a batch."""

from __future__ import annotations

import hashlib
import re

from jobpilot.models import Posting

# Higher fidelity wins when the same job arrives from two sources.
_SOURCE_RANK = {
    "linkedin": 0,
    "greenhouse": 1,
    "lever": 1,
    "ashby": 1,
    "workday": 1,
    "smartrecruiters": 1,
    "workable": 1,
    "recruitee": 1,
    "adzuna": 2,
    "remoteok": 3,
    "hn_hiring": 4,
}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def key(company: str, title: str) -> str:
    """Stable cross-source id from normalized company+title. Location is
    deliberately excluded: boards list one role per metro, and each location
    spelling was hashing to a "new" job (BL-20)."""
    return hashlib.sha1(f"{_norm(company)}|{_norm(title)}".encode()).hexdigest()[:16]


def job_id(p: Posting) -> str:
    return key(p.company, p.title)


def filter_new(postings: list[Posting], known_ids: set[str]) -> list[Posting]:
    """Assign ids, drop already-seen jobs, collapse in-batch duplicates."""
    best: dict[str, Posting] = {}
    for p in postings:
        p.id = job_id(p)
        if p.id in known_ids:
            continue
        cur = best.get(p.id)
        if cur is None or _SOURCE_RANK.get(p.source, 9) < _SOURCE_RANK.get(cur.source, 9):
            best[p.id] = p
    return list(best.values())
