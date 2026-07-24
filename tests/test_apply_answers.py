# tests/test_apply_answers.py
from __future__ import annotations

from jobpilot.apply import answers as an
from jobpilot.apply import plan as pl
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


def _no_llm(p: str) -> str:
    raise AssertionError("llm must not be called")


# --- Bug 1: realistic legal/sensitive phrasings must lock from the profile ---

def test_work_auth_realistic_phrasing_locks_without_llm():
    q = pl.Question(label="Are you over the age of 18?", kind="boolean")
    out = an.answer_question(q, "jd", _resolved(), "", llm=_no_llm)
    assert out == "Yes"


def test_eligible_to_work_phrasing_locks_without_llm():
    q = pl.Question(label="Are you legally eligible to work in the United States?",
                    kind="boolean")
    out = an.answer_question(q, "jd", _resolved(), "", llm=_no_llm)
    assert out == "Yes"  # authorized_to_work_us True


def test_visa_status_phrasing_locks_to_work_authorization_text():
    q = pl.Question(label="What is your current visa status?", kind="text")
    out = an.answer_question(q, "jd", _resolved(), "", llm=_no_llm)
    assert out == "F-1 STEM OPT"  # verbatim work_authorization value


def test_immigration_support_phrasing_locks_to_sponsorship_yes():
    q = pl.Question(
        label="Do you now or will you in the future need immigration support "
              "to work in the US?",
        kind="boolean")
    out = an.answer_question(q, "jd", _resolved(), "", llm=_no_llm)
    assert out == "Yes"  # requires_sponsorship True


def test_age_phrasing_locks_to_over_18_yes():
    q = pl.Question(label="Are you over the age of 18?", kind="boolean")
    out = an.answer_question(q, "jd", _resolved(), "", llm=_no_llm)
    assert out == "Yes"  # over_18 True


# --- Bug 2: ambiguous single-word categories must not hijack free text ---

def test_race_word_in_behavioral_question_falls_through_to_llm():
    q = pl.Question(label="Describe a time when you had to race against a "
                          "tight deadline.", kind="textarea")
    out = an.answer_question(q, "jd", _resolved(), "",
                             llm=lambda p: "a real written answer")
    assert out == "a real written answer"
    assert out not in ("Prefer not to say", "Yes", "No")


def test_sponsor_word_in_behavioral_question_falls_through_to_llm():
    q = pl.Question(label="Tell us about a time you were a sponsor or champion "
                          "for a junior colleague.", kind="textarea")
    out = an.answer_question(q, "jd", _resolved(), "",
                             llm=lambda p: "a real written answer")
    assert out == "a real written answer"
    assert out not in ("Prefer not to say", "Yes", "No")


def test_genuine_eeo_race_question_still_locks_to_profile():
    q = pl.Question(label="Race/Ethnicity", kind="eeo")
    out = an.answer_question(q, "jd", _resolved(), "", llm=_no_llm)
    assert out == "Prefer not to say"


def test_genuine_eeo_race_question_locks_with_select_kind_too():
    q = pl.Question(label="Race/Ethnicity", kind="select")
    out = an.answer_question(q, "jd", _resolved(), "", llm=_no_llm)
    assert out == "Prefer not to say"
