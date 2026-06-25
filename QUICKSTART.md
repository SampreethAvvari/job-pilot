# Quickstart

JobPilot is your personal job-hunt autopilot: it finds fresh roles across many free
sources, scores them against your profile, tailors a one-page resume + cover letter
per match, drafts recruiter outreach (never sends), and tracks everything in a Google
Sheet that doubles as your dashboard. This page gets you running fast. For the full
cloud deployment, see **[docs/FORK-SETUP.md](docs/FORK-SETUP.md)**.

> **It never sends anything on its own.** Emails are Gmail *drafts*; applications are
> your clicks. There are **no secrets in this repo or its history** — you supply your
> own, and your data never touches anyone else's fork.

## 1. Try it locally in ~5 minutes (no cloud, no keys)

You only need Python 3.12+ and git.

```bash
git clone https://github.com/SampreethAvvari/job-pilot.git
cd job-pilot
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"     # Windows  (use .venv/bin/pip on mac/linux)

.venv/Scripts/python -m pytest -q          # 130+ tests, all green
.venv/Scripts/python -m jobpilot --dry-run --sources greenhouse,ashby
```

`--dry-run` does a **live fetch + filter with zero credentials** — no Google, no AI,
no keys — and prints the postings it found. That's the engine working end to end.

## 2. Make it yours (the 3 things that matter)

1. **Your profile** — copy the template and fill it in:
   ```bash
   cp profile.yaml my-profile.yaml      # then edit: name, summary, locations,
                                        # sponsorship, role queries, company watchlist
   ```
   Run with `--config my-profile.yaml`, or keep it private and mount it as the
   `JOBPILOT_PROFILE_YAML` env var in the cloud (see FORK-SETUP).
2. **Your resumes** — replace the four Jane Doe templates in
   `src/jobpilot/resumes/*.tex` with your own (one page each; the LaTeX preamble is
   ATS-verified). Variant keys (`AIE/FDE/MLE/SDE`) are yours to rename — see
   [FORK-SETUP Appendix C](docs/FORK-SETUP.md#appendix-c--the-resume-system-blueprint-bring-your-own-variants).
3. **Your Google + GCP** — the full hourly autopilot, console, and Gmail/Sheets/Drive
   access are set up in **[docs/FORK-SETUP.md](docs/FORK-SETUP.md)** (≈30 min, copy-paste
   commands; you can even hand the repo + that guide to an AI agent and say "set this up").

## 3. Optional keys (everything degrades gracefully without them)

| Key | Unlocks | Free? |
|---|---|---|
| `GEMINI_API_KEY` *or* GCP Vertex | AI scoring + resume/cover tailoring | Vertex: pennies/run |
| `APIFY_TOKEN` | LinkedIn jobs source | free $5/mo credits |
| `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` | Adzuna jobs source | free tier |
| `HUNTER_API_KEY` | Outreach: verified named contacts | free ~50/mo |
| `SERPER_API_KEY` | Outreach: web-search email lookup | free tier |

No key → that one feature is skipped, the rest run fine. The free board sources
(Greenhouse, Lever, Ashby, RemoteOK, HN "Who's Hiring") need **no keys at all**.

## 4. What you get once deployed

- **Hourly**: fresh jobs + inbox reply alerts.
- **4×/day**: LinkedIn + per-job tailored resume/cover PDFs + a digest email.
- A private **Next.js console** (Google sign-in via IAP): jobs, filters, one-click
  apply-and-confirm, applied tracker, resume armory, replies feed, a **Companies**
  watchlist, an **Outreach** tab (search a company → tailored cold email + resume +
  cover letter as a Gmail draft, addressed to a *published* careers email — never
  guessed), and a per-job AI **copilot** chat.

Monthly cost ≈ **$0–10** on GCP free tiers + Vertex Gemini Flash pennies.

## Contributing

MIT licensed. New sources, smarter filters, console UX — PRs welcome. See
[CONTRIBUTING.md](CONTRIBUTING.md); CI (lint + tests) runs on every PR, no secrets
required.
