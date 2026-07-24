# tests/test_apply_engine.py
from __future__ import annotations

from jobpilot.apply import engine
from jobpilot.apply import plan as pl
from tests.test_apply_profile import _sample

# Header-cased keys, matching how sheets.read_rows keys a Jobs row.
JOB = {
    "Job ID": "job-1",
    "Company": "Acme Robotics",
    "Title": "AI Engineer",
    "Location": "New York, NY",
    "JD excerpt": "We build production RAG systems for robotics.",
    "ATS": "greenhouse",
}

BESPOKE_LABEL = "Describe your experience holding a Q clearance"


def _llm(prompt: str) -> str:
    if BESPOKE_LABEL in prompt:
        return ""
    return "I would love to help — I shipped RAG systems at Acme Robotics."


def test_locked_question_answered_from_profile_not_llm():
    questions = [pl.Question(
        label="Will you now or in the future require sponsorship?", kind="boolean")]
    plan = engine.build_plan(JOB, questions, _sample(), "Jane shipped RAG systems",
                             _llm, "2026-07-24")
    assert plan.questions[0].answer == "Yes"  # from profile, not the llm


def test_open_ended_filled_from_llm_and_sanitized():
    questions = [pl.Question(label="Why do you want to work here?", kind="textarea")]
    plan = engine.build_plan(JOB, questions, _sample(), "Jane shipped RAG systems",
                             _llm, "2026-07-24")
    out = plan.questions[0].answer
    assert out
    assert "—" not in out and " - " not in out


def test_unanswerable_required_question_lands_needs_input():
    questions = [
        pl.Question(label="Will you now or in the future require sponsorship?",
                    kind="boolean"),
        pl.Question(label=BESPOKE_LABEL, kind="textarea", required=True),
    ]
    plan = engine.build_plan(JOB, questions, _sample(), "", _llm, "2026-07-24")
    assert plan.questions[1].answer == ""
    assert plan.status == "needs_input"


def test_all_answerable_lands_needs_review():
    questions = [
        pl.Question(label="Will you now or in the future require sponsorship?",
                    kind="boolean"),
        pl.Question(label="Why do you want to work here?", kind="textarea"),
    ]
    plan = engine.build_plan(JOB, questions, _sample(), "Jane shipped RAG systems",
                             _llm, "2026-07-24")
    assert plan.status == "needs_review"


def test_no_answer_contains_a_dash():
    questions = [
        pl.Question(label="Will you now or in the future require sponsorship?",
                    kind="boolean"),
        pl.Question(label="Why do you want to work here?", kind="textarea"),
    ]
    plan = engine.build_plan(JOB, questions, _sample(), "Jane shipped RAG systems",
                             _llm, "2026-07-24")
    for q in plan.questions:
        assert "—" not in q.answer and "–" not in q.answer


def test_cover_letter_text_is_generated_stored_and_sanitized():
    plan = engine.build_plan(JOB, [], _sample(), "Jane shipped RAG systems",
                             _llm, "2026-07-24")
    assert plan.cover_letter_text
    assert "—" not in plan.cover_letter_text


def test_plan_carries_job_identity_and_location():
    plan = engine.build_plan(JOB, [], _sample(), "", _llm, "2026-07-24")
    assert plan.job_id == "job-1"
    assert plan.company == "Acme Robotics"
    assert plan.title == "AI Engineer"
    assert plan.ats == "greenhouse"
    assert plan.location_key == "ny"


def test_bay_area_job_resolves_bay_area_location_key():
    job = dict(JOB, Location="Sunnyvale, CA")
    plan = engine.build_plan(job, [], _sample(), "", _llm, "2026-07-24")
    assert plan.location_key == "bay_area"


def test_build_plan_is_pure_no_leftover_questions_mutation_surprises():
    # Passing lower-case keys (an alternate accessor style) also works.
    job = {"job_id": "job-2", "company": "Beta", "title": "Eng", "location": "NY",
           "jd": "desc", "ats": "lever"}
    plan = engine.build_plan(job, [], _sample(), "", _llm, "2026-07-24")
    assert plan.job_id == "job-2" and plan.company == "Beta" and plan.ats == "lever"
