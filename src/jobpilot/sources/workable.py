"""Workable public widget API — free, keyless, per-company."""

from __future__ import annotations

import httpx

from jobpilot.config import Config, SourceCfg
from jobpilot.models import Posting
from jobpilot.sources.common import fetch_many, parse_dt, strip_html, title_matches

BASE = "https://apply.workable.com/api/v1/widget/accounts/{slug}"


def fetch(sc: SourceCfg, cfg: Config, client: httpx.Client) -> list[Posting]:
    def one(slug: str) -> list[Posting]:
        resp = client.get(BASE.format(slug=slug), params={"details": "true"})
        resp.raise_for_status()
        out: list[Posting] = []
        for job in resp.json().get("jobs", []):
            title = job.get("title", "")
            if not title_matches(title, cfg.queries):
                continue
            workplace = job.get("workplace") or ""
            out.append(
                Posting(
                    title=title,
                    company=slug,
                    location=", ".join(
                        x for x in (job.get("city"), job.get("country")) if x
                    ),
                    remote=workplace == "remote" if workplace else None,
                    url=job.get("url", ""),
                    source="workable",
                    posted_at=parse_dt(job.get("published_on") or job.get("created_at")),
                    description=strip_html(job.get("description", "")),
                )
            )
        return out

    return fetch_many("workable", sc.companies, one, cfg.caps.per_company)
