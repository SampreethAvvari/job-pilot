# Fork setup — build your own JobPilot

This guide is written so you can hand it (plus the repo) to an AI coding agent —
Claude Code, Cursor, etc. — and say *"set this up for me."* It contains every step,
every command, and every file you must personalize.

> **Safety first:** everything in this repo that points at infrastructure belongs to
> the original author — his GCP project (`jobpilot-sva`), his Google Sheet, his
> resumes, his identity. **None of it is usable from your fork**: the CI deploy only
> runs on the original repo (guarded by `if: github.repository == ...`, and the
> Workload Identity provider only trusts that exact repo), the Sheet requires his
> private OAuth token, and there are no secrets anywhere in the repo or its history.
> You will create your own copies of everything below. You can never disturb — or
> bill — the original author, and he can never see your data.

## What you're building

```
Cloud Scheduler (30-min fast-fetch + 4x/day full run)
        │
        ▼
Cloud Run Job "jobpilot" (Python 3.12)
  fetch 7 sources → freshness/seniority/citizenship filters → Gemini scoring
  → Google Sheet (database + dashboard) → tailored resume+cover PDFs (pdflatex)
  → company outreach (published-email lookup) + Gmail drafts → inbox scanner
  → digest email
        ▲ trigger / read / write
Cloud Run Service "jobpilot-ui" (Next.js 16) behind IAP — your private console
```

Monthly cost ≈ **$0–10**: Cloud Run/Scheduler/Secret Manager free tier, Vertex AI
Gemini Flash pennies, Apify free $5 credits (LinkedIn), Adzuna/Apollo free tiers.

## Prerequisites (humans: create accounts; agents: verify CLIs)

- Google account with a GCP **billing account** (new accounts get $300 free credits)
- CLIs installed and authenticated: `gcloud`, `gh`, `git`, `docker`, Python 3.12+, Node 20+
- Free accounts + keys (all optional — each feature degrades gracefully without one):
  [Apify](https://apify.com) (LinkedIn jobs; personal token),
  [Adzuna developer](https://developer.adzuna.com) (job source; app_id + app_key),
  [Hunter.io](https://hunter.io) (outreach: verified named contacts; free tier ~50/mo),
  [Serper.dev](https://serper.dev) (outreach: web-search email lookup; free tier),
  [Apollo.io](https://apollo.io) (legacy per-job recruiter lookup)

## Step 0 — Personalize the repo (DO THIS FIRST)

Replace the original author's identity everywhere:

| File | What to change |
|---|---|
| `profile.yaml` | Your name, headline, summary, locations, sponsorship needs, role queries, company watchlist, `sheet.spreadsheet_id: ""` (empty → first run creates YOUR sheet), `digest.to:` your email |
| `src/jobpilot/resumes/*.tex` | **These are the author's real resumes — replace the content with yours.** Keep the LaTeX structure/preamble; it's ATS-verified. One page each. |
| `src/jobpilot/prompts/*.txt` | The candidate-specific lines (sponsorship status, experience years, variant descriptions) |
| `ui/src/lib/resume-links.ts` | Drive links to YOUR resume PDFs |
| `ui/src/app/resumes/page.tsx` | Your variants' Doc/PDF ids and blurbs |
| `ui/src/lib/google.ts` | `PROJECT` fallback → your project id |
| `.github/workflows/deploy.yml` | Your repo name in the `if:` guard, your project id, project number, service accounts (after Step 5) |
| `docs/gcp-setup.md` | Rewrite for your project as you go |

Sanity rule baked into the codebase: `src/jobpilot/sheets.py HEADERS` and
`ui/src/lib/types.ts HEADERS` must stay identical — if you add sheet columns,
change both.

## Step 1 — GCP project

```bash
export PROJECT=jobpilot-<yourname>        # globally unique
export REGION=us-central1
gcloud auth login
gcloud projects create $PROJECT
gcloud billing accounts list              # grab ACCOUNT_ID
gcloud billing projects link $PROJECT --billing-account=<ACCOUNT_ID>
gcloud services enable run.googleapis.com cloudscheduler.googleapis.com \
  secretmanager.googleapis.com artifactregistry.googleapis.com \
  cloudbuild.googleapis.com aiplatform.googleapis.com sheets.googleapis.com \
  gmail.googleapis.com drive.googleapis.com iap.googleapis.com \
  cloudresourcemanager.googleapis.com --project $PROJECT
```

## Step 2 — Service accounts

```bash
gcloud iam service-accounts create jobpilot-runner --project $PROJECT
gcloud projects add-iam-policy-binding $PROJECT \
  --member="serviceAccount:jobpilot-runner@$PROJECT.iam.gserviceaccount.com" \
  --role=roles/aiplatform.user --condition=None
gcloud projects add-iam-policy-binding $PROJECT \
  --member="serviceAccount:jobpilot-runner@$PROJECT.iam.gserviceaccount.com" \
  --role=roles/secretmanager.secretAccessor --condition=None

gcloud iam service-accounts create jobpilot-ui --project $PROJECT
gcloud projects add-iam-policy-binding $PROJECT \
  --member="serviceAccount:jobpilot-ui@$PROJECT.iam.gserviceaccount.com" \
  --role=roles/run.viewer --condition=None
gcloud projects add-iam-policy-binding $PROJECT \
  --member="serviceAccount:jobpilot-ui@$PROJECT.iam.gserviceaccount.com" \
  --role=roles/secretmanager.secretAccessor --condition=None
```

## Step 3 — Google OAuth (the pipeline acts as YOUR Gmail/Sheets/Drive)

Console steps (cannot be done by CLI):
1. console.cloud.google.com/auth/overview?project=$PROJECT → Get started → app name,
   External audience.
2. Audience page → **Test users → Add** → the Google account that should own the
   dashboard and send email. *(University/work Workspace accounts may need this and
   may still block unverified apps — a personal Gmail always works.)*
3. Clients page → Create client → **Desktop app** → download JSON →
   save as `client_secret.json` in the repo root (gitignored).

Then locally:

```bash
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"   # or bin/ on mac/linux
python scripts/google_oauth_setup.py    # browser opens — sign in as that account
# prints GOOGLE_OAUTH_REFRESH_TOKEN and writes token.json (local dev)
```

**Watching extra inboxes (optional):** the inbox watch can monitor additional Gmail
accounts for recruiter replies and email you the moment a company moves you forward.
Add each extra account as a test user on the consent screen (console step 2 above),
then per account:

```bash
python scripts/google_oauth_setup.py --inbox   # sign in as THAT account
```

This requests **gmail.readonly only** — extra accounts can never send mail or touch
your Sheet. Tokens merge into `inbox_tokens.json` (gitignored); the script prints the
JSON for the `JOBPILOT_INBOX_TOKENS` secret (Step 4). Publish the consent screen to
**In production** (Audience page) or Google expires all refresh tokens after 7 days.

## Step 4 — Secrets

```bash
gcloud secrets create GOOGLE_OAUTH_CLIENT_JSON --data-file=client_secret.json --project $PROJECT
printf '%s' '<refresh-token-from-step-3>' | gcloud secrets create GOOGLE_OAUTH_REFRESH_TOKEN --data-file=- --project $PROJECT
printf '%s' '<apify-token>'   | gcloud secrets create APIFY_TOKEN    --data-file=- --project $PROJECT
printf '%s' '<adzuna-app-id>' | gcloud secrets create ADZUNA_APP_ID  --data-file=- --project $PROJECT
printf '%s' '<adzuna-key>'    | gcloud secrets create ADZUNA_APP_KEY --data-file=- --project $PROJECT
printf '%s' '<apollo-key>'    | gcloud secrets create APOLLO_API_KEY --data-file=- --project $PROJECT  # optional (legacy per-job lookup)
printf '%s' '<hunter-key>'    | gcloud secrets create HUNTER_API_KEY --data-file=- --project $PROJECT  # optional (outreach: verified contacts)
printf '%s' '<serper-key>'    | gcloud secrets create SERPER_API_KEY --data-file=- --project $PROJECT  # optional (outreach: web-search emails)

# optional — only when watching extra inboxes (Step 3 --inbox):
gcloud secrets create JOBPILOT_INBOX_TOKENS --data-file=inbox_tokens.json --project $PROJECT
# and after the job exists (Step 5), attach it:
gcloud run jobs update jobpilot --region $REGION --project $PROJECT \
  --update-secrets "JOBPILOT_INBOX_TOKENS=JOBPILOT_INBOX_TOKENS:latest"
```

## Step 5 — Deploy the pipeline job + console

```bash
# pipeline (from repo root)
gcloud run jobs deploy jobpilot --source . --project $PROJECT --region $REGION \
  --service-account jobpilot-runner@$PROJECT.iam.gserviceaccount.com \
  --set-env-vars GOOGLE_CLOUD_PROJECT=$PROJECT \
  --set-secrets "APIFY_TOKEN=APIFY_TOKEN:latest,ADZUNA_APP_ID=ADZUNA_APP_ID:latest,ADZUNA_APP_KEY=ADZUNA_APP_KEY:latest,GOOGLE_OAUTH_CLIENT_JSON=GOOGLE_OAUTH_CLIENT_JSON:latest,GOOGLE_OAUTH_REFRESH_TOKEN=GOOGLE_OAUTH_REFRESH_TOKEN:latest,APOLLO_API_KEY=APOLLO_API_KEY:latest,HUNTER_API_KEY=HUNTER_API_KEY:latest,SERPER_API_KEY=SERPER_API_KEY:latest" \
  --task-timeout 45m --max-retries 0

# first run — watch it create your Sheet (id is printed in the logs)
gcloud run jobs execute jobpilot --region $REGION --project $PROJECT --wait
gcloud logging read 'resource.type="cloud_run_job"' --project $PROJECT --limit 5 --format="value(textPayload)"
# put that spreadsheet id into profile.yaml → sheet.spreadsheet_id, commit

# console (from ui/)
cd ui && gcloud beta run deploy jobpilot-ui --source . --project $PROJECT --region $REGION \
  --service-account jobpilot-ui@$PROJECT.iam.gserviceaccount.com \
  --set-env-vars "SPREADSHEET_ID=<your-sheet-id>,GOOGLE_CLOUD_PROJECT=$PROJECT,GOOGLE_CLOUD_LOCATION=$REGION" \
  --set-secrets "GOOGLE_OAUTH_CLIENT_JSON=GOOGLE_OAUTH_CLIENT_JSON:latest,GOOGLE_OAUTH_REFRESH_TOKEN=GOOGLE_OAUTH_REFRESH_TOKEN:latest" \
  --iap --no-allow-unauthenticated --memory 512Mi && cd ..

# allow the UI to trigger pipeline runs, and yourself through IAP
gcloud run jobs add-iam-policy-binding jobpilot --region $REGION --project $PROJECT \
  --member="serviceAccount:jobpilot-ui@$PROJECT.iam.gserviceaccount.com" --role=roles/run.invoker
gcloud beta iap web add-iam-policy-binding --project $PROJECT --resource-type=cloud-run \
  --service=jobpilot-ui --region=$REGION --member="user:<you@gmail.com>" \
  --role=roles/iap.httpsResourceAccessor
```

## Step 6 — Schedules

```bash
gcloud run jobs add-iam-policy-binding jobpilot --region $REGION --project $PROJECT \
  --member="serviceAccount:jobpilot-runner@$PROJECT.iam.gserviceaccount.com" --role=roles/run.invoker
# run.developer too: the fast-fetch trigger passes container-arg overrides, which
# need run.jobs.runWithOverrides — with only run.invoker every fast run 403s (BL-21)
gcloud run jobs add-iam-policy-binding jobpilot --region $REGION --project $PROJECT \
  --member="serviceAccount:jobpilot-runner@$PROJECT.iam.gserviceaccount.com" --role=roles/run.developer

# full runs 4x/day (LinkedIn + tailoring + inbox watch + digest)
gcloud scheduler jobs create http jobpilot-daily --location $REGION --project $PROJECT \
  --schedule "0 0,6,12,18 * * *" --time-zone "America/New_York" \
  --uri "https://$REGION-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$PROJECT/jobs/jobpilot:run" \
  --http-method POST --oauth-service-account-email jobpilot-runner@$PROJECT.iam.gserviceaccount.com

# fast fetch + inbox watch every 30 min, offset from the :00 full runs
# (free sources only — protects Apify credits)
gcloud scheduler jobs create http jobpilot-hourly --location $REGION --project $PROJECT \
  --schedule "15,45 * * * *" --time-zone "America/New_York" \
  --uri "https://run.googleapis.com/v2/projects/$PROJECT/locations/$REGION/jobs/jobpilot:run" \
  --http-method POST --headers "Content-Type=application/json" \
  --message-body '{"overrides":{"containerOverrides":[{"args":["--fast","--sources","greenhouse,lever,ashby,remoteok,hn_hiring,adzuna"]}]}}' \
  --oauth-service-account-email jobpilot-runner@$PROJECT.iam.gserviceaccount.com
```

## Step 7 — CI/CD from YOUR repo (optional but nice)

```bash
export PROJECT_NUMBER=$(gcloud projects describe $PROJECT --format="value(projectNumber)")
export YOUR_REPO=<github-user>/<repo-name>
gcloud iam workload-identity-pools create github --location global --project $PROJECT
gcloud iam workload-identity-pools providers create-oidc github-provider \
  --location global --workload-identity-pool github \
  --issuer-uri "https://token.actions.githubusercontent.com" \
  --attribute-mapping "google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition "assertion.repository=='$YOUR_REPO'" --project $PROJECT
gcloud iam service-accounts create jobpilot-deployer --project $PROJECT
for r in roles/run.admin roles/cloudbuild.builds.editor roles/storage.admin \
         roles/artifactregistry.writer roles/serviceusage.serviceUsageConsumer; do
  gcloud projects add-iam-policy-binding $PROJECT \
    --member="serviceAccount:jobpilot-deployer@$PROJECT.iam.gserviceaccount.com" --role=$r --condition=None
done
for sa in jobpilot-runner jobpilot-ui; do
  gcloud iam service-accounts add-iam-policy-binding $sa@$PROJECT.iam.gserviceaccount.com \
    --project $PROJECT --role roles/iam.serviceAccountUser \
    --member "serviceAccount:jobpilot-deployer@$PROJECT.iam.gserviceaccount.com"
done
gcloud iam service-accounts add-iam-policy-binding \
  $PROJECT_NUMBER-compute@developer.gserviceaccount.com --project $PROJECT \
  --role roles/iam.serviceAccountUser \
  --member "serviceAccount:jobpilot-deployer@$PROJECT.iam.gserviceaccount.com"
gcloud iam service-accounts add-iam-policy-binding \
  jobpilot-deployer@$PROJECT.iam.gserviceaccount.com --project $PROJECT \
  --role roles/iam.workloadIdentityUser \
  --member "principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github/attribute.repository/$YOUR_REPO"
```

Then in `.github/workflows/deploy.yml`: change the `if:` guard to your repo, and the
`workload_identity_provider` / `service_account` / project values to yours.

## Verify

```bash
.venv/Scripts/python -m pytest -q                 # 130+ tests green
.venv/Scripts/python -m jobpilot --dry-run --sources greenhouse,ashby   # live fetch, no creds needed
gcloud run jobs execute jobpilot --region $REGION --project $PROJECT --wait
```
Then: digest email arrives, Sheet fills, console shows jobs, ✨Tailor produces a
one-page PDF in ~1 minute.

## Hard-won gotchas (save yourself the debugging)

1. **pdflatex, not XeTeX/Tectonic** for resume PDFs — XeTeX output breaks word
   extraction ("New Y ork") in ATS parsers; `cmap` + pdflatex gives a clean text layer.
2. **Dockerfile must use ENTRYPOINT** (not CMD) or per-execution arg overrides
   (`--tailor-job`) silently run the full pipeline instead.
3. **Apify**: rental actors (e.g. `bebity`) 403 on free accounts — use a
   pay-per-result actor (`curious_coder/linkedin-jobs-scraper`); its `count` min is 10.
4. **Task timeout 45m** — LinkedIn scrape + tailoring exceeds the 20m default.
5. **Workspace accounts** (university/work) must be added as OAuth **test users**;
   wrong-account consent is the #1 setup mistake — verify with a Gmail profile call.
6. **Sheets headers** are duplicated in Python and TypeScript — change both together.
7. Sources fail independently by design — one broken source never kills a run; check
   the digest's "Run notes" for per-source status.

## Appendix A — Google permissions, exactly what you grant and why

The pipeline acts **as you**, via a user-OAuth refresh token (Step 3). Four scopes,
nothing broader:

| Scope | Used for | NOT able to |
|---|---|---|
| `spreadsheets` | create/read/write the JobPilot dashboard Sheet | touch other spreadsheets it didn't open by id |
| `gmail.compose` | create the **drafts** for recruiter outreach and send your digest email to yourself | read your mail |
| `gmail.readonly` | the inbox watch: reads recent inbox mail to spot recruiter replies and real next-step responses (extra watched accounts get ONLY this scope) | send/delete anything |
| `drive.file` | upload tailored resume/cover PDFs and read files **this app created or you explicitly opened with it** | see the rest of your Drive |

Guarantees baked into the code: outreach emails are **created as Gmail drafts, never
sent** (`outreach.py` has no send call); the digest and inbox-watch alerts are sent
only **to your own address**; the inbox watch only moves application status forward
and never overrides your manual edits. Revoke everything anytime at myaccount.google.com → Security →
Third-party access, or destroy the `GOOGLE_OAUTH_REFRESH_TOKEN` secret.

## Appendix B — Feature catalog (what each part does + where it's configured)

- **Multi-source fetch** (`src/jobpilot/sources/`): Greenhouse/Lever/Ashby company
  boards (keyless; watchlist in `profile.yaml`), RemoteOK, HN "Who is hiring",
  Adzuna (free key), LinkedIn via Apify actor with 24h/full-time/entry filters baked
  into the search URLs. Each source fails independently; per-source counts/failures
  appear in the digest's **Run notes**.
- **Filter wall** (`pipeline.quality_filter`): posting age window
  (`caps.freshness_days`), seniority/role words (`exclude_title_words`),
  citizenship/clearance/no-sponsorship regexes (`exclude_jd_patterns`) — all dropped
  *before* any LLM call.
- **AI scoring** (`scorer.py` + `prompts/score_v1.txt`): Gemini scores fit 0–100,
  explains why, flags sponsorship likelihood (auto-rejects "unlikely" when your
  profile requires sponsorship), classifies role (FDE/AIE/MLE/DE/DS/SWE), picks your
  best resume variant. Tune via the prompt + `scoring.threshold`.
- **Dashboard Sheet** (`sheets.py`): created on first run; columns A–AA; Status
  dropdown drives everything downstream. The Sheet is the only database.
- **Resume tailoring** (`tailor.py` + `prompts/tailor_v1.txt`): for every job
  scoring ≥ `tailoring.auto_threshold` (and on-demand via the console's ✨Tailor),
  Gemini rewrites your variant within truth guardrails, pdflatex compiles a one-page
  PDF + cover letter, both upload to Drive and link onto the row with extracted JD
  keywords. Cost ≈ a cent per job, capped by `tailoring.max_per_run`.
- **Per-job outreach drafts** (`outreach.py`, `apollo.py`): when a job turns
  *Applied* (or on-demand ✉Draft), Apollo looks up 1–2 recruiters (skips gracefully
  without a key), Gemini writes a short note from your real accomplishments, and it
  lands in **your Gmail drafts** with a LinkedIn people-search fallback on the row.
- **Company outreach** (`company_outreach.py`, `website_email.py`, `hunter.py`, the
  console **Outreach** tab): search a company → pick the best-fit resume of four
  (auto, overridable) → short plain-English cold email (no buzzwords, no em dashes)
  + tailored one-page cover letter → **Gmail draft, never sent**. The recipient is a
  **published** careers email, never guessed: the company website (`/careers`,
  `/contact`…), then any email printed in the job description, then a web search
  (Serper). With **`HUNTER_API_KEY`** set it also pulls verified named contacts;
  with **`SERPER_API_KEY`** set it adds the web-search source. Every careers email
  found is recorded per company on the Sheet's **Outreach** tab. CLI:
  `--company-outreach "<Company>"` (one), `--auto-company-outreach N [--roles AIE,FDE]`
  (batch the freshest direct-board, entry-level US companies that publish an email;
  deduped; capped at N). All draft-only.
- **Inbox watch** (`inboxwatch.py`): every run (fast + full) reads recent mail
  from the primary inbox plus any extra accounts in `JOBPILOT_INBOX_TOKENS`, and
  judges EVERY email — not just tracked applications. A genuine next step
  (interview/phone-screen invite, scheduling or availability request, online
  assessment, document request) triggers an **immediate alert email** with a deep
  link to the exact message in the right account. Automated "thanks for applying"
  acks and rejections never alert but are logged in the Sheet's `InboxWatch` tab
  (the audit trail of every decision). Emails matched to tracked rows advance
  Status (`Response`/`Interview`/`Rejected`, forward-only; manual edits win).
  Configured in `profile.yaml → inbox_watch`; standalone run:
  `python -m jobpilot --inbox-watch`.
- **Digest email** (`digest.py`): after each full run — shortlist table sorted by
  fit, posted-age, links, and the Run notes. Recipient = `digest.to`.
- **Console** (`ui/`): jobs table (role/posted/fit/source filters, three sort
  modes), Apply→confirm-on-return flow with green ticks and Applied dates,
  **Applied (n)** tab, ✕ Dismiss (hide forever, auditable), resume armory,
  replies feed, **Companies** watchlist, **Outreach** tab (company search +
  batch-draft button), per-job **copilot chat** drawer, ⟳ fast refresh
  (fetch+score only, ~3–6 min).
- **Schedules**: 30-min fast-fetch (free sources), 4×/day full runs. Change cadence
  with `gcloud scheduler jobs update`.

## Appendix C — The resume system blueprint (bring your own variants)

You probably have different resumes for different role types. The whole chain is
variant-driven and yours to reshape:

1. **Write each variant** as a `.tex` file from the template in
   `src/jobpilot/resumes/` (single column, the provided `_preamble.tex`, one page).
   Name them `resume_<KEY>.tex` — keys are yours (e.g. `PM`, `SRE`, `QUANT`).
2. **Register the keys** everywhere they matter (grep for an existing key like
   `AIE` to find all five spots): `VARIANT_FILES` in `src/jobpilot/tailor.py`,
   the `resume_variant` Literal in `src/jobpilot/scorer.py`, the variant
   descriptions in `prompts/score_v1.txt`, `KEYWORDS` in `scripts/ats_check.py`,
   and `ROLES` in `ui/src/lib/types.ts` if you also want it as a console filter.
3. **Validate with the ATS gate**: compile (`docker run --rm -v "$PWD:/work" -w /work
   texlive/texlive pdflatex -interaction=nonstopmode resume_KEY.tex`), define the
   keyword set for that role in `ats_check.py`, then `python scripts/ats_check.py`
   — it enforces **exactly one page** and **≥85% keyword coverage** against a real
   PDF text extraction (what ATS parsers actually see).
4. **Keep the real content private**: store each final `.tex` in Secret Manager and
   mount as `RESUME_TEX_<KEY>` on the job (the repo file stays a Jane Doe template).
   Same for your profile → `JOBPILOT_PROFILE_YAML`. Upload the PDFs to your Drive
   and point the console at them via `RESUME_LINKS` / `RESUMES_JSON` env vars on
   the UI service (plus `PILOT_NAME` for the sidebar).
5. **The loop**: the scorer now recommends one of YOUR variants per job, the
   tailor rewrites that variant per JD (truth-guarded), and the console links the
   right PDF on every row.

## Contributing back

This is an open-source project (MIT). If you build something useful in your fork —
a new source, a better filter, console UX — open a PR: see
[CONTRIBUTING.md](../CONTRIBUTING.md). CI (lint + tests) runs on every PR with no
secrets required.

## Non-negotiable design rules (keep these)

- **Never auto-send** email or auto-submit applications; drafts only, humans click send.
- **Tailoring may never invent facts** — reorder/rephrase/re-emphasize only.
- Respect job boards: official/public APIs only, modest caps, no Easy-Apply bots.
