# GCP layout (reference)

This documents the shape of a JobPilot deployment. For the full provisioning
walkthrough with commands, see [FORK-SETUP.md](FORK-SETUP.md).

- **Project:** `<your-project-id>`, billing-enabled.
- **Cloud Run Job `jobpilot`** — the pipeline. Built from repo source via Cloud Build,
  runs as `jobpilot-runner@…` (roles: `aiplatform.user`, `secretmanager.secretAccessor`,
  `run.invoker` on itself for the scheduler). Env `GOOGLE_CLOUD_PROJECT` switches the
  scorer/tailor to Vertex AI Gemini (no API key needed). Task timeout 45m.
- **Cloud Run Service `jobpilot-ui`** — the console. Runs as `jobpilot-ui@…`
  (roles: `run.viewer`, `run.invoker` on the job, `secretmanager.secretAccessor`),
  protected by IAP with a per-user allowlist.
- **Cloud Scheduler** — `jobpilot-daily` (`0 0,6,12,18 * * *`, full runs) and
  `jobpilot-hourly` (other hours, `--fast` + free sources only). Both run the
  inbox watch (reply detection + alerts) — no extra scheduler needed.
- **Secret Manager** (all injected as env vars):
  `GOOGLE_OAUTH_CLIENT_JSON`, `GOOGLE_OAUTH_REFRESH_TOKEN` — user OAuth identity;
  `JOBPILOT_INBOX_TOKENS` — JSON `{email: refresh_token}` for EXTRA watched
  inboxes (gmail.readonly only; the primary identity is watched automatically);
  `APIFY_TOKEN`, `ADZUNA_APP_ID/KEY`, `APOLLO_API_KEY` — source/contact APIs;
  `JOBPILOT_PROFILE` (→ env `JOBPILOT_PROFILE_YAML`), `RESUME_TEX_FDE/MLE/SDE/AIE`
  — your personal profile and resumes, kept out of the repo.
- **CI/CD** — GitHub Actions: `ci.yml` (lint + tests, runs on all PRs, no secrets),
  `deploy.yml` (path-filtered deploys via Workload Identity Federation, owner repo only).

## Useful commands

```bash
gcloud run jobs execute jobpilot --region <region> --project <project> --wait
gcloud run jobs executions list --job jobpilot --region <region> --project <project>
gcloud logging read 'resource.type="cloud_run_job"' --project <project> --limit 50
gcloud scheduler jobs run jobpilot-daily --location <region> --project <project>
```
