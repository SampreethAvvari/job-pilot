"""Company watchlist: the Companies sheet tab feeding per-ATS board sources.

Spec: docs/superpowers/specs/2026-06-11-company-watchlist-design.md
"""

from __future__ import annotations

from pydantic import BaseModel

from jobpilot import sheets
from jobpilot.config import Config, SourceCfg

ATS_SOURCES = (
    "greenhouse", "lever", "ashby", "workday", "smartrecruiters",
    "workable", "recruitee",
)


class CompanyRow(BaseModel):
    row: int  # 1-based sheet row
    company: str
    careers_url: str = ""
    ats: str = ""
    slug: str = ""
    status: str = ""
    notes: str = ""
    dirty: bool = False  # set by the resolver; forces a write-back


def load(creds, spreadsheet_id: str) -> list[CompanyRow]:
    out: list[CompanyRow] = []
    for d in sheets.read_companies(creds, spreadsheet_id):
        if not d["Company"].strip():
            continue
        out.append(
            CompanyRow(
                row=d["_row"],
                company=d["Company"].strip(),
                careers_url=d["Careers URL"].strip(),
                ats=d["ATS"].strip().lower(),
                slug=d["Slug"].strip(),  # case-sensitive (smartrecruiters)
                status=d["Status"].strip(),
                notes=d["Notes"].strip(),
            )
        )
    return out


def merge_into_sources(cfg: Config, rows: list[CompanyRow]) -> None:
    """Resolved watchlist companies join the per-ATS source configs.

    Sources absent from profile.yaml are created on the fly, so the Sheet alone
    is enough to activate e.g. workday without touching the profile secret.
    """
    for r in rows:
        if r.ats not in ATS_SOURCES or not r.slug or r.status == "unsupported":
            continue
        sc = cfg.sources.get(r.ats)
        if sc is None:
            sc = SourceCfg()
            cfg.sources[r.ats] = sc
        if r.slug not in sc.companies:
            sc.companies.append(r.slug)


def status_updates(rows: list[CompanyRow], stats: dict[str, dict[str, str]],
                   now_str: str) -> list[tuple[int, list[str]]]:
    """(sheet_row, [ATS, Slug, Status, Last checked, Jobs, Notes]) for rows
    touched this run — resolved by the resolver or actually fetched."""
    updates: list[tuple[int, list[str]]] = []
    for r in rows:
        s = stats.get(r.ats, {}).get(r.slug) if r.ats and r.slug else None
        if s is None and not r.dirty:
            continue
        status, jobs = r.status, ""
        if s is not None:
            if s == "404":
                if not status.startswith("error: 404"):
                    status = f"error: 404 since {now_str[:10]}"
            elif s.isdigit():
                status, jobs = "active", s
            else:
                status = f"error: {s}"
        updates.append((r.row, [r.ats, r.slug, status, now_str, jobs, r.notes]))
    return updates
