# Auto-apply design

Date: 2026-07-24
Status: approved for planning

## Goal

Add background automated job application to JobPilot. From the console the user clicks
**Auto apply** on a job. A worker fills the whole application (contact info, resume,
cover letter, education, experience, screening questions), captures a screenshot per
question, and either parks it for review or submits, based on one toggle. Workday is
supported with account creation and Gmail OTP retrieval. The user's existing pipeline,
Sheet, Secret Manager, Vertex, and Gmail tokens are reused; nothing personal enters the
public repo.

## The user experience

Every job card gets an **Auto apply** button. Settings has one toggle, **Leave for
review** (default ON).

- **Review ON:** clicking Auto apply fills the entire application in the background,
  then the application appears in a new **Applications** console tab showing every
  question, the answer that will be submitted, and a screenshot per question. The user
  can edit any answer inline, then click **Approve and submit**. The worker replays the
  fill with the final answers and submits.
- **Review OFF:** clicking Auto apply fills and submits in one pass, no stop. (Unlocked
  last, after the user trusts the answer quality.)

Multiple jobs can be started back to back; each runs as its own isolated browser
session. Concurrency is capped (default 4 simultaneous fills). Workday is one
application at a time per tenant.

The existing hard rule "never auto-submit applications" is **revised** by this spec: the
user may opt into unattended submit via the toggle. Truthfulness rules below are NOT
relaxed in any mode.

## Architecture

New Cloud Run **job** `jobpilot-apply` in project `jobpilot-sva` (us-central1), same
repo, built on the Playwright Python base image (the main pipeline container stays
slim; this is a separate image/target). The console triggers it with container-arg
overrides exactly like tailoring triggers `jobpilot` today. The triggering identity
(UI service account) needs `run.developer` on the new job, not just invoker (the
BL-21/BL-22 lesson).

New module family `src/jobpilot/apply/`:

- `engine.py` — orchestrator; runs the two phases; selects adapter by ATS; enforces
  caps, idempotency, truthfulness gate.
- `adapters/` — one module per ATS: `greenhouse.py`, `lever.py`, `ashby.py`,
  `smartrecruiters.py`, `workable.py`, `recruitee.py`, `workday.py`. Greenhouse and
  Lever also expose a no-browser direct-POST fast path; the rest drive headless
  Chromium. Each adapter implements a common interface: `fill(page, plan, profile)`,
  `submit(page, plan)`, `verify_success(page) -> bool`.
- `answers.py` — AI answer engine (cover letter + screening questions only).
- `plan.py` — the ApplicationPlan data model (questions, answers, evidence, status).
- `profile.py` — loads the locked application profile; picks NY vs Bay Area; exposes
  a locked-field map the engine writes verbatim.
- `otp.py` — Gmail OTP fetch (reuses inbox tokens).
- `accounts.py` — Workday per-tenant credential store (Secret Manager).
- `evidence.py` — screenshots + Drive upload + plan.json.

### Two-phase execution (why)

A browser cannot sit open in Cloud Run waiting hours for the user to approve. So:

- **Phase 1 `--apply-fill <job id>`:** open browser, fill everything, screenshot each
  question, draft answers, save the ApplicationPlan (status `needs_review`), close
  browser. Never submits.
- **Phase 2 `--apply-submit <job id>`:** open a fresh browser, replay the fill from the
  approved plan verbatim, submit, and verify a success signal before marking Applied.

With review OFF, the engine chains phase 2 immediately after phase 1 in the same run.
With review ON, phase 2 is a separate `jobpilot-apply` execution triggered by the
**Approve and submit** button.

## What gets filled, and the locked-vs-AI split

**No resume tailoring.** The base AIE resume PDF is attached as-is. AI is used ONLY for
the cover letter and application-specific screening questions.

**Locked fields (verbatim, AI never touches, always overwrite ATS resume-autofill):**
name, email, phone, address, links, work authorization, sponsorship, EEO answers,
education, experience, compensation/logistics. After any ATS resume-parse autofill step,
the engine re-writes every locked field from the profile so bad parsing can never
degrade the application. Source of truth: the `application:` block in the private
profile (staged in `private/application_profile_draft.yaml`, to be merged into the
private profile + Secret Manager). Personal data never enters the public repo.

**Location switch:** default NY profile (NY address + `..._reallinks.pdf`). If the job
location matches any Bay Area trigger token (san francisco, sf, bay area, sunnyvale,
san jose, palo alto, mountain view, menlo park, cupertino, santa clara, redwood city,
oakland, berkeley, south san francisco, san mateo, foster city), switch to the Sunnyvale
address + `..._reallinks_sunnyvale.pdf`. Triggers are editable in the profile.

**Cover letter (AI):** generated per job from the JD + knowledge pack + resume facts, in
the user's voice. **Always rendered to PDF** (reuse `latexpdf`/tailor rendering) and
stored in the evidence folder for every application. Attached as the PDF when the form
has a file field; when the form only offers a text box, a plain-text version is pasted
AND the PDF is still saved to evidence.

**Length-aware answers (graceful, never abrupt):** before writing any answer or cover
letter, the engine reads the field's real limit from the DOM (`maxlength`, or a stated
word/character cap in the question text). The AI is told the limit up front and writes a
complete, self-contained answer that fits inside it, rather than writing long and hard-
truncating. If a JD or context is too long to fit, the AI summarizes it down gracefully
(preserving the key point) instead of pasting whatever fits and cutting mid-sentence.
A hard-truncate is a last-resort fallback only, and if it ever triggers the answer is
flagged in the plan for review.

**Screening questions (AI):** answered by Gemini grounded in the knowledge pack, resume,
the JD, and the profile's `skills`/`projects`/`portfolio_links` blocks. When an answer
wants a work sample or link, the engine cites a REAL portfolio link (case study, demo,
or GitHub) from the profile and never invents a URL. Each question + drafted answer +
screenshot recorded in the plan.

### Answer style contract (prompt + post-filter)

Persona: confident but not all-knowing or perfect; hardworking, fast-shipping, quick to
learn, takes on any challenge, solves real business use cases, has character. Sells the
engineer who ships and figures things out, not someone who claims to know everything.

Rules, enforced in the prompt and by a deterministic post-filter (reuse the assistant's
dash sanitizer): first person; natural spoken language, not stiff written prose;
succinct; honest, concessions allowed ("I haven't used X in production, but..."); no
AI-tell vocabulary; no em or en dashes.

**Every question answered on its own merits.** Each screening question is handled
individually (its own prompt with that question's field limit), directly answers what
was asked, and reads cleanly. No boilerplate reused across questions, no answer that
dodges the actual question.

### Truthfulness gate (all modes, including full-auto)

- Work authorization and sponsorship answered truthfully from the profile, always.
- Numbers (years of experience, GPA, dates, salary) only from the profile; salary uses
  the JD range if the JD states one, else the fallback 130000-140000, preferring the
  "open to negotiation" text when free-text is allowed.
- EEO answers used verbatim.
- If a REQUIRED question cannot be answered from the profile or knowledge pack, the
  engine does NOT guess. Even with review OFF, that application parks in the queue with
  the question flagged (status `needs_input`).

## Workday (safety measures)

- **Account per tenant:** created with the applications email (from the private profile)
  + a generated strong password,
  stored in Secret Manager `JOBPILOT_WORKDAY_ACCOUNTS` (tenant → {email, password}).
  Reused on later applications to the same tenant.
- **OTP:** pulled via existing Gmail tokens, matched on recipient address + tenant
  sender domain + code pattern + tight recency window, so another company's code can
  never be used.
- **Pacing:** one application at a time per tenant; human-pace typing; no aggressive
  retries. A lockout or CAPTCHA sets status `manual_required` / `captcha_blocked`
  instead of retrying into a flag.
- **Checkpointing:** wizard progress is saved so a phase-1 that dies mid-wizard resumes
  rather than recreating the account.

## Failure handling and local fallback

New Sheet tab **`Applications`** is the state machine. Statuses: `queued`, `filling`,
`needs_review`, `needs_input`, `approved`, `submitting`, `submitted`, `failed`,
`captcha_blocked`, `manual_required`, `check_email`. Idempotency comes from transitions:
a job in `filling` cannot be started twice; a submit that cannot verify success goes to
`check_email`, never auto-retried.

**Local fallback (Simplify-style, fallback only):** when a run hits CAPTCHA or an IP
block, the Applications card shows **Run in my browser**. `scripts/apply_local.py` is a
small script the user runs on their own machine: it opens a real visible Chromium tab,
loads the saved plan, fills it in front of them, the user clears the CAPTCHA, and it
finishes. No always-on local helper; run only when the queue asks.

**Daily submit cap** (default 25) prevents accidental mass-apply patterns that get
candidates soft-banned.

## Evidence trail

Per application, Drive folder `JobPilot Applications/<Company> - <Title>/`: one
timestamped screenshot per question, the final review page, the confirmation page, the
cover letter PDF, and `plan.json` (every question, the answer submitted, its timestamp).
The Applications tab renders all of it. On verified success the job's Sheet row flips to
Applied with the date, feeding the existing reply-watch flow.

## Portfolio knowledge graph (grounds the answer engine)

Auto-apply answers and cover letters are only as good as what the engine knows about the
user's work. Today `knowledge.py:portfolio_section` just fetches the homepage and strips
it to 6000 chars, which is shallow. This feature replaces that with a real crawl that
builds a project knowledge graph and feeds a much richer pack.

**Approach: graph built, pack consumed.** The crawler builds a true graph (JSON + a
viewable visual map), then flattens the relevant parts into the Knowledge pack the
answer engine and Assistant already read. Grounding stays on the proven pack path; the
graph adds connected reasoning and a map the user can look at.

### Crawl

New module `src/jobpilot/portfolio_graph.py`. Starting from `cfg.profile.portfolio`, it
discovers and fetches every portfolio page: projects index, each project, the work page,
and every blog case study (`/posts/*`). It reuses the polite `httpx` client + `strip_html`
already in `knowledge.py` (JobPilot User-Agent, redirects, per-page failure isolation so
one dead page never blocks the rest). Link discovery is scoped to the portfolio host only.

### Extraction → graph

Each page is passed to Gemini with a JSON-schema contract (same pattern as the scorer)
that extracts structured facts per project: name, one-line, problem, approach, stack /
technologies, metrics/outcomes, role, dates, company, and the real links (case study,
demo, repo). These become graph **nodes** (project, skill, technology, company, outcome)
and **edges** (`used-tech`, `solved-problem`, `built-at`, `achieved`, `links-to`).

### Storage

- **Graph JSON** stored in a new Sheet tab `PortfolioGraph` (nodes + edges + source URL +
  crawl timestamp), the same "Sheet is the store" pattern used everywhere else. Optional
  visual HTML map generated via the graphify tooling and saved to Drive
  (`JobPilot Applications/_portfolio_graph.html`) for the user to open.
- **Flattened pack:** `portfolio_section` is rewritten to render the graph into rich,
  per-project Knowledge-pack text (problem, stack, metrics, links) instead of raw stripped
  HTML. The answer engine and Assistant consume it with zero changes on their side.

### Retrieval

When answering a question, the engine selects the relevant subgraph (projects/skills
matching the JD and question) and injects those project facts + real links as grounding.
This is what lets "tell us about a time you shipped X" cite the right project with its
actual metrics and a real link.

**Hero projects preference.** The profile defines a ranked `hero_projects` list, each
with the angle it sells best (Doctor Coach and NPC Coach as two distinct LLM-eval
projects, CDF for agentic multimodal, Enterprise Search for RAG / AI-Engineer roles,
CBCT Scan Validator for money saved / $98K replaced, Reconciliation for simple-yet-
effective wins that break bad practices). When a question invites a work example, the
engine prefers a hero project whose angle matches the role, before reaching for others.

### Trigger & refresh

- **Console button** on a new **Knowledge** page (or Assistant page) → `api/portfolio-graph`
  route triggers a background `jobpilot` run with `--rebuild-portfolio-graph`. Progress/last-
  built shown in the UI.
- **Auto-refresh:** runs in the daily full pipeline (alongside `--refresh-knowledge`) and
  can be nudged after portfolio publishes. Weekly is the floor; the button is for on-demand.
- CLI flag `--rebuild-portfolio-graph` (mirrors `--refresh-knowledge`).

### Honesty guard

The graph is built only from the user's own published portfolio and GitHub. Extraction may
not invent metrics or facts not present on the page (schema + prompt rule). The answer
engine still only cites REAL links from the graph, never fabricated ones.

## Config additions

`profile.yaml` gains an `apply` block:

```yaml
apply:
  enabled: true
  leave_for_review: true      # the toggle default; UI can flip per-session
  max_concurrent: 4
  daily_submit_cap: 25
  # locked application profile lives under application: (private only)
```

Plus the `application:` block (private/Secret Manager only) already drafted in
`private/application_profile_draft.yaml`.

## CLI surface (mirrors existing single-job flags)

- `--apply-fill <job id>` — phase 1
- `--apply-submit <job id>` — phase 2
- `--apply <job id>` — fill then submit (review-off path)
- `--rebuild-portfolio-graph` — crawl portfolio, rebuild graph + pack

## UI additions

- `Auto apply` button on each job card (calls a new `api/apply` route → triggers
  `jobpilot-apply --apply-fill`, or `--apply` when review is off).
- **Applications** tab/view: cards per application with status, per-question
  screenshots + answers (inline editable), Approve-and-submit, Run-in-my-browser.
- Settings: **Leave for review** toggle.
- Provider: extend the shared `JobsProvider` store or add a sibling `ApplicationsProvider`
  polling the Applications tab.

## Rollout order

1. Portfolio knowledge graph (crawl → graph → richer pack) + Knowledge page button.
   This grounds every answer, so it comes first.
2. Application profile loader + answer engine + Applications tab & queue UI + evidence.
3. Greenhouse & Lever (direct POST), then Ashby, SmartRecruiters, Workable, Recruitee
   headless adapters.
4. Workday adapter (accounts, OTP, wizard, checkpointing).
5. Local fallback script.
6. Full-auto (review OFF) toggle unlocked, after enough reviewed plans build trust.

## Risks (acknowledged)

- **Datacenter IP reputation:** Cloud Run egress is datacenter IP; a minority of tenants
  (mostly Workday behind Akamai) may CAPTCHA or 403 form submits. These fail cleanly to
  `captcha_blocked`/`manual_required` → local fallback.
- **Headless fingerprinting:** mitigated with standard stealth config; simple ATSes
  barely check.
- **Bad AI answers in full-auto:** mitigated by staying in review mode until trusted,
  and by the truthfulness gate parking unanswerable required questions.
- **Half/duplicate submits:** mitigated by status-transition idempotency and
  verify-success-before-Applied.
- **Form drift:** adapters verify a success signal; breakage shows as failures, never
  false Applied.
- **ToS:** automating submissions violates some sites' terms; blast radius is a
  per-site block, acceptable for a personal job hunt, named here for honesty.

## Out of scope (v1)

- Resume tailoring per job (explicitly dropped; base resume only).
- Big-tech custom portals (Google/Meta/Amazon careers) — unsupported, same as pipeline.
- Auto-triggering apply on new jobs without a click (user clicks Auto apply per job).
