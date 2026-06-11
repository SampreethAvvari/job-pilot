import json
from datetime import datetime, timezone

import pytest

from jobpilot.latexpdf import CompileError
from jobpilot.tailor import VARIANT_FILES, RESUME_DIR, _build_prompt, generate
from tests.test_sources import make_cfg

NOW = datetime(2026, 6, 11, 15, 0, tzinfo=timezone.utc)


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


JUDGE_REPORT = {"score": 92.0, "breakdown": {}, "keyword_coverage": 0.9,
                "pages": 1, "words": 500, "issues": [], "attempts": 1}
ROW = {"_row": 2, "Company": "Acme", "Title": "MLE", "Job ID": "abc",
       "JD excerpt": "We need RAG", "Resume variant": "MLE", "URL": "https://x.test/j"}


def _patch_tailor_io(monkeypatch, reports, uploads):
    import jobpilot.rewrite_loop as rl
    import jobpilot.sheets as sh
    import jobpilot.tailor as t

    monkeypatch.setattr(rl, "best_of_attempts",
                        lambda *a, **k: ("TEX", b"%PDF", dict(JUDGE_REPORT), 1))
    monkeypatch.setattr(t, "compile_pdf", lambda tex, name: (b"%PDF", 1))
    monkeypatch.setattr(t, "_drive", lambda c: None)
    monkeypatch.setattr(t, "_ensure_folder", lambda d, n, p=None: "folder")
    monkeypatch.setattr(
        t, "upload_pdf",
        lambda c, f, n, b: uploads.append(n) or f"https://drive/{n}")
    monkeypatch.setattr(sh, "update_cells", lambda c, s, u: None)
    monkeypatch.setattr(
        sh, "append_report",
        lambda c, s, kind, key, score, js, ts: reports.append((kind, key, js)))


def test_tailor_row_appends_transparency_report(monkeypatch):
    import jobpilot.explain as ex
    import jobpilot.tailor as t

    reports, uploads = [], []
    _patch_tailor_io(monkeypatch, reports, uploads)
    monkeypatch.setattr(ex, "latexdiff_pdf", lambda b, new, n: b"%DIFF")
    monkeypatch.setattr(ex, "generate_report",
                        lambda p, llm: ex.TransparencyReport(resume_rationale="why"))

    note = t.tailor_row("creds", "sid", dict(ROW), make_cfg(),
                        lambda p: valid_payload(), NOW)
    assert note.startswith("tailored:")
    assert [r[0] for r in reports] == ["job", "tailor"]
    assert reports[1][1] == "abc"
    parsed = json.loads(reports[1][2])
    assert parsed["resume_rationale"] == "why"
    assert parsed["diff_pdf"].endswith("_diff.pdf")
    assert "Acme_MLE_diff.pdf" in uploads


def test_tailor_row_survives_explain_failure(monkeypatch):
    import jobpilot.explain as ex
    import jobpilot.tailor as t

    reports, uploads = [], []
    _patch_tailor_io(monkeypatch, reports, uploads)
    monkeypatch.setattr(ex, "latexdiff_pdf", lambda b, new, n: None)

    def boom(p, llm):
        raise RuntimeError("llm down")

    monkeypatch.setattr(ex, "generate_report", boom)
    note = t.tailor_row("creds", "sid", dict(ROW), make_cfg(),
                        lambda p: valid_payload(), NOW)
    assert note.startswith("tailored:")  # tailoring still succeeds
    assert "report FAILED" in note  # ...but the failure is visible (BL-18)
    assert [r[0] for r in reports] == ["job"]
