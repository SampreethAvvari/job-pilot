# Contributing

JobPilot is open source (MIT). Forks, features, and PRs are welcome — many users run
their own deployment and the best improvements come back upstream.

## Workflow

1. Fork, branch from `master`, build your feature in your own deployment first.
2. Run the gates locally — they're the same ones CI runs on your PR (no secrets needed):
   ```bash
   .venv/Scripts/python -m pytest -q      # all tests green
   .venv/Scripts/python -m ruff check src tests scripts
   cd ui && npm run build                 # console compiles
   ```
3. Open a PR describing: what the feature does, how you've run it in your own
   deployment, and any new env vars/secrets/columns it introduces.

## What gets merged

- Features that generalize: new job sources, better filters, scoring/tailoring
  improvements, console UX — parameterized via `profile.yaml` or env, never hardcoded
  to one person.
- Fixes with a test that fails before and passes after.
- Docs that close a real setup gap.

## House rules (non-negotiable in PRs)

- **Never auto-send** email or auto-submit applications. Drafts only; a human clicks send.
- **Tailoring never invents facts** — reorder, rephrase, re-emphasize only.
- **No personal data in the repo** — profiles/resumes load from env/Secret Manager;
  templates use Jane Doe. CI must stay secret-free.
- Job sources use official/public APIs with modest caps. No ToS-violating scraping,
  no Easy-Apply bots.
- Sheet columns are defined twice (`src/jobpilot/sheets.py` HEADERS and
  `ui/src/lib/types.ts` HEADERS) — change both, append-only, and say so in the PR.

## Architecture orientation

Read `README.md` for the system shape and `docs/FORK-SETUP.md` for the full deployment
blueprint. Pipeline stages live in `src/jobpilot/` (one module per stage; sources are
plug-ins in `sources/` behind `fetch(sc, cfg, client) -> list[Posting]`). The console
is `ui/` (Next.js App Router; Sheet is the only database).
