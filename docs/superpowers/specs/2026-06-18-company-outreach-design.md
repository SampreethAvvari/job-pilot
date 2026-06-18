# Company Outreach — design

## Problem

The existing outreach is job-row-centric: it drafts one email per *applied job* and
relies on Apollo returning a recruiter with a verified email. On the **free Apollo
plan** Apollo returns nothing usable, so that path almost never produces a draft.

The user wants a **company-centric** flow: type a company, get a polished cold-email
draft (tailored resume + cover letter attached) without needing a verified email up
front, with all drafts **pooled by company in Gmail**, plus the means to find the
right people and addresses manually and send one by one.

## Reality constraints (drive the design)

- **Free Apollo** → assume no verified emails. People discovery is best-effort; the
  real recipient is resolved by the human.
- **OAuth scope is `gmail.compose` only** (no `gmail.labels`/`gmail.modify`). Pooling
  is therefore by **subject prefix** `[JobPilot · <Company>]` (Gmail-searchable),
  never by label. No re-consent required.
- **`pdflatex`** is present in the deployed Cloud Run image, absent on the dev laptop.
  Cover-letter compilation must degrade gracefully (draft still created, note added).
- **Nothing is ever sent.** Drafts only — matches the project's first design rule.

## Components

### Python — `src/jobpilot/company_outreach.py`
- `find_people_links(company)` — deterministic LinkedIn / Apollo / Google
  people-search URLs per target role (recruiter, technical recruiter, talent
  acquisition, hiring manager, engineering manager). Free-plan safe; no API call.
- `apollo_people(company, client)` — best-effort Apollo names/titles (reuses
  `apollo.find_contacts` semantics); empty on the free plan, never fatal.
- `company_domain(company, creds, sid)` — domain from the Companies-tab Careers URL
  when the company is on the watchlist, else a `<slug>.com` heuristic (flagged
  unverified). Feeds generic role-inbox guesses (`careers@`, `recruiting@`,
  `talent@`, `jobs@`).
- `pick_variant(company, cfg, llm)` — Gemini chooses one of AIE/FDE/MLE/SDE and a
  one-line reason; a UI dropdown overrides it.
- `cover_letter_pdf(company, variant, cfg, llm)` — LLM returns escaped plain-text
  paragraphs (JSON), wrapped in a known-good LaTeX skeleton (`\input{_preamble}`)
  and compiled via `latexpdf.compile_pdf`. Truth-guarded: grounded only in
  `profile.summary`; never invents facts. Degrades to no-attachment + note.
- `draft_company_email(company, variant, contact_name, cfg, llm)` — body via
  `prompts/company_outreach_v1.txt`.
- `sanitize_text(s)` — **deterministic guarantee**: removes em/en dashes and
  hyphen-as-dash (` - `, ` -- `); keeps intra-word hyphens (`end-to-end`).
- `run(creds, sid, company, variant, cfg, llm, client, now)` — orchestrates the
  above, builds the Gmail draft (resume + cover letter attached, subject prefix,
  To left blank for the human to fill), writes a row to the **Outreach** Sheet tab,
  returns a status note. Every external call degrades independently.

### Email rules (enforced)
Plain, simple English; under ~150 words / 2-minute read; who I am; AI-engineering +
software-development experience; a succinct pitch covering FDE/AIE/MLE; 1–2
high-level project highlights with links; portfolio + LinkedIn; states resume +
cover letter attached; soft ask for a short chat. Banned AI-tell phrases listed in
the prompt; **no em/en dashes** guaranteed by the sanitizer. Deterministic signature
(name + portfolio + LinkedIn + GitHub) appended by the existing `signature()`.

### Draft assembly — `src/jobpilot/outreach.py`
`create_gmail_draft` extended to accept `attachments: list[(name, bytes)]`
(back-compatible with the single `attachment=` kwarg) so resume **and** cover letter
attach together.

### Sheet — new **Outreach** tab
`Searched at, Company, Domain, Resume variant, Variant reason, Subject,
Guessed emails, Draft, Resume, Cover letter, Status, Notes`. Created idempotently
(mirrors `ensure_companies_tab`).

### CLI — `__main__.py`
`--company-outreach "<Company>" [--variant AIE]`. Works locally (instant draft in
your Gmail) and as the Cloud Run job the console triggers.

### UI — new **Outreach** tab
- `nav.tsx` entry (✉).
- `app/outreach/page.tsx` (server) reads the Outreach tab via `lib/outreach.ts`.
- `components/outreach-console.tsx` (client): company input + variant dropdown →
  POST `/api/company-outreach` → triggers the job; renders existing results pooled
  by company with the Gmail draft link, deterministic find-people links, guessed
  inboxes, and status.
- `api/company-outreach/route.ts` + `run.ts#triggerCompanyOutreach`.

### Resume relink — `scripts/relink_resumes.py`
Idempotently uploads the four master PDFs to Drive (`JobPilot Resumes/Masters`),
prints new file ids + a ready `RESUMES_JSON`. Updates `private/profile.yaml`
`masters.pdf_ids` (used by the resume attachment) and the UI `RESUMES_JSON` (the
Resumes tab + `/api/resume/[variant]`). Fixes the dangling links left when the old
Drive files were deleted.

## Non-goals
- No verified-email scraping (free plan). No auto-send. No per-persona draft
  multiplication (one draft per company; the human sets the recipient).

## Testing (basic, per request)
Unit tests with mocked Gmail/Drive/LLM/compile: sanitizer (dash removal), variant
picker, find-people links, draft assembly with two attachments, graceful degrade
when `pdflatex`/Drive are absent. Nothing is ever sent.
