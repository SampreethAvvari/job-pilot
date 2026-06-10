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
    "adzuna": 2,
    "remoteok": 3,
    "hn_hiring": 4,
}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def job_id(p: Posting) -> str:
    """Stable cross-source id from normalized company+title+location."""
    key = f"{_norm(p.company)}|{_norm(p.title)}|{_norm(p.location)}"
    return hashlib.sha1(key.encode()).hexdigest()[:16]


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
