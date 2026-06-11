# Company Watchlist Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `Companies` tab in the Dashboard Sheet becomes a self-service watchlist: add a company row, the pipeline auto-detects its ATS and polls its public job-board JSON API hourly, with per-company health visible in the tab.

**Architecture:** A resolver maps company name/careers-URL → (ats, slug) and writes it back to the tab. Four new ATS adapters (Workday, SmartRecruiters, Workable, Recruitee) join the existing three. A shared `fetch_many()` thread-pool helper gives all per-company sources parallel fetching, per-company caps, per-company error isolation, and a `RUN_STATS` sink the pipeline writes back to the tab.

**Tech Stack:** Python 3.12, httpx, pydantic v2, Google Sheets API, pytest + pytest-httpx, ruff. Spec: `docs/superpowers/specs/2026-06-11-company-watchlist-design.md`.

**Conventions:** run tests from repo root `job-pilot/` with `.venv` active: `python -m pytest tests/ -q`. Lint: `python -m ruff check src tests scripts`. Commit after every task; author is already configured (SampreethAvvari, no co-author trailer).

---

### Task 1: `caps.per_company` config field

**Files:**
- Modify: `src/jobpilot/config.py` (class `Caps`, ~line 53)
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test** — append to `tests/test_config.py`:

```python
def test_caps_per_company_default():
    from tests.test_sources import make_cfg

    cfg = make_cfg()
    assert cfg.caps.per_company == 25
```

- [ ] **Step 2: Run it** — `python -m pytest tests/test_config.py -q` — expect FAIL (`AttributeError: per_company`).

- [ ] **Step 3: Implement** — in `src/jobpilot/config.py`, class `Caps`, add after `per_source`:

```python
    per_company: int = 25  # max matched jobs per company per run (board sources)
```

- [ ] **Step 4: Run it again** — expect PASS.

- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat(config): caps.per_company for board sources"`

---

### Task 2: `fetch_many()` + `RUN_STATS` in sources/common.py

**Files:**
- Modify: `src/jobpilot/sources/common.py`
- Test: `tests/test_sources.py`

- [ ] **Step 1: Write the failing test** — append to `tests/test_sources.py`:

```python
def test_fetch_many_isolates_errors_caps_and_records_stats(httpx_mock):
    from jobpilot.models import Posting
    from jobpilot.sources import common

    httpx_mock.add_response(url="https://x.test/good", json={})
    httpx_mock.add_response(url="https://x.test/bad", status_code=404)
    client = httpx.Client()

    def one(slug):
        client.get(f"https://x.test/{slug}").raise_for_status()
        return [
            Posting(title=f"Engineer {i}", company=slug, url="u", source="t")
            for i in range(3)
        ]

    common.RUN_STATS.clear()
    out = common.fetch_many("t", ["good", "bad"], one, per_company=2)
    assert len(out) == 2  # capped per company
    assert common.RUN_STATS["t"] == {"good": "2", "bad": "404"}
```

- [ ] **Step 2: Run it** — `python -m pytest tests/test_sources.py::test_fetch_many_isolates_errors_caps_and_records_stats -q` — expect FAIL (no `fetch_many`).

- [ ] **Step 3: Implement** — in `src/jobpilot/sources/common.py`, add to the imports `from concurrent.futures import ThreadPoolExecutor` and `import httpx`, then append:

```python
# Per-run health sink for per-company board sources: source -> slug -> count|error.
# Cleared by pipeline.fetch_all() at the start of every run; the pipeline writes
# it back to the Companies sheet tab afterwards.
RUN_STATS: dict[str, dict[str, str]] = {}


def fetch_many(source: str, slugs: list[str], fetch_one, per_company: int,
               max_workers: int = 16) -> list:
    """Run fetch_one(slug) -> list[Posting] across a thread pool.

    Caps each company's matches at per_company, records per-slug counts or
    error strings in RUN_STATS, and never lets one bad board kill the source.
    """
    def run(slug: str) -> tuple[str, list, str]:
        try:
            return slug, fetch_one(slug), ""
        except httpx.HTTPStatusError as exc:
            return slug, [], str(exc.response.status_code)
        except httpx.HTTPError as exc:
            return slug, [], type(exc).__name__

    postings: list = []
    stats = RUN_STATS.setdefault(source, {})
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for slug, got, err in pool.map(run, slugs):
            if err:
                stats[slug] = err
                continue
            got = got[:per_company]
            stats[slug] = str(len(got))
            postings.extend(got)
    return postings
```

- [ ] **Step 4: Run it again** — expect PASS.

- [ ] **Step 5: Commit** — `git commit -am "feat(sources): fetch_many thread-pool helper with per-company caps and RUN_STATS"`

---

### Task 3: Refactor greenhouse/lever/ashby onto `fetch_many`

**Files:**
- Modify: `src/jobpilot/sources/greenhouse.py`, `src/jobpilot/sources/lever.py`, `src/jobpilot/sources/ashby.py`
- Test: `tests/test_sources.py`

- [ ] **Step 1: Write the failing test** — append to `tests/test_sources.py`:

```python
def test_greenhouse_per_company_cap(httpx_mock):
    jobs = {
        "jobs": [
            {
                "title": f"Software Engineer {i}",
                "absolute_url": f"https://boards.greenhouse.io/stripe/jobs/{i}",
                "location": {"name": "NYC"},
                "first_published": "2026-06-09T12:00:00Z",
                "content": "desc",
            }
            for i in range(5)
        ]
    }
    httpx_mock.add_response(url=re.compile(r".*greenhouse.*"), json=jobs)
    cfg = make_cfg()
    cfg.caps.per_company = 2
    out = greenhouse.fetch(cfg.sources["greenhouse"], cfg, httpx.Client())
    assert len(out) == 2
```

- [ ] **Step 2: Run it** — expect FAIL (5 returned; old code truncates only at `per_source`).

- [ ] **Step 3: Implement** — replace the `fetch` body in each of the three files. The 404-skip moves into `fetch_many` (it records `"404"` and continues).

`src/jobpilot/sources/greenhouse.py`:

```python
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
```

`src/jobpilot/sources/lever.py`:

```python
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
```

`src/jobpilot/sources/ashby.py`:

```python
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
```

- [ ] **Step 4: Run the whole suite** — `python -m pytest tests/ -q` — all PASS (existing greenhouse/lever/ashby tests still green).

- [ ] **Step 5: Commit** — `git commit -am "refactor(sources): board sources fetch in parallel with per-company caps and health stats"`

---

### Task 4: Workday adapter

**Files:**
- Create: `src/jobpilot/sources/workday.py`, `tests/fixtures/workday.json`, `tests/fixtures/workday_detail.json`
- Test: `tests/test_sources.py`

- [ ] **Step 1: Create fixtures.**

`tests/fixtures/workday.json`:

```json
{
  "total": 2,
  "jobPostings": [
    {
      "title": "AI Engineer",
      "externalPath": "/job/New-York/AI-Engineer_JR100",
      "locationsText": "New York",
      "postedOn": "Posted Today"
    },
    {
      "title": "Accountant",
      "externalPath": "/job/Austin/Accountant_JR101",
      "locationsText": "Austin",
      "postedOn": "Posted Today"
    }
  ]
}
```

`tests/fixtures/workday_detail.json`:

```json
{
  "jobPostingInfo": {
    "jobDescription": "<p>Build ML systems.</p>",
    "startDate": "2026-06-10"
  }
}
```

- [ ] **Step 2: Write the failing test** — append to `tests/test_sources.py` (note the import addition at the top: extend the existing `from jobpilot.sources import ...` line with `workday` in later tasks as each module appears; final form after Task 7 is `from jobpilot.sources import adzuna, apify_linkedin, ashby, greenhouse, hn_hiring, lever, recruitee, remoteok, smartrecruiters, workable, workday`):

```python
def test_workday(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url=re.compile(r".*myworkdayjobs.*/wday/cxs/.*/jobs"),
        json=load("workday"),
    )
    httpx_mock.add_response(
        url=re.compile(r".*myworkdayjobs.*JR100.*"),
        json=load("workday_detail"),
    )
    cfg = make_cfg(workday={"companies": ["acme/wd5/External"]})
    out = workday.fetch(cfg.sources["workday"], cfg, httpx.Client())
    _assert_valid(out, "workday")
    assert len(out) == 1  # Accountant filtered before any detail fetch
    assert out[0].description == "Build ML systems."
    assert out[0].posted_at is not None
    assert out[0].url == "https://acme.wd5.myworkdayjobs.com/External/job/New-York/AI-Engineer_JR100"
```

- [ ] **Step 3: Run it** — expect FAIL (`ImportError`).

- [ ] **Step 4: Implement** — `src/jobpilot/sources/workday.py`:

```python
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
```

- [ ] **Step 5: Run it again** — `python -m pytest tests/test_sources.py::test_workday -q` — expect PASS.

- [ ] **Step 6: Commit** — `git add -A && git commit -m "feat(sources): workday adapter (CXS public JSON, detail fetch for matched jobs only)"`

---

### Task 5: SmartRecruiters adapter

**Files:**
- Create: `src/jobpilot/sources/smartrecruiters.py`, `tests/fixtures/smartrecruiters.json`, `tests/fixtures/smartrecruiters_detail.json`
- Test: `tests/test_sources.py`

- [ ] **Step 1: Create fixtures.**

`tests/fixtures/smartrecruiters.json`:

```json
{
  "content": [
    {
      "id": "744000001",
      "name": "Machine Learning Engineer",
      "releasedDate": "2026-06-09T10:00:00.000Z",
      "location": {"city": "Austin", "region": "TX", "country": "us", "remote": false},
      "company": {"name": "Acme Corp"}
    },
    {
      "id": "744000002",
      "name": "Sales Lead",
      "releasedDate": "2026-06-09T10:00:00.000Z",
      "location": {"city": "NYC", "country": "us"},
      "company": {"name": "Acme Corp"}
    }
  ]
}
```

`tests/fixtures/smartrecruiters_detail.json`:

```json
{
  "jobAd": {
    "sections": {
      "jobDescription": {"title": "Job Description", "text": "<p>Do ML.</p>"},
      "qualifications": {"title": "Qualifications", "text": "<p>Python</p>"}
    }
  }
}
```

- [ ] **Step 2: Write the failing test** — append to `tests/test_sources.py`:

```python
def test_smartrecruiters(httpx_mock):
    httpx_mock.add_response(
        url=re.compile(r".*api\.smartrecruiters\.com/v1/companies/Acme/postings\?.*"),
        json=load("smartrecruiters"),
    )
    httpx_mock.add_response(
        url=re.compile(r".*postings/744000001.*"),
        json=load("smartrecruiters_detail"),
    )
    cfg = make_cfg(smartrecruiters={"companies": ["Acme"]})
    out = smartrecruiters.fetch(cfg.sources["smartrecruiters"], cfg, httpx.Client())
    _assert_valid(out, "smartrecruiters")
    assert len(out) == 1  # Sales Lead filtered, no detail call for it
    assert "Do ML." in out[0].description and "Python" in out[0].description
    assert out[0].company == "Acme Corp"
```

- [ ] **Step 3: Run it** — expect FAIL (`ImportError`).

- [ ] **Step 4: Implement** — `src/jobpilot/sources/smartrecruiters.py`:

```python
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
```

- [ ] **Step 5: Run it again** — expect PASS.

- [ ] **Step 6: Commit** — `git add -A && git commit -m "feat(sources): smartrecruiters adapter"`

---

### Task 6: Workable adapter

**Files:**
- Create: `src/jobpilot/sources/workable.py`, `tests/fixtures/workable.json`
- Test: `tests/test_sources.py`

- [ ] **Step 1: Create fixture** — `tests/fixtures/workable.json`:

```json
{
  "jobs": [
    {
      "title": "Data Engineer",
      "city": "Berlin",
      "country": "Germany",
      "workplace": "remote",
      "url": "https://apply.workable.com/acme/j/ABC123",
      "published_on": "2026-06-08",
      "description": "<p>Pipelines.</p>"
    },
    {
      "title": "Office Admin",
      "city": "Berlin",
      "country": "Germany",
      "url": "https://apply.workable.com/acme/j/DEF456",
      "published_on": "2026-06-08",
      "description": "x"
    }
  ]
}
```

- [ ] **Step 2: Write the failing test** — append to `tests/test_sources.py`:

```python
def test_workable(httpx_mock):
    httpx_mock.add_response(url=re.compile(r".*workable.*"), json=load("workable"))
    cfg = make_cfg(workable={"companies": ["acme"]})
    out = workable.fetch(cfg.sources["workable"], cfg, httpx.Client())
    _assert_valid(out, "workable")
    assert len(out) == 1
    assert out[0].remote is True
    assert out[0].description == "Pipelines."
```

- [ ] **Step 3: Run it** — expect FAIL.

- [ ] **Step 4: Implement** — `src/jobpilot/sources/workable.py`:

```python
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
```

- [ ] **Step 5: Run it again** — expect PASS.

- [ ] **Step 6: Commit** — `git add -A && git commit -m "feat(sources): workable adapter"`

---

### Task 7: Recruitee adapter + registry + dedup ranks + profile template

**Files:**
- Create: `src/jobpilot/sources/recruitee.py`, `tests/fixtures/recruitee.json`
- Modify: `src/jobpilot/sources/__init__.py`, `src/jobpilot/dedup.py:11-19`, `profile.yaml`
- Test: `tests/test_sources.py`

- [ ] **Step 1: Create fixture** — `tests/fixtures/recruitee.json`:

```json
{
  "offers": [
    {
      "title": "Software Engineer Backend",
      "location": "Amsterdam, Netherlands",
      "remote": true,
      "careers_url": "https://acme.recruitee.com/o/backend-engineer",
      "published_at": "2026-06-07T09:00:00.000Z",
      "description": "<p>Go services.</p>"
    },
    {
      "title": "Recruiter",
      "location": "Amsterdam",
      "careers_url": "https://acme.recruitee.com/o/recruiter",
      "published_at": "2026-06-07T09:00:00.000Z",
      "description": "x"
    }
  ]
}
```

- [ ] **Step 2: Write the failing test** — append to `tests/test_sources.py`:

```python
def test_recruitee(httpx_mock):
    httpx_mock.add_response(url=re.compile(r".*recruitee.*"), json=load("recruitee"))
    cfg = make_cfg(recruitee={"companies": ["acme"]})
    out = recruitee.fetch(cfg.sources["recruitee"], cfg, httpx.Client())
    _assert_valid(out, "recruitee")
    assert len(out) == 1
    assert out[0].remote is True
```

- [ ] **Step 3: Run it** — expect FAIL.

- [ ] **Step 4: Implement** — `src/jobpilot/sources/recruitee.py`:

```python
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
```

- [ ] **Step 5: Register all four sources** — in `src/jobpilot/sources/__init__.py`, extend the import inside `registry()` and the returned dict:

```python
def registry() -> dict[str, FetchFn]:
    from jobpilot.sources import (
        adzuna,
        apify_linkedin,
        ashby,
        greenhouse,
        hn_hiring,
        lever,
        recruitee,
        remoteok,
        smartrecruiters,
        workable,
        workday,
    )

    return {
        "greenhouse": greenhouse.fetch,
        "lever": lever.fetch,
        "ashby": ashby.fetch,
        "workday": workday.fetch,
        "smartrecruiters": smartrecruiters.fetch,
        "workable": workable.fetch,
        "recruitee": recruitee.fetch,
        "remoteok": remoteok.fetch,
        "hn_hiring": hn_hiring.fetch,
        "adzuna": adzuna.fetch,
        "apify_linkedin": apify_linkedin.fetch,
    }
```

- [ ] **Step 6: Dedup ranks** — in `src/jobpilot/dedup.py`, `_SOURCE_RANK`, add alongside the existing rank-1 entries:

```python
    "workday": 1,
    "smartrecruiters": 1,
    "workable": 1,
    "recruitee": 1,
```

- [ ] **Step 7: Profile template** — in `profile.yaml` (repo Jane Doe template), after the `ashby:` block add:

```yaml
  # The four below are normally populated from the Companies sheet tab
  # (auto-resolved by jobpilot.resolver); listing slugs here also works.
  workday:
    enabled: true
    companies: []   # slug format: tenant/wdN/site, from the careers URL
  smartrecruiters:
    enabled: true
    companies: []   # case-sensitive id from careers.smartrecruiters.com/{Company}
  workable:
    enabled: true
    companies: []
  recruitee:
    enabled: true
    companies: []
```

- [ ] **Step 8: Update the test imports** — top of `tests/test_sources.py`, final import line:

```python
from jobpilot.sources import (
    adzuna,
    apify_linkedin,
    ashby,
    greenhouse,
    hn_hiring,
    lever,
    recruitee,
    remoteok,
    smartrecruiters,
    workable,
    workday,
)
```

- [ ] **Step 9: Run the whole suite** — `python -m pytest tests/ -q` — all PASS, including `test_registry_covers_all_profile_sources`.

- [ ] **Step 10: Commit** — `git add -A && git commit -m "feat(sources): recruitee adapter; register workday/smartrecruiters/workable/recruitee"`

---

### Task 8: Companies tab functions in sheets.py

**Files:**
- Modify: `src/jobpilot/sheets.py` (append after the InboxWatch block, ~line 270)

No unit test (sheets.py functions are thin API wrappers, untested by convention in this repo — verified live in Task 12).

- [ ] **Step 1: Implement** — append to `src/jobpilot/sheets.py`:

```python
COMPANIES_HEADERS = [
    "Company", "Careers URL", "ATS", "Slug", "Status", "Last checked",
    "Jobs (last fetch)", "Notes",
]


def ensure_companies_tab(creds, spreadsheet_id: str) -> None:
    svc = _svc(creds)
    meta = svc.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    titles = [s["properties"]["title"] for s in meta["sheets"]]
    if "Companies" in titles:
        return
    svc.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": [{"addSheet": {"properties": {"title": "Companies"}}}]},
    ).execute()
    svc.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id, range="Companies!A1", valueInputOption="RAW",
        body={"values": [COMPANIES_HEADERS]},
    ).execute()


def read_companies(creds, spreadsheet_id: str) -> list[dict]:
    """Companies tab rows as dicts keyed by header, with 1-based row numbers."""
    ensure_companies_tab(creds, spreadsheet_id)
    resp = (
        _svc(creds)
        .spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range="Companies!A2:H")
        .execute()
    )
    rows = []
    for i, values in enumerate(resp.get("values", []), start=2):
        padded = values + [""] * (len(COMPANIES_HEADERS) - len(values))
        rows.append({"_row": i, **dict(zip(COMPANIES_HEADERS, padded))})
    return rows


def update_company_rows(creds, spreadsheet_id: str,
                        updates: list[tuple[int, list[str]]]) -> None:
    """Batch-write C..H (ATS, Slug, Status, Last checked, Jobs, Notes) per row."""
    if not updates:
        return
    data = [{"range": f"Companies!C{row}", "values": [vals]} for row, vals in updates]
    _svc(creds).spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"valueInputOption": "RAW", "data": data},
    ).execute()
```

- [ ] **Step 2: Lint** — `python -m ruff check src` — clean.

- [ ] **Step 3: Commit** — `git commit -am "feat(sheets): Companies watchlist tab (ensure/read/update)"`

---

### Task 9: companies.py — load, merge, status write-back

**Files:**
- Create: `src/jobpilot/companies.py`
- Test: `tests/test_companies.py`

- [ ] **Step 1: Write the failing tests** — `tests/test_companies.py`:

```python
from jobpilot import companies
from jobpilot.companies import CompanyRow
from tests.test_sources import make_cfg


def test_merge_into_sources_adds_creates_and_dedupes():
    cfg = make_cfg()  # greenhouse already has ["stripe"]; no workday source yet
    rows = [
        CompanyRow(row=2, company="Nvidia", ats="workday",
                   slug="nvidia/wd5/Ext", status="active"),
        CompanyRow(row=3, company="Stripe", ats="greenhouse", slug="stripe",
                   status="active"),
        CompanyRow(row=4, company="Mystery", status="unsupported"),
        CompanyRow(row=5, company="Typo Co", ats="linkedin", slug="x", status="active"),
    ]
    companies.merge_into_sources(cfg, rows)
    assert cfg.sources["workday"].companies == ["nvidia/wd5/Ext"]
    assert cfg.sources["workday"].enabled
    assert cfg.sources["greenhouse"].companies.count("stripe") == 1
    assert "linkedin" not in cfg.sources


def test_status_updates_counts_404s_and_skips_untouched():
    rows = [
        CompanyRow(row=2, company="A", ats="greenhouse", slug="a", status="active"),
        CompanyRow(row=3, company="B", ats="greenhouse", slug="b", status="active"),
        CompanyRow(row=4, company="C", ats="lever", slug="c", status="active"),
        CompanyRow(row=5, company="D", status="unsupported",
                   notes="no public ATS API found", dirty=True),
        CompanyRow(row=6, company="E", ats="greenhouse", slug="e",
                   status="error: 404 since 2026-06-01"),
    ]
    stats = {"greenhouse": {"a": "3", "b": "404", "e": "404"}}
    ups = dict(companies.status_updates(rows, stats, "2026-06-11 12:00"))
    assert ups[2] == ["greenhouse", "a", "active", "2026-06-11 12:00", "3", ""]
    assert ups[3][2] == "error: 404 since 2026-06-11"
    assert 4 not in ups  # no stats, not dirty -> row untouched
    assert ups[5][2] == "unsupported"
    assert ups[6][2] == "error: 404 since 2026-06-01"  # original since-date kept
```

- [ ] **Step 2: Run them** — `python -m pytest tests/test_companies.py -q` — expect FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement** — `src/jobpilot/companies.py`:

```python
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
```

- [ ] **Step 4: Run them again** — expect PASS.

- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat(companies): watchlist load/merge/status write-back"`

---

### Task 10: resolver.py — ATS auto-detection

**Files:**
- Create: `src/jobpilot/resolver.py`
- Test: `tests/test_resolver.py`

- [ ] **Step 1: Write the failing tests** — `tests/test_resolver.py`:

```python
import httpx

from jobpilot import resolver
from jobpilot.companies import CompanyRow


def test_match_url_patterns():
    cases = {
        "https://boards.greenhouse.io/stripe": ("greenhouse", "stripe"),
        "https://job-boards.greenhouse.io/figma/jobs/123": ("greenhouse", "figma"),
        "https://boards.greenhouse.io/embed/job_board?for=gusto": ("greenhouse", "gusto"),
        "https://jobs.lever.co/palantir": ("lever", "palantir"),
        "https://jobs.eu.lever.co/n26": ("lever", "n26"),
        "https://jobs.ashbyhq.com/openai": ("ashby", "openai"),
        "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite":
            ("workday", "nvidia/wd5/NVIDIAExternalCareerSite"),
        "https://salesforce.wd12.myworkdayjobs.com/en-US/External_Career_Site":
            ("workday", "salesforce/wd12/External_Career_Site"),
        "https://careers.smartrecruiters.com/Visa": ("smartrecruiters", "Visa"),
        "https://apply.workable.com/acme-inc/": ("workable", "acme-inc"),
        "https://acme.recruitee.com/": ("recruitee", "acme"),
    }
    for url, expected in cases.items():
        assert resolver.match_url(url) == expected, url
    assert resolver.match_url("https://www.example.com/careers") is None


def test_slug_candidates():
    assert resolver.slug_candidates("Scale AI") == ["scaleai", "scale-ai", "scale"]
    assert resolver.slug_candidates("Stripe") == ["stripe"]


def test_resolve_from_careers_url_no_http():
    row = CompanyRow(row=2, company="Stripe",
                     careers_url="https://boards.greenhouse.io/stripe")
    resolver.resolve(row, httpx.Client())  # URL match needs no requests
    assert (row.ats, row.slug, row.status, row.dirty) == \
        ("greenhouse", "stripe", "active", True)


def test_resolve_by_probe(httpx_mock):
    httpx_mock.add_response(
        url="https://boards-api.greenhouse.io/v1/boards/stripe/jobs",
        json={"jobs": []},
    )
    row = CompanyRow(row=2, company="Stripe")
    resolver.resolve(row, httpx.Client())
    assert (row.ats, row.slug, row.status) == ("greenhouse", "stripe", "active")


def test_resolve_unsupported(httpx_mock):
    httpx_mock.add_response(status_code=404, is_reusable=True)  # every probe 404s
    row = CompanyRow(row=2, company="Zzz Qqq")
    resolver.resolve(row, httpx.Client())
    assert row.status == "unsupported"
    assert row.dirty


def test_resolve_pending_skips_resolved_rows():
    rows = [CompanyRow(row=2, company="Done", ats="lever", slug="done",
                       status="active")]
    notes = resolver.resolve_pending(rows)
    assert notes == []
```

- [ ] **Step 2: Run them** — expect FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement** — `src/jobpilot/resolver.py`:

```python
"""Detect which ATS a watchlist company uses and derive its board slug.

Three strategies, first hit wins: careers-URL pattern match (free), slug
probing against each ATS's public API, then a one-shot careers-page sniff for
embedded boards. Workday is never probed — tenant/site can't be guessed, so it
requires a careers URL.
"""

from __future__ import annotations

import re

import httpx

from jobpilot.companies import CompanyRow

URL_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("greenhouse",
     re.compile(r"(?:boards|job-boards)\.greenhouse\.io/(?:embed/job_board\?for=)?([\w-]+)")),
    ("lever", re.compile(r"jobs\.(?:eu\.)?lever\.co/([\w-]+)")),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([\w.-]+)")),
    ("workday",
     re.compile(r"([\w-]+)\.(wd\d+)\.myworkdayjobs\.com(?:/[a-z]{2}-[A-Z]{2})?/([\w-]+)")),
    ("smartrecruiters",
     re.compile(r"(?:careers|jobs)\.smartrecruiters\.com/([\w-]+)")),
    ("workable", re.compile(r"apply\.workable\.com/([\w-]+)")),
    ("recruitee", re.compile(r"([\w-]+)\.recruitee\.com")),
]

PROBES = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
    "lever": "https://api.lever.co/v0/postings/{slug}?mode=json&limit=1",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}",
    "smartrecruiters": "https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=1",
    "workable": "https://apply.workable.com/api/v1/widget/accounts/{slug}",
    "recruitee": "https://{slug}.recruitee.com/api/offers/",
}

UNSUPPORTED_NOTE = "no public ATS API found; covered via Adzuna/LinkedIn sources"


def match_url(text: str) -> tuple[str, str] | None:
    """Match a careers URL (or page HTML) against known ATS patterns."""
    for ats, pat in URL_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        if ats == "workday":
            return ats, f"{m.group(1)}/{m.group(2)}/{m.group(3)}"
        return ats, m.group(1)
    return None


def slug_candidates(company: str) -> list[str]:
    """Likely board slugs for a company name, e.g. Scale AI -> scaleai, scale-ai, scale."""
    lower = company.lower()
    joined = re.sub(r"[^a-z0-9]+", "", lower)
    hyphen = re.sub(r"[^a-z0-9]+", "-", lower).strip("-")
    first = re.sub(r"[^a-z0-9]", "", lower.split()[0]) if lower.split() else ""
    out: list[str] = []
    for s in (joined, hyphen, first):
        if s and s not in out:
            out.append(s)
    return out


def _probe(client: httpx.Client, ats: str, slug: str) -> bool:
    try:
        return client.get(PROBES[ats].format(slug=slug)).status_code == 200
    except httpx.HTTPError:
        return False


def resolve(row: CompanyRow, client: httpx.Client) -> CompanyRow:
    """Fill ats/slug/status on a pending row in place; marks it dirty."""
    row.dirty = True
    if row.careers_url:
        hit = match_url(row.careers_url)
        if hit:
            row.ats, row.slug = hit
            row.status = "active"
            return row
    for slug in slug_candidates(row.company):
        for ats in ("greenhouse", "lever", "ashby", "smartrecruiters",
                    "workable", "recruitee"):
            if _probe(client, ats, slug):
                row.ats, row.slug, row.status = ats, slug, "active"
                return row
    if row.careers_url:
        try:
            page = client.get(row.careers_url).text
            hit = match_url(page)
            if hit:
                row.ats, row.slug = hit
                row.status = "active"
                return row
        except httpx.HTTPError:
            pass
    row.status = "unsupported"
    if not row.notes:
        row.notes = UNSUPPORTED_NOTE
    return row


def resolve_pending(rows: list[CompanyRow]) -> list[str]:
    """Resolve every blank/pending row; returns pipeline notes."""
    pending = [r for r in rows
               if not r.ats and r.status in ("", "pending")]
    if not pending:
        return []
    client = httpx.Client(
        timeout=15, follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (compatible; JobPilot)"},
    )
    for r in pending:
        resolve(r, client)
    ok = sum(1 for r in pending if r.status == "active")
    return [f"resolver: {ok} of {len(pending)} new companies resolved"]
```

- [ ] **Step 4: Run them again** — `python -m pytest tests/test_resolver.py -q` — expect PASS.

- [ ] **Step 5: Lint + full suite** — `python -m ruff check src tests && python -m pytest tests/ -q` — clean/green.

- [ ] **Step 6: Commit** — `git add -A && git commit -m "feat(resolver): ATS auto-detection (URL patterns, slug probing, page sniff)"`

---

### Task 11: Pipeline wiring

**Files:**
- Modify: `src/jobpilot/pipeline.py`
- Test: existing `tests/test_pipeline.py` must stay green (dry-run path unchanged in behavior)

- [ ] **Step 1: Implement.** Three edits to `src/jobpilot/pipeline.py`:

(a) In `fetch_all`, clear the stats sink at the top:

```python
def fetch_all(cfg: Config, only: list[str] | None = None) -> tuple[list[Posting], list[str]]:
    from jobpilot.sources import common
    common.RUN_STATS.clear()
    client = httpx.Client(timeout=60, follow_redirects=True)
    ...  # rest unchanged
```

(b) Restructure `run()` so the dry-run branch comes first (it has no Sheet access, hence no watchlist), and the live path loads/resolves/merges the watchlist **before** fetching and writes health back **after**:

```python
def run(cfg: Config, dry_run: bool = False, only: list[str] | None = None,
        fast: bool = False) -> list[Scored]:
    now = datetime.now(timezone.utc)

    if dry_run:
        postings, notes = fetch_all(cfg, only)
        postings = _apply_quality_filter(postings, cfg, now, notes)
        new = dedup.filter_new(postings, set())
        scored = score(new, cfg, _stub_llm)
        notes.append(f"dedup: {len(new)} new of {len(postings)} fetched (no sheet in dry-run)")
        _print_table(scored, now)
        html = digest.build_html(scored, "https://sheet.example", now, cfg.scoring.threshold, notes)
        Path("digest_preview.html").write_text(html, encoding="utf-8")
        print(f"\n{len(scored)} jobs; digest preview -> digest_preview.html")
        return scored

    from jobpilot import companies, inboxwatch, resolver
    from jobpilot.gauth import credentials, inbox_credentials
    from jobpilot.sources import common as sources_common

    creds = credentials()
    sid = os.environ.get("JOBPILOT_SPREADSHEET_ID") or cfg.sheet.spreadsheet_id
    sid = sheets.ensure_dashboard(creds, sid)

    watchlist = companies.load(creds, sid)
    resolver_notes = resolver.resolve_pending(watchlist)
    companies.merge_into_sources(cfg, watchlist)

    postings, notes = fetch_all(cfg, only)
    notes.extend(resolver_notes)
    sheets.update_company_rows(
        creds, sid,
        companies.status_updates(watchlist, sources_common.RUN_STATS,
                                 now.strftime("%Y-%m-%d %H:%M")),
    )
    postings = _apply_quality_filter(postings, cfg, now, notes)

    llm = make_gemini_llm(cfg)
    new = dedup.filter_new(postings, sheets.known_ids(creds, sid))
    ...  # rest of the existing live path unchanged
```

(c) Extract the repeated freshness-note block into a helper (replaces the two inline copies):

```python
def _apply_quality_filter(postings: list[Posting], cfg: Config, now: datetime,
                          notes: list[str]) -> list[Posting]:
    fresh = quality_filter(postings, cfg, now)
    notes.append(
        f"freshness/seniority filter: kept {len(fresh)} of {len(postings)} "
        f"(window {cfg.caps.freshness_days}d)"
    )
    return fresh
```

- [ ] **Step 2: Full suite + lint** — `python -m pytest tests/ -q && python -m ruff check src tests scripts` — green/clean (notably `test_dry_run_end_to_end`).

- [ ] **Step 3: Commit** — `git commit -am "feat(pipeline): company watchlist — resolve, merge into sources, write health back to Companies tab"`

---

### Task 12: README note, deploy, scheduler args, live smoke test

**Files:**
- Modify: `README.md` (sources/configuration section — add a short "Company watchlist" paragraph)

- [ ] **Step 1: README** — add under the sources/configuration docs:

```markdown
### Company watchlist

Add rows to the **Companies** tab of the dashboard Sheet (created automatically):
just a company name, plus its careers URL if you have it (required for Workday).
Within one scheduled run the pipeline detects the company's ATS
(Greenhouse / Lever / Ashby / Workday / SmartRecruiters / Workable / Recruitee),
fills in the board slug, and starts polling its public job-board API. The
`Status`, `Last checked`, and `Jobs (last fetch)` columns show each board's
health; companies on unsupported ATSes are marked `unsupported` and remain
covered by the aggregator sources.
```

- [ ] **Step 2: Final full check** — `python -m pytest tests/ -q && python -m ruff check src tests scripts`.

- [ ] **Step 3: Commit + push (auto-deploys via GH Actions/WIF)**:

```bash
git add -A && git commit -m "docs: company watchlist README section" && git push origin master
```

- [ ] **Step 4: Watch the deploy** — `gh run list --repo SampreethAvvari/job-pilot --limit 3` until the deploy workflow succeeds.

- [ ] **Step 5: Update the hourly scheduler args** (adds the four new sources):

```bash
gcloud scheduler jobs update http jobpilot-hourly --location=us-central1 --project=jobpilot-sva \
  --message-body='{"overrides":{"containerOverrides":[{"args":["--fast","--sources","greenhouse,lever,ashby,workday,smartrecruiters,workable,recruitee,remoteok,hn_hiring,adzuna"]}]}}'
```

- [ ] **Step 6: Live smoke test** — execute one fast run and confirm the Companies tab appears and the run completes:

```bash
gcloud run jobs execute jobpilot --region=us-central1 --project=jobpilot-sva \
  --args="--fast","--sources","greenhouse,lever,ashby" --wait
```

Expected: execution succeeds; the Sheet now has a `Companies` tab with headers. Then add 2–3 real rows (e.g. `Nvidia` + `https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite`, `Snowflake`, `Canva`) and run once more with all sources to verify resolution + fetch end-to-end.

---

## Self-review notes

- Spec coverage: tab schema (T8/T9), resolver 3-step (T10), four adapters (T4–T7), parallel fetch + per-company cap + 404 health (T2/T3), pipeline merge/write-back (T11), scheduler (T12), yaml-merge compat (T9 `merge_into_sources` + template entries T7). Backfill/digest behavior needs no code (fast runs send no digest).
- The profile **secret** does not need updating: `merge_into_sources` creates missing source entries dynamically, so the Sheet alone activates new ATSes in prod.
- `slug` is never lowercased (SmartRecruiters ids are case-sensitive); only the `ATS` column is normalized.
