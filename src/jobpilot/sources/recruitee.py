"""Recruitee public offers API — free, keyless, per-company."""

from __future__ import annotations

import httpx

from jobpilot.config import Config, SourceCfg
from jobpilot.models import Posting
from jobpilot.sources.common import fetch_many, parse_dt, strip_html, title_matches

BASE = "https://{slug}.recruitee.com/api/offers/"


def fetch(sc: SourceCfg, cfg: Config, client: httpx.Client) -> list[Posting]:
    def one(slug: str) -> list[Posting]:
        resp = client.get(BASE.format(slug=slug))
        resp.raise_for_status()
        out: list[Posting] = []
        for job in resp.json().get("offers", []):
            title = job.get("title", "")
            if not title_matches(title, cfg.queries):
                continue
            remote = job.get("remote")
            out.append(
                Posting(
                    title=title,
                    company=slug,
                    location=job.get("location", ""),
                    remote=bool(remote) if remote is not None else None,
                    url=job.get("careers_url", ""),
                    source="recruitee",
                    posted_at=parse_dt(job.get("published_at")),
                    description=strip_html(job.get("description", "")),
                )
            )
        return out

    return fetch_many("recruitee", sc.companies, one, cfg.caps.per_company)
