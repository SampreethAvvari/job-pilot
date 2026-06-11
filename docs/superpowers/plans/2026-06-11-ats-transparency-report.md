# ATS Transparency Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Click/hover the ATS score on the dashboard to see a persisted per-job report: what was pulled from the JD, each keyword's source quote + link, what the baseline resume was missing, how gaps were closed (with highlighted diff + latexdiff PDF), what's genuinely missing, and the model's rationale.

**Architecture:** One extra schema-enforced Gemini call at the end of `tailor_row` produces a `TransparencyReport`; deterministic diff sections and a latexdiff PDF are attached in code; everything persists to the existing Reports tab (`kind="tailor"`, key=job id). The Next.js console renders a hover summary card + click-pinned panel from `/api/reports?kind=tailor&key=<id>`. Legacy rows get an on-demand `--explain-job` reconstruction from PDFs.

**Tech Stack:** Python 3.12 (pydantic, google-genai via existing `make_gemini_llm`), latexdiff (texlive-extra-utils), Next.js 16 console (no new deps; hand-rolled LCS word diff).

Spec: `docs/superpowers/specs/2026-06-11-ats-transparency-report-design.md`

---

### Task 1: `explain.py` — models, prompt, diff sections, truncation

**Files:**
- Create: `src/jobpilot/explain.py`
- Test: `tests/test_explain.py`

- [ ] **Step 1: failing tests** for `diff_sections`, `build_explain_prompt`, `assemble_report` truncation (see test code below)
- [ ] **Step 2: run, verify fail** — `pytest tests/test_explain.py -q` → ImportError
- [ ] **Step 3: implement** `explain.py`:

```python
"""Tailoring transparency: why the resume changed, keyword provenance, rationale."""
from __future__ import annotations

import json
from typing import Callable, Literal

from pydantic import BaseModel, Field

from jobpilot.judge import parse_tex

MAX_REPORT_CHARS = 49000


class KeywordFate(BaseModel):
    keyword: str
    jd_quote: str = ""          # verbatim JD sentence it came from
    in_baseline: bool = False
    action: Literal["already_present", "added", "not_addable"]
    section: str = ""           # where it was added
    before: str = ""            # bullet/line before the change ("" if new)
    after: str = ""             # bullet/line after the change
    reason: str = ""            # why added there / why genuinely not addable


class JDPulled(BaseModel):
    summary: str = ""
    requirements: list[str] = Field(default_factory=list)
    nice_to_haves: list[str] = Field(default_factory=list)


class TransparencyReport(BaseModel):
    jd: JDPulled = JDPulled()
    keywords: list[KeywordFate] = Field(default_factory=list)
    resume_rationale: str = ""
    cover_rationale: str = ""
    master_suggestions: list[str] = Field(default_factory=list)


PROMPT = """..."""  # full prompt in implementation


def build_explain_prompt(company, title, jd_excerpt, job_url, baseline_tex,
                         tailored_tex, cover_tex, keywords, ats_issues) -> str: ...

def diff_sections(baseline_tex: str, tailored_tex: str) -> list[dict]:
    """Deterministic plain-text pairs via judge.parse_tex: summary, skills, roles."""

def generate_report(prompt: str, llm: Callable[[str], str]) -> TransparencyReport:
    """1 retry on schema mismatch, then raises."""

def assemble_report(tr: TransparencyReport, diffs: list[dict], diff_pdf: str,
                    ats: dict, precision: str = "tex") -> str:
    """JSON string capped at MAX_REPORT_CHARS (drop diffs first, then jd_quotes)."""
```

- [ ] **Step 4: run, verify pass**
- [ ] **Step 5: commit** `feat(explain): transparency report models, prompt, diff sections`

### Task 2: latexdiff PDF

**Files:**
- Create: `latexdiff_pdf()` in `src/jobpilot/explain.py`
- Modify: `Dockerfile` (add `texlive-extra-utils` to the apt install line)
- Test: `tests/test_explain.py` (subprocess mocked)

- [ ] Failing test: `latexdiff_pdf` returns None when latexdiff missing/fails; returns pdf bytes when subprocess succeeds (mock `subprocess.run` + `compile_pdf`)
- [ ] Implement: write both texes to temp files, `latexdiff --type=UNDERLINE base.tex tailored.tex`, compile via `latexpdf.compile_pdf`; any exception → `None`
- [ ] Dockerfile: `texlive-extra-utils` appended to apt packages
- [ ] Run suite, commit `feat(explain): latexdiff highlighted diff PDF`

### Task 3: wire into `tailor_row`

**Files:**
- Modify: `src/jobpilot/tailor.py` (after `append_report` of judge report)
- Test: `tests/test_tailor.py`

- [ ] Failing test: monkeypatched `tailor_row` happy path appends a second report `kind="tailor"` and uploads `<slug>_diff.pdf`; explainer exception does NOT fail tailoring (note still says "tailored:")
- [ ] Implement in `tailor_row` after the existing `append_report`:

```python
        try:
            from jobpilot import explain
            diff_pdf_url = ""
            dp = explain.latexdiff_pdf(_resume_tex(variant), tex, f"{company}_diff")
            if dp:
                diff_pdf_url = upload_pdf(creds, day, f"{slug}_diff.pdf", dp)
            ep = explain.build_explain_prompt(company, title, description,
                                              row.get("URL", ""), _resume_tex(variant),
                                              tex, result.cover_letter_tex,
                                              result.keywords, report["issues"])
            tr = explain.generate_report(ep, explain_llm)
            diffs = explain.diff_sections(_resume_tex(variant), tex)
            sheets.append_report(creds, spreadsheet_id, "tailor", row["Job ID"],
                                 report["score"],
                                 explain.assemble_report(tr, diffs, diff_pdf_url, report),
                                 now.strftime("%Y-%m-%d %H:%M"))
        except Exception as exc:
            ...  # note only — tailoring already succeeded
```

`explain_llm` = `make_gemini_llm(cfg, schema=explain.TransparencyReport)` built in `tailor_row` (scorer already supports per-call schema, BL-18).

- [ ] Run suite, commit `feat(tailor): persist transparency report + diff PDF per tailoring`

### Task 4: `--explain-job` CLI (legacy rows)

**Files:**
- Create: `explain_job_row()` in `src/jobpilot/explain.py`
- Modify: `src/jobpilot/__main__.py` (new arg, same shape as `--tailor-job`)
- Test: `tests/test_explain.py`

- [ ] Failing test: `explain_job_row` with mocked Drive download + llm appends `kind="tailor"` report with `"precision": "pdf"`
- [ ] Implement: download tailored PDF by file id parsed from the `Tailored resume` URL, pypdf text; baseline = compile `_resume_tex(variant)` → pypdf text; same prompt with PDF text; `diff_sections` from two single-section text blobs; no diff PDF
- [ ] `__main__.py`: `--explain-job <job_id>` dispatch (mirror `--tailor-job` block)
- [ ] Run suite, commit `feat(explain): --explain-job backfill for legacy tailored rows`

### Task 5: UI trigger route

**Files:**
- Modify: `ui/src/lib/run.ts` (add `triggerExplain`)
- Create: `ui/src/app/api/explain/route.ts` (clone of tailor route calling `triggerExplain`)

- [ ] Implement both (no UI test framework; `npm run lint && npm run build` is the gate)
- [ ] Commit `feat(ui): explain-job trigger route`

### Task 6: hover card + pinned panel

**Files:**
- Create: `ui/src/lib/word-diff.ts` (LCS word diff → `{text, added}[]`)
- Create: `ui/src/components/ats-report.tsx` (`AtsBadge`: hover summary card, click-pinned portal panel, fetches `/api/reports?kind=tailor&key=<id>` lazily, caches; sections: pulled-from-JD, keyword table with `#:~:text=` source links, highlighted diff, rationale, ATS bars, PDF links, "Generate report" button posting to `/api/explain` when no tailor report exists)
- Modify: `ui/src/components/jobs-table.tsx` ATS cell → `<AtsBadge job={j} />`

- [ ] Implement; `npm run lint && npm run build` pass
- [ ] Commit `feat(ui): ATS hover card + pinned transparency panel`

### Task 7: config, IAM, deploy, verify

- [ ] `private/profile.yaml`: `tailoring: {auto_threshold: 75, max_per_run: 30}`; `gcloud secrets versions add JOBPILOT_PROFILE --data-file=private/profile.yaml`
- [ ] Verify UI override permission: `jobpilot-ui` SA needs `run.developer` on the job for v2 overrides (same as BL-21) — check whether ✨Tailor 403s today; grant with user's OK if needed
- [ ] Push → CI deploy both; trigger `--tailor-job` on one queued Fit≥75 job; open console, verify hover/pin/diff/links
- [ ] Update `docs/gcp-setup.md` Reports note + memory

## Self-review

- Spec coverage: report generation (T1/T3), diff PDF (T2), legacy (T4), UI (T5/T6), config+deploy (T7) ✓
- Types consistent: `TransparencyReport`/`KeywordFate` used in T3/T4; `assemble_report(tr, diffs, diff_pdf, ats)` signature matches call sites ✓
- No placeholders except `PROMPT = """..."""` which Task 1 implementation fills (full prompt text written at implementation time by design — it must reference the exact JSON schema field names defined in the same file)
