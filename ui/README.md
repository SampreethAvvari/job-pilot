# JobPilot console

The web console for **[JobPilot](../README.md)**: a **Next.js 16** (App Router) app
that runs on Cloud Run behind Google IAP and sits on top of the same Google Sheet
the Python pipeline writes to. The Sheet is the database; this UI is the cockpit.

## What's in it

- **Jobs** — every scored posting with its fit score, the model's "why", source,
  live posted-age, and best-match resume variant. Filter by role category,
  posted-age, fit, source, and **resume variant** (FDE / AIE / MLE / SDE); sort by
  recency.
- **Apply flow** — open the posting, then confirm when you come back; the row stamps
  a date and moves to **Applied**. Dismiss (✕) hides an irrelevant job for good
  (logged, so it can train the filters later).
- **Companies** — the watchlist: add/remove companies, see each board's health and
  newest-job freshness, collapse quiet companies, and drill into one company's jobs.
- **Replies** — the inbox-watch feed: recruiter replies classified into real
  next-steps, rejections, and noise, each linked back to the original message.
- **Per-job copilot (💬)** — an independent chat drawer on every row, grounded in a
  knowledge pack (GitHub / portfolio / resumes / profile) and the job's live-fetched
  description, with PDF/image attachments and clear-chat. Plus **✨ tailor** and
  **✉ draft** actions per job.

## Develop

```bash
npm install
npm run dev      # http://localhost:3000
```

The console reads and writes the dashboard Sheet through the pipeline's service
account, and the chat copilot calls Vertex AI through a guardrailed server route
(no model keys ever reach the browser). The IAP, OAuth, and Cloud Run deploy steps
all live in **[../docs/FORK-SETUP.md](../docs/FORK-SETUP.md)**.

> Heads up: this is **Next.js 16** (App Router). Some APIs and conventions differ
> from older Next.js — check `node_modules/next/dist/docs/` before assuming an API
> exists (see [`AGENTS.md`](AGENTS.md)).
