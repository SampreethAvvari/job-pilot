# Company Watchlist — Design

**Date:** 2026-06-11
**Status:** Approved

## Problem

JobPilot polls 39 hand-picked companies via Greenhouse/Lever/Ashby board slugs that
live in `profile.yaml` (Secret Manager in prod). Scaling to ~200 companies needs:

1. A frictionless way to add/remove companies — no `gcloud secrets versions add`,
   no redeploys.
2. Coverage for companies on other ATS platforms (Workday, SmartRecruiters,
   Workable, Recruitee).
3. Visibility into dead boards (slugs 404 silently today).
4. A fix for the per-source cap, which truncates across *all* companies and would
   silently drop jobs at 200-company scale.

Filtering, scoring, dedup ("once shown, never again"), and scheduling already
exist and are unchanged.

## Solution overview

A `Companies` tab in the Dashboard Sheet is the managed watchlist. The user adds
a row (company name, optionally careers URL). Each pipeline run, a resolver
auto-detects the ATS for new rows and stores the slug; board sources then poll
every watchlist company through the ATS's public keyless JSON API on the existing
hourly schedule. Results flow through the unchanged
filter → dedup → score → Sheet → digest pipeline.

## Companies tab schema

| Column | Writer | Notes |
|---|---|---|
| Company | user | display name |
| Careers URL | user (optional) | required for Workday (tenant/site can't be guessed) |
| ATS | pipeline | `greenhouse` / `lever` / `ashby` / `workday` / `smartrecruiters` / `workable` / `recruitee`; manually overridable |
| Slug | pipeline | board identifier; Workday form: `tenant/wd5/site` |
| Status | pipeline | `pending` → `active` / `unsupported` / `error: 404 since <date>` |
| Last checked | pipeline | timestamp of last poll |
| Jobs (last fetch) | pipeline | matching-job count from the last poll |
| Notes | user | free text |

`profile.yaml` company lists keep working and are merged in (Sheet wins on
conflict) so migration is non-breaking.

## Resolver (`src/jobpilot/resolver.py`)

Runs at the start of each non-dry run, only on rows with blank/`pending` status.
Steps, stopping at first hit:

1. **URL pattern match** — `boards.greenhouse.io/{slug}`,
   `job-boards.greenhouse.io/{slug}`, `jobs.lever.co/{slug}`,
   `jobs.ashbyhq.com/{slug}`, `{tenant}.wd{n}.myworkdayjobs.com/{site}`,
   `careers.smartrecruiters.com/{Company}`, `apply.workable.com/{slug}`,
   `{slug}.recruitee.com`.
2. **Slug probing** — candidate slugs derived from the company name
   (`Scale AI` → `scaleai`, `scale-ai`, `scale`), probed against each ATS's
   public API. Workday excluded (not guessable).
3. **Page sniff** — fetch the careers URL once, look for ATS fingerprints in
   HTML (covers embedded boards).

No match → `unsupported` + note ("covered via Adzuna/LinkedIn sources").
Results written back in one batch. Resolver failures are never fatal.

## New source adapters

Each ~40–60 lines, modeled on `greenhouse.py`, registered in
`sources/__init__.py`, enabled via `profile.yaml`:

- **`workday.py`** — POST `…/wday/cxs/{tenant}/{site}/jobs`, paginated 20/page,
  capped at ~200 newest postings per company. Descriptions fetched from the
  detail endpoint **only for title-matched jobs**.
- **`smartrecruiters.py`** — GET
  `api.smartrecruiters.com/v1/companies/{id}/postings`; detail fetch for matched
  jobs only.
- **`workable.py`** — GET
  `apply.workable.com/api/v1/widget/accounts/{slug}?details=true`.
- **`recruitee.py`** — GET `{slug}.recruitee.com/api/offers/`.

## Pipeline wiring

- `companies.py` loads the tab once per run; `fetch_all` merges Sheet companies
  into each ATS source's `SourceCfg.companies`. Dry-run uses yaml lists only.
- **Parallel fetches**: `fetch_many()` helper in `sources/common.py` runs
  per-company requests on a 16-thread pool (200 companies ≈ 20 s, keeping Cloud
  Run inside free tier).
- **Cap fix**: per-company board sources use new `caps.per_company`
  (default 25 matched jobs per company per run) instead of truncating the
  combined list; aggregator sources keep `caps.per_source`.
- Per-company errors are caught, recorded in the tab Status column, and never
  kill a source or the run. 404s become `error: 404 since <date>` instead of a
  silent skip.

## Scheduling & rollout

No new scheduler. `jobpilot-hourly` container args gain the four new source
names. Dedup means only never-seen jobs cost Gemini tokens, so the 30-min
cadence stays near-free. Fast runs send no digest, so bulk-adding companies
backfills the Sheet quietly; the 7-day freshness window caps backfill volume.

## Cost (200 companies)

~$3–6/month incremental: Gemini scoring of new postings (~30–100/day) dominates;
ATS APIs are keyless/free; Cloud Run stays in free tier with parallel fetches;
one-time backfill ~$1–3.

## Testing

Fixture-based unit tests matching `tests/test_sources.py` (payloads recorded via
`scripts/record_fixtures.py`) for the four new adapters; resolver tests for URL
patterns and slug derivation. CI (ruff + pytest) unchanged.

## Out of scope

- Big-tech custom portals (Google/Meta/Amazon/Apple/Microsoft/Netflix) —
  `unsupported`; Adzuna/LinkedIn sources remain their coverage.
- Console UI page for the watchlist (Sheet tab chosen).
- Dedup semantics change (company+title key, BL-20: reposts stay hidden).
- Headless-browser scraping fallback.
