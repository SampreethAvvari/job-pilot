import json

import pytest

from jobpilot.latexpdf import CompileError
from jobpilot.tailor import VARIANT_FILES, RESUME_DIR, _build_prompt, generate


def valid_payload():
    return json.dumps({
        "keywords": ["Python", "LLM", "RAG", "GCP"],
        "tailored_tex": "\\documentclass[10pt]{article}\\input{_preamble}...",
        "cover_letter_tex": "\\documentclass[10pt]{article}\\input{_preamble}...",
        "changes": "emphasized RAG",
    })


def test_all_variant_files_exist():
    for f in VARIANT_FILES.values():
        assert (RESUME_DIR / f).exists(), f


def test_prompt_contains_jd_and_resume():
    p = _build_prompt("Acme", "ML Engineer", "We need RAG and Kubernetes", "MLE")
    assert "Acme" in p and "RAG and Kubernetes" in p
    assert "\\name{" in p  # master resume LaTeX embedded
    assert "NEVER invent" in p


def test_resume_env_override(monkeypatch):
    monkeypatch.setenv("RESUME_TEX_MLE", "\\name{REAL PERSON} private content")
    p = _build_prompt("Acme", "ML Engineer", "desc", "MLE")
    assert "REAL PERSON" in p


def test_generate_happy_path():
    out = generate("Acme", "MLE", "desc", "MLE", lambda p: valid_payload())
    assert out.keywords[0] == "Python"
    assert out.tailored_tex.startswith("\\documentclass")


def test_generate_retries_then_fails():
    calls = []

    def bad(p):
        calls.append(1)
        return "not json"

    with pytest.raises(CompileError):
        generate("Acme", "MLE", "desc", "MLE", bad)
    assert len(calls) == 2
