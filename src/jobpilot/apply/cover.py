"""Cover letter generation: voice-driven text (LLM, sanitized, no dashes) and a
one-page PDF render. Text-gen is unit-testable without pdflatex; PDF render reuses
company_outreach's LaTeX builder (_cover_tex + latexpdf.compile_pdf) rather than
reimplementing LaTeX. Spec: docs/superpowers/specs/2026-07-24-auto-apply-design.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from jobpilot.apply.profile import ResolvedProfile
from jobpilot.company_outreach import _cover_tex, _latex_escape, sanitize_text

PROMPT = Path(__file__).parent.parent / "prompts" / "apply_cover_v1.txt"


def cover_letter_text(company: str, title: str, jd: str, profile: ResolvedProfile,
                      knowledge: str, llm: Callable[[str], str]) -> str:
    """Voice-driven cover letter body: 3 plain-text paragraphs, sanitized (no
    dashes, no AI-tell), grounded only in `knowledge` + `jd`.

    Returns "" on any LLM error so a broken cover letter never blocks the rest
    of an application.
    """
    name = profile.identity.display_name or profile.identity.legal_name
    prompt = PROMPT.read_text(encoding="utf-8").format(
        name=name, company=company, title=title,
        jd=(jd or "")[:4000], knowledge=knowledge or "(no extra background)")
    try:
        raw = llm(prompt)
    except Exception:  # noqa: BLE001 — no cover letter beats a wrong one
        return ""
    return sanitize_text(raw).strip()


def render_cover_pdf(text: str, profile: ResolvedProfile, company: str) -> bytes:
    """Compile `text` to a one-page cover-letter PDF for `company`.

    Reuses company_outreach._cover_tex + jobpilot.latexpdf.compile_pdf (the same
    path cover_letter_pdf() uses) instead of duplicating the LaTeX. Raises
    latexpdf.CompileError if pdflatex is unavailable or compilation fails; callers
    that want a soft-fail should catch that themselves (see cover_letter_pdf for
    the pattern), since text-gen and PDF render are kept as separate steps here.
    """
    from jobpilot.latexpdf import compile_pdf

    name = profile.identity.legal_name
    links = " \\textbar{} ".join(
        p for p in (profile.identity.portfolio, profile.identity.linkedin,
                    profile.identity.github) if p)
    contact_line = _latex_escape(links) if links else ""
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    tex = _cover_tex(name, contact_line, company, paragraphs)
    pdf, _pages = compile_pdf(tex, f"{company}_cover")
    return pdf
