"""Answer engine: locked deterministic answers + LLM open-ended screeners, all
run through the no-dash sanitizer. Cover letter lives in cover.py (Task 5)."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from jobpilot.apply.plan import Question
from jobpilot.apply.profile import ResolvedProfile
from jobpilot.company_outreach import sanitize_text

PROMPT = Path(__file__).parent.parent / "prompts" / "apply_answer_v1.txt"

_YES = "Yes"
_NO = "No"


def _is(label: str, *needles: str) -> bool:
    lo = label.lower()
    return any(n in lo for n in needles)


def _locked_answer(q: Question, profile: ResolvedProfile, jd: str) -> str | None:
    """Return a verbatim locked answer, or None if this is an open-ended screener."""
    lbl = q.label
    idn = profile.identity
    if _is(lbl, "sponsor"):
        return _YES if idn.requires_sponsorship else _NO
    if _is(lbl, "authorized to work", "legally authorized", "work authorization"):
        return idn.work_authorization if _is(lbl, "status") else (
            _YES if idn.authorized_to_work_us else _NO)
    if _is(lbl, "18 years", "over 18", "at least 18"):
        return _YES if idn.over_18 else _NO
    if _is(lbl, "gender"):
        return profile.eeo.gender
    if _is(lbl, "race", "ethnicity"):
        return profile.eeo.race_ethnicity
    if _is(lbl, "veteran"):
        return profile.eeo.veteran_status
    if _is(lbl, "disab"):
        return profile.eeo.disability_status
    if _is(lbl, "hispanic", "latino"):
        return _YES if profile.eeo.hispanic_latino else _NO
    if _is(lbl, "salary", "compensation expectation", "expected pay", "desired salary"):
        wants_number = q.kind in ("text", "number") or _is(lbl, "number", "amount")
        return profile.compensation.salary_answer(jd, wants_number)
    if _is(lbl, "how did you hear", "how you heard", "referral source"):
        return profile.compensation.how_did_you_hear
    if _is(lbl, "relocat"):
        return _YES if profile.compensation.willing_to_relocate else _NO
    if _is(lbl, "start date", "earliest start", "available to start"):
        return profile.compensation.earliest_start
    if _is(lbl, "notice period"):
        return profile.compensation.notice_period
    return None


def _graceful_trim(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit]
    for sep in (". ", "! ", "? "):
        i = cut.rfind(sep)
        if i >= limit // 2:
            return cut[: i + 1].strip()
    i = cut.rfind(" ")
    return (cut[:i] if i > 0 else cut).strip()


def answer_question(q: Question, jd: str, profile: ResolvedProfile, knowledge: str,
                    llm: Callable[[str], str]) -> str:
    locked = _locked_answer(q, profile, jd)
    if locked is not None:
        return locked
    limit_line = (f"- Keep the answer under {q.char_limit} characters, complete and "
                  "self-contained." if q.char_limit else "")
    prompt = PROMPT.read_text(encoding="utf-8").format(
        limit_line=limit_line, knowledge=knowledge or "(no extra background)",
        jd=(jd or "")[:4000], question=q.label)
    try:
        raw = llm(prompt)
    except Exception:  # noqa: BLE001 — no answer beats a wrong/injected one
        return ""
    out = sanitize_text(raw).strip()
    if q.char_limit and len(out) > q.char_limit:
        try:
            shorter = sanitize_text(llm(prompt + f"\n\nToo long. Rewrite in under "
                                        f"{q.char_limit} characters.")).strip()
            if len(shorter) <= q.char_limit:
                return shorter
        except Exception:  # noqa: BLE001
            pass
        return _graceful_trim(out, q.char_limit)
    return out
