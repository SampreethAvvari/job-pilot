"""LinkedIn jobs via an Apify actor — free monthly credits, result-capped (APIFY_TOKEN env).

Runs the actor asynchronously and polls, since scrapes routinely exceed the
run-sync endpoint's limit. Field names vary by actor, so normalization tries
several candidate keys.
"""

from __future__ import annotations

import os
import time

import httpx

from jobpilot.config import Config, SourceCfg
from jobpilot.models import Posting
from jobpilot.sources import SourceError, SourceSkipped
from jobpilot.sources.common import parse_dt, strip_html

API = "https://api.apify.com/v2"
POLL_TIMEOUT_S = 300


def _first(item: dict, *keys: str) -> str:
    for k in keys:
        if item.get(k):
            return item[k]
    return ""


def fetch(sc: SourceCfg, cfg: Config, client: httpx.Client) -> list[Posting]:
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        raise SourceSkipped("apify_linkedin: APIFY_TOKEN not set")

    from urllib.parse import quote

    # LinkedIn search URLs with filters baked in: last 24h (f_TPR=r86400),
    # full-time (f_JT=F), entry/associate level (f_E=2,3), US-wide.
    urls = [
        "https://www.linkedin.com/jobs/search/?keywords=" + quote(q)
        + "&location=United%20States&f_TPR=r86400&f_JT=F&f_E=2%2C3&sortBy=DD"
        for q in cfg.queries[:5]
    ]
    run_input = {
        "urls": urls,
        "count": max(10, sc.max_items),  # actor minimum is 10 (total cap)
        "scrapeCompany": False,
    }
    resp = client.post(
        f"{API}/acts/{sc.actor_id}/runs", params={"token": token}, json=run_input
    )
    resp.raise_for_status()
    run = resp.json()["data"]

    deadline = time.monotonic() + POLL_TIMEOUT_S
    status = run["status"]
    while status in ("READY", "RUNNING") and time.monotonic() < deadline:
        time.sleep(10)
        poll = client.get(f"{API}/actor-runs/{run['id']}", params={"token": token})
        poll.raise_for_status()
        run = poll.json()["data"]
        status = run["status"]
    if status != "SUCCEEDED":
        raise SourceError(f"apify_linkedin: run ended with status {status}")

    items_resp = client.get(
        f"{API}/datasets/{run['defaultDatasetId']}/items",
        params={"token": token, "format": "json", "clean": "true"},
    )
    items_resp.raise_for_status()

    out: list[Posting] = []
    for item in items_resp.json():
        title = _first(item, "title", "jobTitle", "position")
        url = _first(item, "jobUrl", "link", "url")
        if not title or not url:
            continue
        out.append(
            Posting(
                title=title,
                company=_first(item, "companyName", "company"),
                location=_first(item, "location", "jobLocation"),
                url=url,
                source="linkedin",
                posted_at=parse_dt(
                    item.get("publishedAt") or item.get("postedAt") or item.get("postedTime")
                ),
                description=strip_html(_first(item, "description", "descriptionText")),
                salary=_first(item, "salary", "salaryInfo") or None,
            )
        )
    return out[: min(sc.max_items, cfg.caps.per_source)]
