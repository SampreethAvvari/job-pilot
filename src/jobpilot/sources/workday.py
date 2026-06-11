"""Workday CXS job listings — free, keyless, per-company.

Slug format: ``tenant/wdN/site`` (e.g. ``nvidia/wd5/NVIDIAExternalCareerSite``),
taken from the careers URL ``https://{tenant}.{wdN}.myworkdayjobs.com/{site}``.
The list endpoint has no descriptions, so the detail endpoint is fetched only
for title-matched jobs.
"""

from __future__ import annotations

import httpx

from jobpilot.config import Config, SourceCfg
from jobpilot.models import Posting
from jobpilot.sources.common import fetch_many, parse_dt, strip_html, title_matches

LIST = "https://{tenant}.{wd}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
DETAIL = "https://{tenant}.{wd}.myworkdayjobs.com/wday/cxs/{tenant}/{site}{path}"
PAGE = 20
MAX_POSTINGS = 200  # newest-first; freshness filter drops the long tail anyway


def fetch(sc: SourceCfg, cfg: Config, client: httpx.Client) -> list[Posting]:
    def one(slug: str) -> list[Posting]:
        try:
            tenant, wd, site = slug.split("/")
        except ValueError:
            return []  # malformed slug; resolver writes tenant/wdN/site
        matched: list[dict] = []
        for offset in range(0, MAX_POSTINGS, PAGE):
            resp = client.post(
                LIST.format(tenant=tenant, wd=wd, site=site),
                json={"appliedFacets": {}, "limit": PAGE, "offset": offset,
                      "searchText": ""},
            )
            resp.raise_for_status()
            data = resp.json()
            jobs = data.get("jobPostings", [])
            matched.extend(j for j in jobs if title_matches(j.get("title", ""), cfg.queries))
            if not jobs or offset + PAGE >= int(data.get("total", 0)):
                break
        out: list[Posting] = []
        for job in matched[: cfg.caps.per_company]:
            path = job.get("externalPath", "")
            desc, posted = "", None
            try:
                d = client.get(DETAIL.format(tenant=tenant, wd=wd, site=site, path=path))
                d.raise_for_status()
                info = d.json().get("jobPostingInfo", {})
                desc = strip_html(info.get("jobDescription", ""))
                posted = parse_dt(info.get("startDate"))
            except (httpx.HTTPError, ValueError):
                pass  # listing still useful without the detail payload
            out.append(
                Posting(
                    title=job.get("title", ""),
                    company=tenant,
                    location=job.get("locationsText", ""),
                    url=f"https://{tenant}.{wd}.myworkdayjobs.com/{site}{path}",
                    source="workday",
                    posted_at=posted,
                    description=desc,
                )
            )
        return out

    return fetch_many("workday", sc.companies, one, cfg.caps.per_company)
