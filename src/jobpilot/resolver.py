"""Detect which ATS a watchlist company uses and derive its board slug.

Three strategies, first hit wins: careers-URL pattern match (free), slug
probing against each ATS's public API, then a one-shot careers-page sniff for
embedded boards. Workday is never probed — tenant/site can't be guessed, so it
requires a careers URL.
"""

from __future__ import annotations

import re

import httpx

from jobpilot.companies import CompanyRow

URL_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("greenhouse",
     re.compile(r"(?:boards|job-boards)\.greenhouse\.io/(?:embed/job_board\?for=)?([\w-]+)")),
    ("lever", re.compile(r"jobs\.(?:eu\.)?lever\.co/([\w-]+)")),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([\w.-]+)")),
    ("workday",
     re.compile(r"([\w-]+)\.(wd\d+)\.myworkdayjobs\.com(?:/[a-z]{2}-[A-Z]{2})?/([\w-]+)")),
    ("smartrecruiters",
     re.compile(r"(?:careers|jobs)\.smartrecruiters\.com/([\w-]+)")),
    ("workable", re.compile(r"apply\.workable\.com/([\w-]+)")),
    ("recruitee", re.compile(r"([\w-]+)\.recruitee\.com")),
]

PROBES = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
    "lever": "https://api.lever.co/v0/postings/{slug}?mode=json&limit=1",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}",
    "smartrecruiters": "https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=1",
    "workable": "https://apply.workable.com/api/v1/widget/accounts/{slug}",
    "recruitee": "https://{slug}.recruitee.com/api/offers/",
}

UNSUPPORTED_NOTE = "no public ATS API found; covered via Adzuna/LinkedIn sources"


def match_url(text: str) -> tuple[str, str] | None:
    """Match a careers URL (or page HTML) against known ATS patterns."""
    for ats, pat in URL_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        if ats == "workday":
            return ats, f"{m.group(1)}/{m.group(2)}/{m.group(3)}"
        return ats, m.group(1)
    return None


def slug_candidates(company: str) -> list[str]:
    """Likely board slugs for a company name, e.g. Scale AI -> scaleai, scale-ai, scale."""
    lower = company.lower()
    joined = re.sub(r"[^a-z0-9]+", "", lower)
    hyphen = re.sub(r"[^a-z0-9]+", "-", lower).strip("-")
    first = re.sub(r"[^a-z0-9]", "", lower.split()[0]) if lower.split() else ""
    out: list[str] = []
    for s in (joined, hyphen, first):
        if s and s not in out:
            out.append(s)
    return out


def _probe(client: httpx.Client, ats: str, slug: str) -> bool:
    try:
        return client.get(PROBES[ats].format(slug=slug)).status_code == 200
    except httpx.HTTPError:
        return False


def resolve(row: CompanyRow, client: httpx.Client) -> CompanyRow:
    """Fill ats/slug/status on a pending row in place; marks it dirty."""
    row.dirty = True
    if row.careers_url:
        hit = match_url(row.careers_url)
        if hit:
            row.ats, row.slug = hit
            row.status = "active"
            return row
    for slug in slug_candidates(row.company):
        for ats in ("greenhouse", "lever", "ashby", "smartrecruiters",
                    "workable", "recruitee"):
            if _probe(client, ats, slug):
                row.ats, row.slug, row.status = ats, slug, "active"
                return row
    if row.careers_url:
        try:
            page = client.get(row.careers_url).text
            hit = match_url(page)
            if hit:
                row.ats, row.slug = hit
                row.status = "active"
                return row
        except httpx.HTTPError:
            pass
    row.status = "unsupported"
    if not row.notes:
        row.notes = UNSUPPORTED_NOTE
    return row


def resolve_pending(rows: list[CompanyRow]) -> list[str]:
    """Resolve every blank/pending row; returns pipeline notes."""
    pending = [r for r in rows
               if not r.ats and r.status in ("", "pending")]
    if not pending:
        return []
    client = httpx.Client(
        timeout=15, follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (compatible; JobPilot)"},
    )
    for r in pending:
        resolve(r, client)
    ok = sum(1 for r in pending if r.status == "active")
    return [f"resolver: {ok} of {len(pending)} new companies resolved"]
