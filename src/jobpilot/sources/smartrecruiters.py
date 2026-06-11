"""SmartRecruiters public postings API — free, keyless, per-company.

Slug is the case-sensitive company identifier from
``careers.smartrecruiters.com/{Company}``. Detail endpoint fetched only for
title-matched jobs.
"""

from __future__ import annotations

import httpx

from jobpilot.config import Config, SourceCfg
from jobpilot.models import Posting
from jobpilot.sources.common import fetch_many, parse_dt, strip_html, title_matches

BASE = "https://api.smartrecruiters.com/v1/companies/{slug}/postings"


def fetch(sc: SourceCfg, cfg: Config, client: httpx.Client) -> list[Posting]:
    def one(slug: str) -> list[Posting]:
        resp = client.get(BASE.format(slug=slug), params={"limit": 100})
        resp.raise_for_status()
        out: list[Posting] = []
        for item in resp.json().get("content", []):
            title = item.get("name", "")
            if not title_matches(title, cfg.queries):
                continue
            if len(out) >= cfg.caps.per_company:
                break
            desc = ""
            try:
                d = client.get(f"{BASE.format(slug=slug)}/{item['id']}")
                d.raise_for_status()
                sections = (d.json().get("jobAd") or {}).get("sections") or {}
                desc = strip_html(
                    " ".join(s.get("text", "") for s in sections.values()
                             if isinstance(s, dict))
                )
            except (httpx.HTTPError, ValueError, KeyError):
                pass
            loc = item.get("location") or {}
            out.append(
                Posting(
                    title=title,
                    company=(item.get("company") or {}).get("name") or slug,
                    location=", ".join(
                        x for x in (loc.get("city"), loc.get("region"), loc.get("country"))
                        if x
                    ),
                    remote=loc.get("remote"),
                    url=f"https://jobs.smartrecruiters.com/{slug}/{item['id']}",
                    source="smartrecruiters",
                    posted_at=parse_dt(item.get("releasedDate")),
                    description=desc,
                )
            )
        return out

    return fetch_many("smartrecruiters", sc.companies, one, cfg.caps.per_company)
