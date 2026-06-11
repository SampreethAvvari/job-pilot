"""Judge-driven rewrite loop: generate, score, feed violations back, keep the best.

Used by per-job tailoring and master-resume regeneration. Up to max_attempts
rewrites; stops early when the gate passes; the highest-scoring attempt wins.
"""

from __future__ import annotations

import json
from typing import Callable

from jobpilot.judge import judge, passes
from jobpilot.latexpdf import compile_pdf

REWRITE_RULES = """
HARD STYLE RULES (the scorer enforces all of these):
- Every bullet <= 26 words, opens with a strong past-tense action verb, and carries a
  concrete number or metric. No verb may open more than 2 bullets.
- NO em dashes or en dashes anywhere; use commas, colons, or periods. No hyphenated
  asides. Write like a careful human, not a model.
- Banned: "responsible for", "worked on", "helped", "leveraged", "utilized",
  buzzwords (robust, scalable, innovative, cutting-edge, passionate, dynamic),
  filler (successfully, various, efficiently), personal pronouns, passive voice.
- Keep evidence of leadership (led/managed/mentored), communication (stakeholders,
  presented, CEO/clients), and collaboration (partnered/coordinated) IF the source
  material truthfully supports it. Never invent facts.
- Exactly one page. Summary 25-65 words with at least one concrete number.
"""


def best_of_attempts(
    initial_tex: str,
    keywords: list[str],
    regenerate: Callable[[str, list[str]], str],
    jobname: str,
    max_attempts: int = 10,
    min_score: float = 90.0,
) -> tuple[str, bytes, dict, int]:
    """Iterate: judge -> regenerate(prev_tex, issues) -> compile -> judge.

    Returns (tex, pdf_bytes, report, attempts_used) for the BEST attempt.
    `regenerate` gets the previous tex and the judge issues and returns new tex.
    """
    best: tuple[float, str, bytes, dict] | None = None
    tex = initial_tex
    attempts = 0
    issues: list[str] = []
    for attempt in range(1, max_attempts + 1):
        attempts = attempt
        if attempt > 1:
            tex = regenerate(best[1] if best else tex, issues)
        try:
            pdf, _pages = compile_pdf(tex, jobname)
        except Exception as exc:  # compile failure: report as issues, try again
            issues = [f"LATEX: compile failed: {exc}"]
            continue
        report = judge(tex, pdf, keywords)
        if best is None or report["score"] > best[0]:
            best = (report["score"], tex, pdf, report)
        issues = report["issues"]
        if passes(report, min_score):
            break
    if best is None:
        raise RuntimeError(f"all {max_attempts} attempts failed to compile")
    score, tex, pdf, report = best
    report["attempts"] = attempts
    return tex, pdf, report, attempts


def report_json(report: dict) -> str:
    return json.dumps({
        "score": report["score"],
        "breakdown": report["breakdown"],
        "keyword_coverage": report["keyword_coverage"],
        "pages": report["pages"],
        "words": report["words"],
        "attempts": report.get("attempts", 1),
        "issues": report["issues"][:60],
    }, ensure_ascii=False)
