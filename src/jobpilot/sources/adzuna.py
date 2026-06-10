"""Adzuna aggregator — free API key (ADZUNA_APP_ID / ADZUNA_APP_KEY env)."""

from __future__ import annotations

import os

import httpx

from jobpilot.config import Config, SourceCfg
from jobpilot.models import Posting
from jobpilot.sources import SourceSkipped
from jobpilot.sources.common import parse_dt, strip_html

URL = "https://api.adzuna.com/v1/api/jobs/us/search/1"


def fetch(sc: SourceCfg, cfg: Config, client: httpx.Client) -> list[Posting]:
    app_id, app_key = os.environ.get("ADZUNA_APP_ID"), os.environ.get("ADZUNA_APP_KEY")
    if not app_id or not app_key:
        raise SourceSkipped("adzuna: ADZUNA_APP_ID/ADZUNA_APP_KEY not set")
    out: list[Posting] = []
    per_query = max(10, sc.max_items // max(len(cfg.queries), 1))
    for query in cfg.queries:
        resp = client.get(
            URL,
            params={
                "app_id": app_id,
                "app_key": app_key,
                "what": query,
                "max_days_old": 2,
                "sort_by": "date",
                "full_time": 1,
                "results_per_page": per_query,
            },
        )
        resp.raise_for_status()
        for job in resp.json().get("results", []):
            salary = None
            if job.get("salary_min"):
                salary = f"${int(job['salary_min']):,}–${int(job.get('salary_max') or job['salary_min']):,}"
            out.append(
                Posting(
                    title=job.get("title", ""),
                    company=(job.get("company") or {}).get("display_name", ""),
                    location=(job.get("location") or {}).get("display_name", ""),
                    url=job.get("redirect_url", ""),
                    source="adzuna",
                    posted_at=parse_dt(job.get("created")),
                    description=strip_html(job.get("description", "")),
                    salary=salary,
                )
            )
    return out[: cfg.caps.per_source]
