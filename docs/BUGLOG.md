# Bug log — every real issue this project hit, so nobody hits it twice

Format: **Symptom → Root cause → Fix → Guard now in place.**

### BL-01 · Resume PDFs unreadable by ATS parsers
- **Symptom:** keyword checker reported words missing that were visibly in the PDF; extraction showed `"New Y ork"`, `"T erraform"`.
- **Root cause:** XeTeX (tectonic) output with Type1 fonts produces a text layer that splits words at kerns — real ATS parsers see the same garbage.
- **Fix:** compile with **pdflatex + `\usepackage{cmap}`** (clean ToUnicode map).
- **Guard:** `scripts/ats_check.py` extracts text from the real PDF and fails under 85% keyword coverage.

### BL-02 · LaTeX "Undefined color 'RULE'"
- **Symptom:** first compile failed inside the section-title rule.
- **Root cause:** `\uppercase` (TeX primitive) in `\titleformat` swallowed the following optional-arg tokens, uppercasing the color name.
- **Fix:** `\MakeUppercase` placed as titlesec's explicit formatting command.

### BL-03 · Next.js build: googleapis bundled into the browser
- **Symptom:** `Module not found` cascade for `https-proxy-agent` etc. in client components.
- **Root cause:** client component imported types from a module that also imported `googleapis` (server-only).
- **Fix/Guard:** `ui/src/lib/types.ts` holds client-safe types/constants; server-only code stays in `jobs.ts`/`google.ts`.

### BL-04 · Next.js tried to prerender Sheet-backed pages at build time
- **Symptom:** `next build` failed: "No access, refresh token…" during static generation.
- **Root cause:** Next 16 statically prerenders pages whose dynamic data source it can't detect (googleapis isn't fetch()).
- **Fix:** `export const dynamic = "force-dynamic"` on every Sheet-reading page.

### BL-05 · ✨Tailor button ran the FULL pipeline instead of one job
- **Symptom:** button spun "tailoring…" forever; a 30-minute execution appeared.
- **Root cause:** Dockerfile used `CMD`; Cloud Run per-execution `args` overrides **replace** CMD, so the override either failed or was ignored.
- **Fix:** `ENTRYPOINT ["python","-m","jobpilot"]` — overrides now append as arguments.
- **Guard:** comment in Dockerfile; FORK-SETUP gotcha #2.

### BL-06 · LinkedIn source silently dead (403 every run)
- **Symptom:** almost no "posted ≤ 24h" jobs; digest run-notes showed `apify_linkedin: FAILED 403`.
- **Root cause:** the configured Apify actor (`bebity~…`) is **rental-only** — free accounts can't run it.
- **Fix:** switched to `curious_coder/linkedin-jobs-scraper` (pay-per-result, works on free credits); note its `count` minimum is 10. Filters (24h/full-time/entry) are baked into the LinkedIn search URLs.
- **Guard:** per-source status always lands in the digest's Run notes — read them when volume looks off.

### BL-07 · Pipeline killed at 20 minutes
- **Symptom:** execution terminated mid-tailoring; no digest sent.
- **Root cause:** LinkedIn scrape + 15-job tailoring exceeds Cloud Run's default-ish 20m task timeout.
- **Fix:** 45m task timeout (job + deploy.yml so CI doesn't revert it). Tailoring is idempotent — the next run finishes whatever was cut off.

### BL-08 · First CI deploy: PERMISSION_DENIED on Cloud Build
- **Symptom:** `caller does not have permission to act as service account <project-number>-compute@…`.
- **Root cause:** source deploys build via Cloud Build's default (compute) service account; the WIF deployer SA needs `iam.serviceAccountUser` **on that SA** too, not just on the runtime SAs.
- **Fix:** grant it once (FORK-SETUP step 7 includes it).

### BL-09 · OAuth consent captured the wrong Google account
- **Symptom:** pipeline acted as the work account; digest sent from the wrong address; later consents 403'd ("app not verified") for the intended account.
- **Root causes:** account chooser defaults + the intended account wasn't added as a **test user** on the OAuth consent screen.
- **Fix:** add the target account under Audience → Test users; redo consent; **verify identity** with a `gmail.users.getProfile` call before storing the token.
- **Guard:** FORK-SETUP step 3 calls this the #1 setup mistake.

### BL-10 · Sheet columns past Z broke updates
- **Symptom:** would-be writes to column 27+ computed garbage ranges.
- **Root cause:** `chr(65+idx)` / `String.fromCharCode(65+idx)` only works to Z.
- **Fix:** proper base-26 `col_letter()` in **both** Python and TypeScript (HEADERS are mirrored — change both, append-only).

### BL-11 · Test fixtures were invalid JSON
- **Symptom:** `json.JSONDecodeError: Unterminated string` loading recorded fixtures.
- **Root cause:** fixture recorder truncated the JSON **string** at 2MB.
- **Fix:** truncate structurally (keep first N jobs), never by slicing serialized text.

### BL-12 · "Engineer" matched "Engineering Manager"
- **Symptom:** manager/staff/770-day-old postings flooding results.
- **Root cause:** substring title matching; no posting-age window.
- **Fix:** word-boundary regex matching + `freshness_days` window + `exclude_title_words` list.

### BL-13 · Confirm-apply modal invisible (screen dims, no dialog)
- **Symptom:** overlay rendered; the centered card didn't.
- **Root cause:** `position: fixed` inside an ancestor with a CSS transform/animation — the fixed child positions against the ancestor, not the viewport.
- **Fix:** render the modal through `createPortal(document.body)` with inline styles.

### BL-14 · Vertex AI 429 RESOURCE_EXHAUSTED during tailoring bursts
- **Symptom:** one tailor in a batch fails with quota error.
- **Mitigation:** failures are per-job and non-fatal; the row keeps its ✨Tailor button; next run retries. If frequent, lower `tailoring.max_per_run`.

### BL-15 · Windows/PowerShell papercuts (dev environment)
- PS 5.1 mangles `sh -c '...'` quoting and `$f` in docker commands → use git-bash for docker/loops.
- `✓` in print() crashes under cp1252 → ASCII-only script output.
- gcloud on Windows prompts interactively mid-script (API enablement) → pre-enable `cloudresourcemanager.googleapis.com`; never rely on prompts in automation.
- Native-command stderr + `2>&1` in PS 5.1 wraps lines in error records → don't redirect; stderr is captured anyway.

### BL-16 · Resumes page rendered placeholder cards despite correct env vars
- **Symptom:** RESUMES_JSON verified present on the Cloud Run service, page still showed "Set RESUMES_JSON…".
- **Root cause:** the page had no dynamic marker, so Next.js statically prerendered it at build time — baking in the env-less placeholder state.
- **Fix:** `export const dynamic = "force-dynamic"` on every env- or data-driven page.
- **Guard:** check the build output table — data pages must show `ƒ (Dynamic)`, never `○ (Static)`.

### BL-17 · The first ATS checker was a golden retriever (fake 100s)
- **Symptom:** in-house checker scored resumes 100/100; ResumeWorded scored the same file 73.
- **Root cause:** keyword-coverage-only scoring measures none of what real graders weight: quantified bullets, 2-line brevity, weak verbs, buzzwords, soft-skill evidence.
- **Fix:** researched the actual rubric (published checks + documented score reports) and rebuilt `src/jobpilot/judge.py` as a weighted replica (impact 35 / brevity 20 / style 15 / sections 15 / soft skills 15). Calibration: new judge scored the old resumes 76-86 vs the real 73.
- **Guard:** never trust a self-built scorer without an external ground-truth comparison; keep feeding real grader reports back in as rules.

### BL-18 · The reply scanner never matched anything in production
- **Symptom:** recruiter replies sat in the inbox; rows never advanced; digest always said "no application replies".
- **Root cause:** `make_gemini_llm` baked `response_schema=_ScoreBatch` into every call, so the scanner's prompt (expecting `{"matches": ...}`) always got `{"scores": ...}` back; `_MatchBatch.model_validate_json` failed and `classify()` silently returned `[]` — the catch-all that "must never break the run" also never told anyone.
- **Fix:** `make_gemini_llm(cfg, schema=...)` — schema is per call site; the scanner's replacement (`inboxwatch.py`) passes its own `FindingBatch`.
- **Guard:** a shared LLM wrapper with a baked-in response schema silently breaks every other caller — when a "degrade, never raise" path returns empty, make sure the empty case is distinguishable from "nothing to do" (the InboxWatch tab now logs every judged message).

### BL-19 · Inbox watch alerted twice on Ford OTP emails
- **Symptom:** two "🎯 Ford Motor responded" alerts; both were "Confirm your identity" one-time-passcode emails, not real next steps.
- **Root cause:** two distinct Gmail messages (per-message dedup worked correctly), but the classifier prompt had no rule for transactional identity/OTP mail — "Confirm your identity for job X" pattern-matched "real progression", so each message alerted.
- **Fix:** (1) prompt now states verification/OTP/password emails are automated_ack, NEVER next_step; (2) deterministic guard `is_verification()` downgrades any next_step whose subject/body matches OTP patterns before alerting — belt and braces over the LLM.
- **Guard (related window):** `watch()` now appends the InboxWatch dedup log *before* the Jobs-sheet update; previously a transient `update_cells` failure skipped the log append and every alerted message would re-alert the next run.

### BL-20 · Same job appeared again and again in the Jobs tab
- **Symptom:** Oracle "Software Developer 4" ×5 rows, Deloitte "Agentic AI Engineer" ×4, … (23 duplicate groups of 426 rows).
- **Root cause:** the dedup key hashed company+title+**location**, and boards list one role per metro (Adzuna county-level spellings, LinkedIn per-city reposts) — every location variant hashed to a "new" job. Zero exact-id duplicates: the mechanism worked; the key was wrong.
- **Fix:** `dedup.key()` is company+title only; in-batch collapse keeps the highest-fidelity source. `sheets.known_ids()` now **recomputes** keys from the Title+Company columns instead of reading the stored Job ID column — old rows carry location-based ids that would never match the new scheme and everything would have been re-added once.
- **Trade-off (accepted):** genuinely distinct same-title reqs in different cities collapse to one row; for an apply-once dashboard that is the right granularity.
