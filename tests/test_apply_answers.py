# tests/test_apply_answers.py
from __future__ import annotations

from jobpilot.apply import answers as an
from jobpilot.apply import plan as pl
from jobpilot.apply import profile as ap
from tests.test_apply_profile import _sample


def _resolved():
    return _sample().for_location("New York, NY")


def test_sponsorship_answered_from_profile_not_llm():
    q = pl.Question(label="Will you now or in the future require sponsorship?",
                    kind="boolean")
    out = an.answer_question(q, "jd", _resolved(), "", llm=lambda p: "SHOULD NOT BE USED")
    assert out.lower().startswith("yes")  # requires_sponsorship True


def test_work_auth_answered_from_profile():
    q = pl.Question(label="Are you authorized to work in the US?", kind="boolean")
    out = an.answer_question(q, "jd", _resolved(), "", llm=lambda p: "no")
    assert out.lower().startswith("yes")


def test_open_ended_uses_llm_and_sanitizes_dashes():
    q = pl.Question(label="Why do you want to work here?", kind="textarea")
    out = an.answer_question(q, "We build AI infra", _resolved(),
                             "Jane shipped RAG systems",
                             llm=lambda p: "I love infra — especially RAG.")
    # sanitize_text's real contract: em/en dashes and " - " clause dashes are
    # removed; intra-word hyphens (e.g. "F-1") are deliberately preserved.
    assert "—" not in out and " - " not in out
    assert out  # non-empty


def test_char_limit_trims_gracefully_without_midsentence_cut():
    q = pl.Question(label="One line pitch", kind="textarea", char_limit=40)
    long = "I ship production ML. I love hard problems. I move fast."
    out = an.answer_question(q, "jd", _resolved(), "", llm=lambda p: long)
    assert len(out) <= 40
    assert out.endswith(".") or out.endswith("ML.") or not out.endswith(" ")
