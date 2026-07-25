# tests/test_apply_cover.py
from __future__ import annotations

from jobpilot.apply import cover
from tests.test_apply_profile import _sample


def test_cover_text_is_sanitized_and_grounded():
    text = cover.cover_letter_text(
        "Acme", "AI Engineer", "We build RAG infra", _sample().for_location("NY"),
        "Jane shipped a RAG platform with citations",
        llm=lambda p: "I would love to help — I shipped RAG at Acme Robotics.")
    assert "—" not in text
    assert text.strip()


def test_cover_text_degrades_to_empty_on_llm_error():
    def boom(p):
        raise RuntimeError("no llm")
    text = cover.cover_letter_text("Acme", "AIE", "jd", _sample().for_location("NY"),
                                   "", llm=boom)
    assert text == ""
