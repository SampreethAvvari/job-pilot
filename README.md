# JobPilot ✈️

**Your personal job-hunt autopilot.** Every hour it finds fresh postings across seven
sources, filters out everything you'd never apply to, AI-scores what's left against
*your* profile, tailors a one-page ATS-clean resume and cover letter per match, finds
recruiter contacts and drafts the outreach email — then hands you a sleek console where
you review, click Apply, and track everything to offer.

It never sends anything on its own. You stay the pilot; it does the paperwork.

> Fork it and run your own for ~$0–10/month: **[docs/FORK-SETUP.md](docs/FORK-SETUP.md)**
> is a complete blueprint written to be handed to an AI coding agent.

## What a day looks like

- **Hourly**, fresh jobs from the free sources appear in your console — and every
  watched inbox (yours + any extra Gmail accounts) is checked for recruiter replies.
  A genuine next step (interview invite, scheduling request, online assessment)
  triggers an **instant alert email** telling you which company responded in which
  inbox, with a link to the exact message. Rejections quietly update your tracker;
  "thanks for applying" autoresponders are ignored.
- **Four times a day**, a full run adds LinkedIn, tailors resumes + cover letters for
  every job scoring ≥ 60, drafts recruiter outreach for anything you applied to, and
  emails you a digest.
- **You** open the console, sort by *recently posted*, run down your best role category,
  click **Apply ↗** with the right tailored PDF one click away, and confirm when you're
  back. Irrelevant job? **✕** and it's gone forever.

## The machinery

```
                    Cloud Scheduler ──── hourly fast-fetch · 4x/day full run
                          │
                          ▼
   ┌─ Cloud Run Job (Python 3.12) ─────────────────────────────────────────┐
   │ fetch: Greenhouse · Lever · Ashby · Workday · SmartRecruiters ·        │
   │        Workable · Recruitee · RemoteOK · HN hiring · Adzuna ·          │
   │        LinkedIn (Apify) — company boards via the Companies sheet tab   │
   │ filter: freshness · seniority words · citizenship/clearance/           │
   │         no-sponsorship regex wall (dropped before any compute)         │
   │ score:  Vertex AI Gemini, JSON-schema contract — fit 0-100, why,       │
   │         sponsorship signal, role category, best resume variant         │
   │ tailor: per-job resume + cover letter → pdflatex → one-page PDF →      │
   │         Drive (truth guardrails: may rephrase, can never invent)       │
   │ reach:  company outreach — find a PUBLISHED careers email (website ·   │
   │         job text · web search) → cold email + resume + cover letter    │
   │         as a Gmail DRAFT, recorded per company (NOTHING auto-sent)     │
   │ watch:  every inbox judged for REAL next-steps → instant alert email · │
   │         status auto-advances (rejections too) · InboxWatch audit tab   │
   │ record: Google Sheet = database AND human-readable dashboard           │
   └────────────────────────────────────────────────────────────────────────┘
                          ▲  trigger · read · write
   Cloud Run Service — Next.js 16 console behind IAP (Google sign-in)
   jobs · filters (role/posted/fit/source) · apply-confirm flow · applied (n)
   tab · resume armory · reply feed · Outreach tab · per-job copilot chat ·
   ✨tailor & ✉draft buttons per job
```

## The copilot

Every job row has a **💬** that opens its own chat drawer, grounded in a knowledge
pack (your GitHub, portfolio, resumes, and profile) plus the job's description
fetched live when you open it, so answers are specific to *that* role and *your*
background. Attach a PDF or image (a JD screenshot, a recruiter's note) straight
into the conversation; nothing is persisted client-side. The same guardrailed
Vertex chat powers a manual-job tailor flow for the role a friend forwards that no
board ever surfaced. A `us_only` location wall runs upstream in the pipeline too,
so non-US postings never reach the Sheet in the first place.

## Cold outreach (the Outreach tab)

Type a company. JobPilot picks your best-fit resume of four (AIE / FDE / MLE / SDE,
overridable), writes a short plain-English cold email (no buzzwords, no em dashes,
2-minute read), generates a tailored one-page cover letter, finds a **published**
careers email — **never guessed**, scraped from the company's own site, then any
email printed in the job post, then a web search — and drops it all as a **Gmail
draft you review and send**. Every careers email found is recorded per company on
the Sheet's **Outreach** tab. You can draft one company at a time, or **batch the
freshest real-hiring companies** (direct ATS boards only, deduped, entry-level US
AIE/FDE) in one click. Optional API keys widen reach: **Hunter.io** (free tier,
verified named contacts) and **Serper.dev** (free tier, web-search email lookup) —
both degrade gracefully when absent. Nothing is ever sent automatically.

## Tech stack, and why each piece

| Layer | Choice | Why |
|---|---|---|
| Pipeline | **Python 3.12**, `httpx`, `pydantic` | Plug-in sources behind one `Posting` model; every LLM response validated against a schema with retry |
| LLM | **Vertex AI Gemini Flash** | No API key (service-account auth), structured output, pennies per run; falls back to AI Studio key |
| Database | **Google Sheets** | The DB *is* the dashboard — filters, audit trail, manual overrides for free; at job-hunt scale a real DB is overkill |
| Resume engine | **LaTeX + pdflatex + `cmap`** | The only reliably ATS-parseable PDF text layer we found (XeTeX output splits words like "New Y ork" in parsers) |
| Resume judge | **Calibrated ResumeWorded-replica** (`src/jobpilot/judge.py`) | ~40 deterministic checks weighted impact 35 / brevity 20 / style 15 / sections 15 / soft-skills 15; every resume (master or tailored) goes through a judge-guided rewrite loop — up to 10 attempts, best wins, improvements only — and ships with its full ATS report in the console |
| Console | **Next.js 16** (App Router) on Cloud Run + **IAP** | Zero-auth-code private app: Google sign-in and allowlisting handled entirely by infrastructure |
| Copilot | **Guardrailed Vertex chat** | Per-job drawer grounded in a knowledge pack + the live JD; PDF/image attachments; model keys stay server-side |
| Identity | **User OAuth refresh token** in Secret Manager | The pipeline acts as *you* — your Sheet, your Gmail drafts, your Drive — with four narrow scopes (see FORK-SETUP) |
| Personal data | **Env/Secret-Manager overrides** | Profile and resumes load from `JOBPILOT_PROFILE_YAML` / `RESUME_TEX_*` env; the repo ships Jane Doe templates only |
| CI/CD | **GitHub Actions + Workload Identity Federation** | Push to master → path-filtered deploys, no stored cloud keys anywhere; lint+tests run secret-free on every PR |
| Schedule | **Cloud Scheduler** | Hourly fast-fetch (free sources), 4x/day full runs (LinkedIn + tailoring + digest) |

## Design rules

1. **Nothing outbound is ever automatic.** Emails are drafts; applications are clicks.
2. **The tailor cannot lie.** It may reorder, rephrase, and re-emphasize the master
   resume — inventing employers, dates, or metrics is structurally out of bounds.
3. **Sources fail independently.** One broken API never kills a run; per-source status
   lands in the digest's run notes.
4. **Personal data lives in Secret Manager, not git.** This repo contains no secrets,
   no real resumes, no identity — verified across the entire history.

## Company watchlist

Add rows to the **Companies** tab of the dashboard Sheet (created automatically):
just a company name, plus its careers URL if you have it (required for Workday).
Within one scheduled run the pipeline detects the company's ATS
(Greenhouse / Lever / Ashby / Workday / SmartRecruiters / Workable / Recruitee),
fills in the board slug, and starts polling its public job-board API. The
`Status`, `Last checked`, and `Jobs (last fetch)` columns show each board's
health; companies on unsupported ATSes are marked `unsupported` and remain
covered by the aggregator sources.

## Setting it up — where everything is explained

| You want to… | Go to |
|---|---|
| **Clone and try it locally in a few minutes (no cloud, no keys)** | **[QUICKSTART.md](QUICKSTART.md)** |
| Create the GCP project, billing, APIs, service accounts | [FORK-SETUP §1–2](docs/FORK-SETUP.md#step-1--gcp-project) |
| Grant Gmail/Sheets/Drive permissions (and understand exactly what each scope can do — drafts-only email, never auto-send) | [FORK-SETUP §3 + Appendix A](docs/FORK-SETUP.md#appendix-a--google-permissions-exactly-what-you-grant-and-why) |
| Get the digest job emails 4×/day + hourly fresh jobs | [FORK-SETUP §6 (schedules)](docs/FORK-SETUP.md#step-6--schedules) |
| Set up Apollo recruiter lookup + Gmail outreach drafts | [FORK-SETUP Appendix B → Outreach](docs/FORK-SETUP.md#appendix-b--feature-catalog-what-each-part-does--where-its-configured) |
| Understand every feature and its config knob | [FORK-SETUP Appendix B](docs/FORK-SETUP.md#appendix-b--feature-catalog-what-each-part-does--where-its-configured) |
| Add your own resume variants + run the ATS validator on them | [FORK-SETUP Appendix C](docs/FORK-SETUP.md#appendix-c--the-resume-system-blueprint-bring-your-own-variants) |
| Avoid every bug we already hit | [docs/BUGLOG.md](docs/BUGLOG.md) |
| Contribute a feature upstream | [CONTRIBUTING.md](CONTRIBUTING.md) |

## Run it

```bash
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"
.venv/Scripts/python -m pytest -q                      # 130+ tests
.venv/Scripts/python -m jobpilot --dry-run             # live fetch, zero credentials
.venv/Scripts/python -m jobpilot --dry-run --sources greenhouse,ashby
```

Full deployment (GCP project, OAuth, secrets, schedulers, console, CI):
**[docs/FORK-SETUP.md](docs/FORK-SETUP.md)**.

## Contributing

PRs welcome — new sources, smarter filters, console UX. See
[CONTRIBUTING.md](CONTRIBUTING.md). MIT licensed.
