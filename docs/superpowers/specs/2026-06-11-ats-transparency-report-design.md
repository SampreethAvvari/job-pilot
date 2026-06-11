# ATS Transparency Report — design

Date: 2026-06-11. Status: approved (chat) — "did you implement this and deploy it?"

## Problem

The dashboard shows a tailored resume, cover letter, and an ATS score per job, but
not *why*: which JD keywords drove the rewrite, where each keyword came from in the
posting, what the baseline resume was missing, how gaps were closed, and which gaps
are genuinely unfillable. The ATS link today opens a raw judge report in a new tab.

## Decisions (user-confirmed)

- **Interaction:** hover on the ATS score shows a compact summary card; click pins
  the full report panel over the dashboard (no navigation). Esc/outside-click closes.
- **Diff:** both a `latexdiff` highlighted PDF in Drive (additions marked, deletions
  struck) AND a deterministic word-level diff rendered inside the panel.
- **Backfill:** forward-only. Pre-feature rows get a "Generate report" button in the
  panel that reconstructs a report from the stored PDFs on demand.
- **Throughput:** `tailoring.max_per_run` 15 → 30, `tailoring.auto_threshold`
  60 → 75 (private profile.yaml + JOBPILOT_PROFILE secret, not repo defaults).

## Architecture

### 1. Report generation (`src/jobpilot/explain.py`)

One extra schema-enforced Gemini call at the END of `tailor_row`, after the rewrite
loop picks the winning tex and the cover letter compiles. Inputs: JD excerpt, job
URL, baseline master tex, final tailored tex, cover letter tex, JD keywords, judge
report. Output (pydantic `TransparencyReport`):

- `jd`: `{summary, requirements[], nice_to_haves[]}` — what was pulled from the link
- `keywords[]`: `{keyword, jd_quote, in_baseline, action: already_present|added|
  not_addable, section, before, after, reason}` — `jd_quote` is the verbatim JD
  sentence the keyword came from; UI builds `jobURL#:~:text=` source links from it
- `resume_rationale`, `cover_rationale`: the model's thinking
- `master_suggestions[]`: not-addable keywords worth adding to the master for real

Deterministic extras attached in code (not LLM-claimed):

- `diff_sections[]`: `{section, baseline, tailored}` plain-text pairs (summary,
  skills, per-role bullets) parsed via `judge.parse_tex` from both texes — the UI
  diffs and highlights these client-side
- `diff_pdf`: Drive URL of the latexdiff PDF ("" when unavailable)
- `ats`: the judge report (score, breakdown, coverage, attempts)

Persisted via `sheets.append_report(kind="tailor", key=job_id, …)` — same Reports
tab as judge reports; report JSON capped at 49 000 chars (truncate `diff_sections`
first, then JD quotes). Generation failures degrade to a note; tailoring itself
must never fail because the explainer did.

### 2. Diff PDF (`latexdiff`)

`texlive-extra-utils` added to the Docker image. `latexdiff baseline.tex
tailored.tex | pdflatex` → `<slug>_diff.pdf` uploaded next to the resume PDF.
Any failure (latexdiff markup breaking custom macros) → skip the PDF, log a note,
panel diff still works.

### 3. Legacy rows (`--explain-job <job_id>` CLI)

Downloads the tailored resume PDF from Drive, extracts text (pypdf), compiles the
baseline master to PDF text, runs the same explain prompt with PDF text instead of
tex (`precision: "pdf"` recorded in the report; no diff PDF, coarser
`diff_sections`). Triggered from the UI panel button through the same Cloud Run
job-override path the ✨ Tailor button uses (`/api/explain` → `--explain-job`).

### 4. UI

- `GET /api/reports?kind=tailor&key=<id>&format=json` returns the parsed report
  (existing route gains a JSON mode).
- `components/ats-report.tsx`: hover card (score bars, coverage, added/missing
  counts) + pinned panel (portal-rendered per BL-13; sections: pulled-from-JD,
  keyword table with source links, highlighted diff, rationale, ATS breakdown,
  links to resume/cover/diff PDFs). Word-level diff computed with a small LCS
  helper, no new dependency.
- `jobs-table.tsx`: ATS score becomes the hover/click trigger; report fetched
  lazily on first hover, cached in component state.

## Error handling

- Explain call: 1 retry on schema mismatch, then degrade (tailoring note says
  "report failed"; panel shows judge report + Generate report button).
- latexdiff: best-effort, never blocks tailoring.
- Reports tab row >49KB: truncate as above; JSON parse failures in UI render the
  raw judge report fallback.

## Testing

- Python: unit tests for explain prompt building, report assembly/truncation,
  diff_sections parsing, latexdiff wrapper (subprocess mocked), CLI dispatch.
- UI: textual diff helper unit-tested; component render smoke via existing
  patterns (manual verification on the deployed console for hover/pin behavior).

## Out of scope

- No new Sheet columns (HEADERS untouched on both sides).
- No auto-backfill of the ~136 legacy rows.
- Outreach drafts unchanged.
