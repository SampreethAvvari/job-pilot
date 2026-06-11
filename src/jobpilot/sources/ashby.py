"""Ashby public job-board API — free, keyless, per-company."""

from __future__ import annotations

import httpx

from jobpilot.config import Config, SourceCfg
from jobpilot.models import Posting
from jobpilot.sources.common import fetch_many, parse_dt, strip_html, title_matches

BASE = "https://api.ashbyhq.com/posting-api/job-board/{slug}"


def fetch(sc: SourceCfg, cfg: Config, client: httpx.Client) -> list[Posting]:
    def one(slug: str) -> list[Posting]:
        resp = client.get(BASE.format(slug=slug))
        resp.raise_for_status()
        out: list[Posting] = []
        for job in resp.json().get("jobs", []):
            title = job.get("title", "")
            if not title_matches(title, cfg.queries):
                continue
            out.append(
                Posting(
                    title=title,
                    company=slug,
                    location=job.get("location", ""),
                    remote=job.get("isRemote"),
                    url=job.get("jobUrl") or job.get("applyUrl", ""),
                    source="ashby",
                    posted_at=parse_dt(job.get("publishedAt")),
                    description=strip_html(job.get("descriptionHtml", "")),
                )
            )
        return out

    return fetch_many("ashby", sc.companies, one, cfg.caps.per_company)
