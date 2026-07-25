"""Browserless fill orchestrator: ties the profile, answer engine, and cover
letter together into a populated ApplicationPlan. Pure logic - no browser, no
Sheet writes, no Drive (the caller persists what this returns). The ATS
adapters (Phase 3) supply the real question list; here it is passed in and
tested with synthetic sets. Spec: docs/superpowers/specs/2026-07-24-auto-apply-design.md
"""

from __future__ import annotations

from typing import Callable

from jobpilot.apply import answers, cover
from jobpilot.apply.plan import ApplicationPlan, Question
from jobpilot.apply.profile import ApplicationProfile


def _field(job: dict, *keys: str) -> str:
    """Defensive accessor: supports both Sheet header-cased keys ("Job ID",
    "JD excerpt") and lower-case keys ("job_id", "jd"), trying each in order."""
    for key in keys:
        val = job.get(key)
        if val:
            return val
    return ""


def build_plan(job: dict, questions: list[Question], app_profile: ApplicationProfile,
               knowledge: str, llm: Callable[[str], str], now) -> ApplicationPlan:
    """Resolve the location profile, answer every question (locked + LLM),
    generate the cover letter text, and return a populated ApplicationPlan with
    status set by the truthfulness gate (next_status_after_fill).

    `now` is accepted for interface symmetry with the caller's other build
    steps; this function does not stamp a timestamp onto the plan itself (the
    caller records `Updated` when it persists to the Applications Sheet tab).
    """
    del now  # unused here; caller stamps Updated on persist

    job_id = _field(job, "job_id", "Job ID")
    company = _field(job, "company", "Company")
    title = _field(job, "title", "Title")
    location = _field(job, "location", "Location")
    jd = _field(job, "jd", "JD excerpt", "description")
    ats = _field(job, "ats", "ATS")

    resolved = app_profile.for_location(location)

    for q in questions:
        q.answer = answers.answer_question(q, jd, resolved, knowledge, llm)

    cover_text = cover.cover_letter_text(company, title, jd, resolved, knowledge, llm)

    plan = ApplicationPlan(
        job_id=job_id, company=company, title=title, ats=ats,
        location_key=resolved.location_key, cover_letter_text=cover_text,
        questions=questions,
    )
    plan.status = plan.next_status_after_fill()
    return plan
