"""Greenhouse public board API — free, keyless, per-company."""

from __future__ import annotations

import httpx

from jobpilot.config import Config, SourceCfg
from jobpilot.models import Posting
from jobpilot.sources.common import fetch_many, parse_dt, strip_html, title_matches

BASE = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"


def fetch(sc: SourceCfg, cfg: Config, client: httpx.Client) -> list[Posting]:
    def one(slug: str) -> list[Posting]:
        resp = client.get(BASE.format(slug=slug), params={"content": "true"})
        resp.raise_for_status()
        out: list[Posting] = []
        for job in resp.json().get("jobs", []):
            title = job.get("title", "")
            if not title_matches(title, cfg.queries):
                continue
            out.append(
                Posting(
                    title=title,
                    company=job.get("company_name") or slug,
                    location=(job.get("location") or {}).get("name", ""),
                    url=job.get("absolute_url", ""),
                    source="greenhouse",
                    posted_at=parse_dt(job.get("first_published") or job.get("updated_at")),
                    description=strip_html(job.get("content", "")),
                )
            )
        return out

    return fetch_many("greenhouse", sc.companies, one, cfg.caps.per_company)
