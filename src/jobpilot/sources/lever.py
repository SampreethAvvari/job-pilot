"""Lever public postings API — free, keyless, per-company."""

from __future__ import annotations

import httpx

from jobpilot.config import Config, SourceCfg
from jobpilot.models import Posting
from jobpilot.sources.common import fetch_many, parse_dt, title_matches

BASE = "https://api.lever.co/v0/postings/{slug}"


def fetch(sc: SourceCfg, cfg: Config, client: httpx.Client) -> list[Posting]:
    def one(slug: str) -> list[Posting]:
        resp = client.get(BASE.format(slug=slug), params={"mode": "json"})
        resp.raise_for_status()
        out: list[Posting] = []
        for job in resp.json():
            title = job.get("text", "")
            if not title_matches(title, cfg.queries):
                continue
            cats = job.get("categories") or {}
            workplace = (job.get("workplaceType") or "").lower()
            out.append(
                Posting(
                    title=title,
                    company=slug,
                    location=cats.get("location", ""),
                    remote=workplace == "remote" if workplace else None,
                    url=job.get("hostedUrl", ""),
                    source="lever",
                    posted_at=parse_dt(job.get("createdAt")),
                    description=job.get("descriptionPlain", ""),
                )
            )
        return out

    return fetch_many("lever", sc.companies, one, cfg.caps.per_company)
