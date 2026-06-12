# JobPilot Assistant (grounded chat) — Design

**Date:** 2026-06-12
**Status:** Approved

## Problem

Some applications need human-in-the-loop artifacts the pipeline can't produce
unattended: jobs whose auto-tailoring failed or that were never tracked, and
application extras ("Why this company?", "Explain a project"). The user wants a
chat grounded in his real work history (GitHub, portfolio, resumes) that can:

1. Generate an updated resume + cover letter from a pasted JD.
2. Answer application questions in STAR form, technically, with company
   research — and without AI tells (no em-dashes, no filler).
3. Refuse everything else.

## Decisions (user-approved)

- Models: Gemini 2.5 Flash default, 3.1 Pro per-message toggle (~$10/mo + usage).
- Grounding sources: GitHub (auto), portfolio site (auto), 4 master resumes,
  profile.yaml, manual "Extra facts" — LinkedIn skipped (no API; facts can be
  pasted into Extra facts).
- Resume/cover output: real PDFs through the existing tailor pipeline (judge
  loop, ATS gate, Drive, transparency report) — never chat-improvised LaTeX.
- Surface: `Assistant` page in the console (IAP), plus per-job entry points.

## Knowledge pack

`src/jobpilot/knowledge.py` builds a distilled corpus and writes it to a
`Knowledge` Sheet tab (`Source | Updated | Content` rows, chunked under the
50k-char cell limit):

- `github`: public repos of the configured user — name, description, language,
  topics, stars, README excerpt (top repos by recency/stars, capped).
- `portfolio`: profile.portfolio URL fetched and stripped to text.
- `resumes`: text content of the 4 master resume variants (facts source of truth).
- `profile`: headline, summary, locations, sponsorship constraints.
- `extras`: free-text row the user edits directly in the Sheet; never
  overwritten by refresh.

Refresh: CLI `--refresh-knowledge`, run inside the daily full runs; reading is
a single Sheet range fetch. Pack size target 10–20k tokens.

## Chat API

`POST /api/assistant` (console route handler, Node → Vertex AI REST):

- Request: `{ messages: [{role, text}], model: "flash"|"pro", jobId?: string }`.
- Server builds: guardrail system prompt + knowledge pack (from the Sheet) +
  job context (Sheet row JD when jobId given) + history.
- Google Search grounding tool enabled on every call (company research).
- UI service account needs `roles/aiplatform.user` on the project.
- Non-streaming JSON response; model ids: `gemini-2.5-flash`, `gemini-3.1-pro`.

## Guardrails

Scope (system prompt): ONLY resume updates, cover letters, application-question
answers, and questions about the user's own background/projects (company
research allowed in service of these). Anything else → one-line refusal.

Truth: answers may only use facts present in the knowledge pack / job context;
never invent employers, metrics, or skills (same rule as tailoring).

Style: STAR structure for experience answers and resume bullets; first person;
technical specificity; banned AI tells. Deterministic post-filter: output
containing em/en dashes (— –) is regenerated once with explicit feedback, then
sanitized (dashes replaced) as a last resort.

## Resume/cover generation flow

Chat never writes LaTeX. When the user requests documents:

1. Assistant extracts `{company, title, jd}` from the conversation (structured
   output call).
2. `POST /api/assistant/track` appends a Jobs row (source `manual`, JD excerpt
   filled, status New) — reusing dedup keys; if the job already exists (by
   company+title) it reuses that row.
3. The route triggers the existing `--tailor-job <id>` Cloud Run execution;
   the chat polls `/api/jobs` and posts Resume/Cover/ATS links when ready.
4. The job is now tracked: apply-confirm, outreach, replies all work on it.

## UI

`/assistant` page: chat thread (localStorage persistence), model toggle,
job-context selector (tracked job dropdown or pasted JD), action chip
"Generate resume + cover" when a JD is in context. Jobs-table rows get a 💬
link that opens `/assistant?job=<id>`.

## Out of scope

- LinkedIn ingestion (manual Extra facts instead).
- Server-side chat history.
- Auto-submitting anything (hard rule: drafts/PDFs only, never sent).
- Streaming responses (add later if latency annoys).

## Cost

~$8–15/mo at ~5 sessions/day on Flash; Pro toggle adds per-use; search
grounding $0–10/mo; infra $0 (existing console + job).
