# Inbox Watch — multi-account reply detection with real-time alerts

**Date:** 2026-06-10
**Status:** Approved

## Problem

JobPilot's reply scanner watches one inbox (the runtime identity), only matches
emails to applications already tracked in the Sheet, and reports findings
silently in the digest. The user applies to jobs from three email addresses and
wants to know — within the hour — when a company sends a *genuine* next-step
response (interview invite, scheduling request, online assessment, document
request), as opposed to an automated "thanks for applying" acknowledgment or a
rejection. The signal arrives as an alert email: "check this inbox, this
company responded."

## Decisions (from brainstorming)

- **Inboxes:** the primary runtime account plus two extra Gmail accounts
  (all three are Google accounts; real addresses live in Secret Manager /
  private config, never in the repo).
- **Scope:** judge ALL inbox mail, not just tracked applications — manual
  applications outside JobPilot must be caught too.
- **Cadence:** hourly. The existing `jobpilot-hourly` Cloud Scheduler trigger
  already runs the job every hour with `--fast`; inbox watch joins that run.
  No new scheduler.
- **Alerts:** immediate, one email per finding, sent from the primary account
  to the digest recipient. Self-notification only — the "never auto-send
  email" rule (about recruiters/companies) is untouched.
- **OA invites count as next steps** (they are progression, even if automated).

## Architecture

One new module, `src/jobpilot/inboxwatch.py`, supersedes `scanner.py` (which
is deleted; its forward-only status logic and tests move over). It runs in
both the hourly `--fast` runs and the 4x/day full runs, and standalone via
`python -m jobpilot --inbox-watch`.

```
hourly/full run
  └─ inboxwatch.watch(creds_map, primary_creds, sheet_id, cfg, llm, now)
       for each account:
         fetch recent inbox messages (Gmail API, metadata + body excerpt)
         drop message ids already in the InboxWatch sheet tab
         one Gemini call: classify each message + optional tracked-job match
         next_step  → send alert email immediately (one per finding)
         tracked match → forward-only status update on the Jobs tab
         append every judged message to the InboxWatch tab (audit + dedup)
       returns notes[] for the digest; never raises
```

### Credentials (`gauth.py`)

- Existing `credentials()` stays the primary identity (Sheets/Gmail
  compose+read/Drive).
- New `inbox_credentials() -> dict[str, Credentials]`: extra accounts from
  `JOBPILOT_INBOX_TOKENS` (JSON `{email: refresh_token}`; env from Secret
  Manager, or local gitignored `inbox_tokens.json` for dev). These credentials
  carry **only** `gmail.readonly` — the extra accounts never get compose,
  Sheets, or Drive scopes.
- The primary account's address is discovered at runtime via
  `users().getProfile(userId="me")` — no address in config or repo.

### Fetching

Per account: `in:inbox newer_than:2d -category:promotions -category:social`,
max 50 messages, metadata headers (From, Subject) + snippet + a plain-text
body excerpt (~1200 chars, from `format=full`) so the classifier sees real
evidence, not just a truncated snippet.

### Classification (one LLM call per account)

Gemini Flash (same `make_gemini_llm` wrapper as scoring), JSON-schema
response, pydantic-validated, returns per message:

- `classification`: `next_step | automated_ack | rejection | unrelated`
- `company`: best-guess company name ("" if unknown)
- `reason`: one sentence of evidence
- `job_id`: optional — set only when the email clearly matches a tracked
  application from the Sheet (tracked rows are included in the prompt, as the
  old scanner did)

Prompt is conservative on `next_step`: it requires explicit progression
evidence — scheduling request, availability ask, interview invite, OA invite,
recruiter question, document/portfolio request. Explicitly excluded:
application-received autoresponders, rejections, newsletters, job alerts, and
JobPilot's own digest/alerts. When uncertain between `next_step` and
`automated_ack`, choose `automated_ack` (a missed edge case appears in the
audit tab and can be tuned; a false alert erodes trust).

### Alerting

For each `next_step` finding, immediately send one email from the primary
account to `cfg.digest.to`:

- Subject: `🎯 {company} responded — check {account}`
- Body: account, From, Subject, body excerpt, the classifier's reason, and a
  deep link `https://mail.google.com/mail/u/?authuser={account}#all/{message_id}`
  that opens the exact message in the right Gmail account.

### State / dedup (Sheet tab `InboxWatch`)

New tab in the existing dashboard spreadsheet, created idempotently like the
Reports tab. Columns: `Checked at | Key | Account | From | Subject | Class |
Company | Alerted`. `Key` is `{account}:{message_id}` and is the dedup set —
every judged message is logged exactly once (including `unrelated`, so
nothing is re-judged hourly), and the tab doubles as an audit log of what the
classifier decided and why an alert did or didn't fire.

### Sheet status integration

When `job_id` matches a tracked row, update its `Last reply` / `Reply class`
columns and move `Status` using the forward-only rule ported from the old
scanner (manual edits always win, never downgrade, terminal Rejected always
allowed). The old scanner's `interview` class folds into `next_step`; a
boolean `is_interview` on each finding keeps the mapping mechanical:

- `rejection → Rejected`
- `next_step` with `is_interview → Interview`
- `next_step` otherwise `→ Response`
- `automated_ack` / `unrelated` → no status change

### Pipeline / CLI wiring

- `pipeline.run(..., fast=True)`: after recording jobs, run
  `inboxwatch.watch(...)` (replaces "scanner left to next scheduled run").
- `pipeline.run(...)` full: `inboxwatch.watch(...)` replaces `scanner.scan(...)`.
- `__main__.py`: new `--inbox-watch` flag runs only the watch (manual/local).
- Failure isolation: `watch()` never raises; per-account failures (expired
  token etc.) become notes that surface in the digest, so a dark inbox is
  visible.

### Config (`config.py` + profile.yaml template)

```yaml
inbox_watch:
  enabled: true
  lookback_days: 2
  max_messages: 50
```

(Account addresses/tokens deliberately live only in the secret; the secret's
key set IS the account list.)

### Ops / setup (manual, one-time)

1. `scripts/google_oauth_setup.py --inbox` — new mode: runs the consent flow
   with only `gmail.readonly`, merges the refresh token into local
   `inbox_tokens.json`, prints the JSON for Secret Manager. Run once per extra
   account.
2. `gcloud secrets create JOBPILOT_INBOX_TOKENS` + add version with the JSON.
3. `gcloud run jobs update jobpilot --set-secrets ...` to inject the env var
   (deploy.yml does source deploys and preserves env/secret config).
4. Verify the OAuth consent screen is **In production** (Testing-mode refresh
   tokens die after 7 days) and the two extra accounts can complete consent.
5. Docs: FORK-SETUP.md and gcp-setup.md gain an Inbox Watch section.

## Testing

Same patterns as the old scanner tests (pure functions, stub LLM):

- classification parsing: valid JSON → findings; garbage → empty; empty
  inputs skip the LLM
- forward-only transitions (ported from test_scanner.py)
- alert email construction: subject/body/deep-link from a finding
- dedup: messages whose key is in the seen-set are not re-judged
- watch() error isolation: a throwing account yields a note, not an exception
- fixture emails for the tricky cases: automated ack, rejection, OA invite,
  recruiter scheduling, newsletter, JobPilot's own digest

CI (`ci.yml`) runs lint + tests as usual. No UI changes (the Replies page
keeps reading the Jobs columns, which the watcher still updates).

## Out of scope

- Real-time Gmail push (Pub/Sub `users.watch`) — upgrade path if hourly ever
  feels slow; the module boundary (`watch()` per account) already fits it.
- UI surface for the InboxWatch tab — the Sheet tab is the audit view for now.
- Non-Gmail providers.
