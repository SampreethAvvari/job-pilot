"""Tailoring transparency: keyword provenance, what changed and why, diff artifacts.

One schema-enforced Gemini call AFTER tailoring explains the final artifacts.
Deterministic extras (section diffs, latexdiff PDF) are attached in code so the
UI never has to trust LLM-claimed diffs. Reports persist to the Reports tab
(kind="tailor", key=job id) and render as the dashboard's ATS popup.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Literal

from pydantic import BaseModel, Field

from jobpilot.judge import parse_tex
from jobpilot.latexpdf import compile_pdf

MAX_REPORT_CHARS = 49000  # Reports tab column E budget (sheets.append_report)


class KeywordFate(BaseModel):
    keyword: str
    jd_quote: str = ""  # verbatim JD sentence the keyword came from
    in_baseline: bool = False
    action: Literal["already_present", "added", "not_addable"]
    section: str = ""  # where it was added / lives
    before: str = ""  # the line before the change ("" when newly added)
    after: str = ""  # the line carrying it now
    reason: str = ""  # why added there, or why genuinely not addable


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


PROMPT = """You are auditing how a resume was tailored for one job application. You get the
job description, the BASELINE master resume, the FINAL tailored resume, the cover
letter, the JD keywords the tailor extracted, and the ATS scorer's notes. Explain
the tailoring truthfully — describe only changes that actually appear between
baseline and final.

Return JSON with exactly these fields:
- jd: {{"summary": 2-3 sentences on the role, "requirements": [hard requirements],
  "nice_to_haves": [preferred extras]}} — only what the description actually says.
- keywords: one entry PER extracted keyword:
  {{"keyword", "jd_quote": the verbatim sentence (<=200 chars) from the description
  where this keyword appears or is implied — copy it EXACTLY so it can be located
  on the posting page, "in_baseline": did the baseline resume already contain it,
  "action": "already_present" | "added" | "not_addable",
  "section": resume section involved, "before": the baseline line that changed
  ("" if a new line), "after": the final line carrying the keyword ("" if not
  added), "reason": one sentence — why it was added there, or why it is genuinely
  not addable (not in the candidate's real experience)}}.
- resume_rationale: 3-6 sentences on the overall reshaping strategy.
- cover_rationale: 2-4 sentences on the cover letter's angle.
- master_suggestions: keywords marked not_addable that the candidate could
  legitimately develop or surface in the master resume, phrased as suggestions.

COMPANY: {company}
TITLE: {title}
JOB URL: {job_url}
JOB DESCRIPTION:
{jd_excerpt}

JD KEYWORDS EXTRACTED BY THE TAILOR: {keywords}

BASELINE MASTER RESUME (LaTeX or extracted text):
{baseline}

FINAL TAILORED RESUME (LaTeX or extracted text):
{tailored}

COVER LETTER:
{cover}

ATS SCORER NOTES:
{ats_issues}
"""


def build_explain_prompt(company: str, title: str, jd_excerpt: str, job_url: str,
                         baseline: str, tailored: str, cover: str,
                         keywords: list[str], ats_issues: list[str]) -> str:
    return PROMPT.format(
        company=company, title=title, job_url=job_url,
        jd_excerpt=jd_excerpt[:6000], keywords=json.dumps(keywords),
        baseline=baseline[:12000], tailored=tailored[:12000], cover=cover[:4000],
        ats_issues="\n".join(ats_issues[:25]),
    )


def generate_report(prompt: str, llm: Callable[[str], str]) -> TransparencyReport:
    last: Exception | None = None
    for _ in range(2):
        try:
            return TransparencyReport.model_validate_json(llm(prompt))
        except Exception as exc:  # malformed output — retry once
            last = exc
    raise RuntimeError(f"explain generation failed: {last}")


def _sections_of(tex_or_text: str) -> list[tuple[str, str]]:
    """(section name, plain text) pairs; whole input as one section when not LaTeX."""
    import re

    from jobpilot.judge import detex

    if "\\section" not in tex_or_text:
        return [("Resume", tex_or_text.strip())]
    p = parse_tex(tex_or_text)
    out: list[tuple[str, str]] = []
    if p["summary"]:
        out.append(("Summary", p["summary"]))
    for role in p["roles"]:
        out.append((f"{role['title']} — {role['org']}", "\n".join(role["bullets"])))
    m = re.search(r"\\section\{(Skills[^}]*)\}(.*?)(\\section|\\end\{document\})",
                  tex_or_text, re.S | re.I)
    if m:
        out.append((m.group(1), detex(m.group(2))))
    return out


def diff_sections(baseline: str, tailored: str) -> list[dict]:
    """Deterministic plain-text pairs the UI diffs client-side. Sections are
    matched by name; unmatched ones pair with ''."""
    base = dict(_sections_of(baseline))
    tail = _sections_of(tailored)
    out = []
    seen = set()
    for name, text in tail:
        out.append({"section": name, "baseline": base.get(name, ""), "tailored": text})
        seen.add(name)
    for name, text in base.items():
        if name not in seen:
            out.append({"section": name, "baseline": text, "tailored": ""})
    return out


def assemble_report(tr: TransparencyReport, diffs: list[dict], diff_pdf: str,
                    ats: dict, precision: str = "tex") -> str:
    """Report JSON within the Reports-tab budget: drop diffs first, then quotes."""
    doc = {
        "precision": precision,
        "jd": tr.jd.model_dump(),
        "keywords": [k.model_dump() for k in tr.keywords],
        "resume_rationale": tr.resume_rationale,
        "cover_rationale": tr.cover_rationale,
        "master_suggestions": tr.master_suggestions,
        "diff_sections": diffs,
        "diff_pdf": diff_pdf,
        "ats": ats,
    }
    s = json.dumps(doc, ensure_ascii=False)
    if len(s) > MAX_REPORT_CHARS:
        budget = MAX_REPORT_CHARS - (len(s) - sum(
            len(d["baseline"]) + len(d["tailored"]) for d in doc["diff_sections"]))
        kept: list[dict] = []
        for d in doc["diff_sections"]:
            cost = len(d["baseline"]) + len(d["tailored"])
            if cost <= budget:
                kept.append(d)
                budget -= cost
        doc["diff_sections"] = kept
        s = json.dumps(doc, ensure_ascii=False)
    if len(s) > MAX_REPORT_CHARS:
        for k in doc["keywords"]:
            k["jd_quote"] = k["jd_quote"][:120]
            k["before"] = k["before"][:160]
            k["after"] = k["after"][:160]
        s = json.dumps(doc, ensure_ascii=False)
    return s[:MAX_REPORT_CHARS]


def latexdiff_pdf(baseline_tex: str, tailored_tex: str, jobname: str) -> bytes | None:
    """Highlighted diff PDF (additions underlined, deletions struck); None on any
    failure — the popup's text diff covers when latexdiff can't."""
    try:
        with tempfile.TemporaryDirectory() as td:
            old, new = Path(td, "old.tex"), Path(td, "new.tex")
            old.write_text(baseline_tex, encoding="utf-8")
            new.write_text(tailored_tex, encoding="utf-8")
            res = subprocess.run(
                ["latexdiff", "--type=UNDERLINE", str(old), str(new)],
                capture_output=True, text=True, timeout=60,
            )
            if res.returncode != 0 or not res.stdout.strip():
                return None
            pdf, _pages = compile_pdf(res.stdout, jobname)
            return pdf
    except Exception:  # noqa: BLE001 — strictly best-effort
        return None


def explain_job_row(creds, spreadsheet_id: str, row: dict, cfg,
                    llm: Callable[[str], str], now) -> str:
    """Legacy backfill: reconstruct a report from the stored PDFs (--explain-job).

    Pre-feature rows never saved their tailored tex, so precision is 'pdf':
    text extracted from the Drive PDF vs the compiled baseline master.
    """
    import io
    import re

    from googleapiclient.discovery import build as gbuild
    from pypdf import PdfReader

    from jobpilot import sheets
    from jobpilot.tailor import _resume_tex

    company, title = row["Company"], row["Title"]
    try:
        m = re.search(r"/d/([\w-]+)", row.get("Tailored resume", ""))
        if not m:
            return f"explain FAILED for {company}: no tailored resume URL"
        drive = gbuild("drive", "v3", credentials=creds, cache_discovery=False)
        blob = drive.files().get_media(fileId=m.group(1)).execute()
        tailored_text = " ".join(
            pg.extract_text() or "" for pg in PdfReader(io.BytesIO(blob)).pages)

        variant = row.get("Resume variant") or "FDE"
        base_tex = _resume_tex(variant)
        base_pdf, _ = compile_pdf(base_tex, f"{variant}_baseline")
        baseline_text = " ".join(
            pg.extract_text() or "" for pg in PdfReader(io.BytesIO(base_pdf)).pages)

        keywords = [k.strip() for k in (row.get("JD keywords") or "").split(",") if k.strip()]
        prompt = build_explain_prompt(
            company, title, row.get("JD excerpt") or "", row.get("URL", ""),
            baseline_text, tailored_text, "(cover letter not stored)", keywords, [])
        tr = generate_report(prompt, llm)
        diffs = diff_sections(baseline_text, tailored_text)
        ats = {"score": float(row["Resume ATS"])} if row.get("Resume ATS") else {}
        sheets.append_report(creds, spreadsheet_id, "tailor", row["Job ID"],
                             ats.get("score", 0), assemble_report(tr, diffs, "", ats, "pdf"),
                             now.strftime("%Y-%m-%d %H:%M"))
        return f"explained: {company} — {title} (from PDFs)"
    except Exception as exc:  # noqa: BLE001 — report-only path, never fatal
        return f"explain FAILED for {company} — {title}: {type(exc).__name__}: {exc}"
