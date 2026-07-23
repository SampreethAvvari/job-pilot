# Console cards and freshness redesign

Date: 2026-07-23
Status: approved by owner (design review in session)
Scope: Python pipeline freshness and hygiene, single master resume base, full console UI rebuild as a light premium card system.

## 1. Problem

A live audit of the Dashboard Sheet (5,093 Jobs rows) plus a code trace found that fresh jobs are fetched reliably (22 to 58 rows added every day for the last two weeks, all recent additions posted within 7 days), but the console buries them:

1. Default sort is "Date found" (run date), not "Posted" (`ui/src/components/jobs-table.tsx:153`). A 50 day old posting fetched today lands on top.
2. Board sources may be up to 60 days old (`board_freshness_days=60`, `config.py:63`), so June postings keep entering as new.
3. Postings with no posted date skip the freshness gate entirely (`pipeline.py:106`), mainly Workday detail fetch failures, and sort to the top with a blank Posted cell.
4. Nothing prunes the Sheet and there is no minimum fit to write: 2,960 "New" rows are over 30 days old, 2,959 rows sit under fit 60. Every UI load fetches all of it.
5. Thresholds are inconsistent: pipeline 60, console gate 70, dashboard 60, and unscored jobs (fit null) bypass every fit filter.
6. Dedup memory is recomputed from the Jobs tab Title and Company columns (`sheets.py:165`), so deleting a row causes the pipeline to re add it on the next fetch. Any removal feature must preserve dedup memory.

## 2. Approved decisions

- Visibility window: a posting older than 14 days leaves the lists.
- Minimum fit: 75, enforced pipeline side and as the console default.
- Cleanup: stale and sub 75 rows move to a new Archive tab in the same Sheet. Dedup reads Jobs plus Archive, so nothing archived ever returns.
- Resume: one master AIE resume becomes the base for every tailored resume. The four variant bases retire.
- UI: light premium SaaS look, rich accents, card layouts on every tab, X to dismiss.
- Keep the Google Sheet as source of truth and keep the existing API routes and data layer.

## 3. Non goals

- No database migration, no auth changes, no new job sources.
- Assistant logic unchanged (theme restyle only).
- The public demo site and its repo are untouched.
- No light and dark toggle: the console ships light only.

## 4. Pipeline changes (src/jobpilot/)

### 4.1 Freshness gate (`pipeline.py`, `config.py`, sources)

- `board_freshness_days` drops from 60 to 14. `freshness_days` stays 7 for aggregators.
- `quality_filter` drops postings with no posted date: `if p.posted_at is None or p.posted_at < limit: continue`. Dropped counts are recorded in `RUN_STATS` (for example `dropped_undated`, `dropped_stale`) and appear in the run summary. This is self healing: an undated job never enters dedup memory, so a later run with a successful date fetch can still admit it.
- `greenhouse.py` uses `first_published` only; `updated_at` no longer masquerades as a posted date.
- `workday.py` keeps the detail fetch; on failure the posting stays undated and the gate drops it.

### 4.2 Write gate and Archive tab (`sheets.py`, `pipeline.py`)

- Scored jobs split at write time: fit >= 75 appends to Jobs; fit below 75 appends to Archive with Status `Low fit`. Archive has the same 28 headers.
- Unscored batches (scorer failure returns fit None) are not written at all; the jobs are retried on the next run because they never entered dedup memory.
- `known_ids` unions `Jobs!C2:D` and `Archive!C2:D`.
- `ensure_tabs` creates Archive when missing.
- Thresholds move to 75 in one place each: `scoring.threshold`, `tailoring.auto_threshold` (config defaults and the private profile), and the console (section 6).

### 4.3 Archiver sweep

A sweep function runs at the end of every full run (4 times daily) and behind a `--archive-sweep` CLI flag:

- Moves to Archive: rows with Status `New` or blank whose Posted is older than 14 days, blank, or whose Fit is below 75 or unparseable; all `Dismissed` rows; `Rejected` rows that have no Applied date and no Last reply (sponsorship auto rejects).
- Never touches: any row with an Applied date or a Last reply, or Status in Applied, Outreach sent, Response, Interview, Offer.
- Manual rows (Source `manual`) are exempt from the fit and undated rules while Status is `New`; they age out on the 14 day window using Date found.
- Move means append to Archive then delete from Jobs bottom up in one batch. The sweep verifies each row by Job ID immediately before deletion so a concurrent append cannot shift targets undetected.

### 4.4 One time migration and stats

- First `--archive-sweep` run migrates the current backlog (about 4,300 rows) so the Jobs tab is instantly lean.
- The Stats tab formulas are repaired (they currently show zeros) and updated to read the lean Jobs tab plus Archive for lifetime totals.

## 5. Resume: single AIE master

- The owner's master AIE resume (maintained outside this repo) is ported into `private/` with its preamble, replacing the AIE base; the FDE, MLE, and SDE bases retire. Secret Manager gets the new `RESUME_TEX_AIE` version; the retired secrets stay but are no longer read.
- `tailor.py` and `rebuild.py` always use the AIE base. The scorer keeps classifying role type (used for card badges and filters); it no longer selects a resume variant.
- Gate before shipping: the ported master compiles to one page with pdflatex and passes `scripts/ats_check.py` locally.
- The Resumes page becomes a single master card (download, ATS report, regenerate). The `RESUMES_JSON` and `RESUME_LINKS` service env vars shrink to one entry at deploy time.

## 6. Console UI (ui/)

### 6.1 Design system (globals.css rewrite)

- Light premium tokens, same family as the approved v3 mockup: background `#FBFBFD`, ink `#1D1D1F` with 72/55/36/10 percent tiers, white cards, primary blue `#0066CC`, accents emerald `#34D399`, violet `#A78BFA`, amber `#F5A524`, rose `#F43F5E`, soft layered shadows, radius 12 to 16 px.
- A real type scale (12/13/14/16/20/28) and spacing scale; buttons share one height scale. Fonts: Archivo for display, Inter for body, IBM Plex Mono for numbers and code accents.
- All color moves into tokens and utility classes; inline style color usage and hardcoded hex modal chrome are removed.

### 6.2 Shared primitives (new `ui/src/components/ui/`)

Button (primary, ghost, danger), Card, Modal (single portal implementation replacing the three copies), Badge and StatusPill, FitRing (score ring, emerald >= 85, blue >= 75, amber below), Skeleton, EmptyState, Toast (dismiss undo), FilterBar (segmented pills plus search).

### 6.3 Shared jobs store

One `JobsProvider` context with a single poller replaces the five independent `setInterval` pollers and the duplicated `pushUpdate` helpers. It exposes `jobs`, `mutate` (optimistic with revert), and busy sets for tailoring and drafting. No new dependencies.

### 6.4 Jobs tab (centerpiece)

- Responsive card grid (1/2/3 columns). Card contents: company and role title, FitRing, live posted age, location and remote badge, sponsorship signal, one line "why it fits", source tag.
- X in the card corner dismisses instantly (optimistic removal, undo toast for a few seconds, write is `Status: Dismissed`). Dismissed cards never reappear (section 4).
- Primary button Apply: opens the posting and on window refocus asks "did you apply?" (existing flow, restyled). Secondary actions: Tailor, ATS report, Draft outreach, Ask (chat drawer). Status changes via a compact menu.
- Defaults: fit >= 75 (the fit selector gains a 75 option), posted within 14 days, sorted by effective recency (Posted when present, Date found for manual rows). Unscored non manual rows no longer pass the fit filter.
- The dashboard "Top open matches" uses the same 75 gate (today it uses 60).

### 6.5 Other tabs

- Dashboard: stat tiles, a "fresh today" card rail, latest replies feed, all on the new primitives.
- Applied: card timeline sorted by applied date with status, reply, and docs at a glance.
- Companies: cards with health dot, newest job age (green within 24 h), remaining count; quiet companies stay collapsed; add and remove flows keep working.
- Replies: inbox style card list; the classification dropdown and its status walk back rules move over unchanged.
- Outreach: draft form plus draft cards (contact found, draft link, cover, status).
- Resumes: single master card (section 5).
- Assistant: inherits the light theme; chat logic untouched.

### 6.6 Shell and navigation

Sidebar stays on desktop; below `md` a bottom tab bar appears (today mobile has no navigation at all). Header keeps the refresh button and schedule note. Every page gets loading skeletons and a consistent error state instead of throwing.

## 7. Edge cases

- Legacy rows with unparseable fit (including mojibake values) count as unscored: migration archives them unless manual or applied.
- Manual adds stay visible while New (owner added them deliberately) and age out at 14 days.
- Dismiss undo writes Status back to `New`; after the sweep archives a dismissed row, undo is no longer offered (toast lifetime is seconds, sweep cadence is hours).
- Concurrent hourly append during a sweep: deletion targets are re verified by Job ID in the same batch window; appends land at the bottom and are never deletion targets.
- If the Archive tab is deleted by hand, `ensure_tabs` recreates it and dedup falls back to Jobs only until rows accumulate again.

## 8. Verification

- pytest: new tests for the undated drop, the 14 day board window, the 75 write split, sweep selection rules (including never touch rules and manual exemptions), and the two range `known_ids` union. Existing tests keep passing.
- Resume gate: pdflatex compile plus `ats_check.py` pass locally before any secret update.
- UI: production build and lint clean; click through checklist per tab on localhost against the live Sheet.
- Pipeline: local dry run plus one supervised `--fast` run before merging.

## 9. Rollout

1. All work lands on branch `redesign/console-cards-freshness`.
2. Owner reviews the console on localhost and the pipeline dry run output. Nothing is committed until this approval (standing rule).
3. After approval: commit, merge to master, auto deploy runs. Secret updates (profile thresholds, `RESUME_TEX_AIE`) and service env changes (`RESUMES_JSON`, `RESUME_LINKS`) run with an explicit owner go ahead.
4. One supervised `--archive-sweep` migration run, then verify the console and a scheduled run end to end.
