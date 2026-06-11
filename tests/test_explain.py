import json

import pytest

from jobpilot import explain
from jobpilot.explain import (
    KeywordFate,
    TransparencyReport,
    assemble_report,
    build_explain_prompt,
    diff_sections,
    generate_report,
    latexdiff_pdf,
)

BASE_TEX = r"""
\documentclass{article}
\begin{document}
\section{Summary}
Engineer with 2 years building data systems.
\section{Experience}
\entry{Data Engineer}{Acme}{Jan 2024 -- Present}
\begin{itemize}
\item Built pipelines processing 2M rows daily
\end{itemize}
\section{Skills}
Python, SQL
\end{document}
"""

TAILORED_TEX = BASE_TEX.replace(
    "Built pipelines processing 2M rows daily",
    "Built Kafka pipelines processing 2M rows daily with Airflow orchestration",
)


def test_diff_sections_pairs_summary_skills_and_roles():
    out = diff_sections(BASE_TEX, TAILORED_TEX)
    names = [d["section"] for d in out]
    assert any("summary" in n.lower() for n in names)
    assert any("skills" in n.lower() for n in names)
    role = next(d for d in out if "Data Engineer" in d["section"])
    assert "Kafka" in role["tailored"] and "Kafka" not in role["baseline"]


def test_build_explain_prompt_includes_inputs_and_schema_fields():
    p = build_explain_prompt(
        "Acme", "ML Engineer", "We need Kafka and Airflow", "https://x.test/j/1",
        BASE_TEX, TAILORED_TEX, "Dear team", ["Kafka", "Airflow"],
        ["KEYWORDS: missing ['Spark']"],
    )
    for needle in ("Acme", "We need Kafka", "https://x.test/j/1", "jd_quote",
                   "not_addable", "master_suggestions", "Dear team"):
        assert needle in p, needle


def test_generate_report_retries_once_then_raises():
    calls = {"n": 0}

    def bad_llm(prompt):
        calls["n"] += 1
        return "not json"

    with pytest.raises(Exception):
        generate_report("p", bad_llm)
    assert calls["n"] == 2


def test_generate_report_parses_valid():
    tr = TransparencyReport(keywords=[KeywordFate(keyword="Kafka", action="added")])
    out = generate_report("p", lambda p: tr.model_dump_json())
    assert out.keywords[0].keyword == "Kafka"


def test_assemble_report_truncates_diffs_before_quotes():
    tr = TransparencyReport(
        keywords=[KeywordFate(keyword="k", action="added", jd_quote="q" * 200)])
    huge_diffs = [{"section": "s", "baseline": "b" * 30000, "tailored": "t" * 30000}]
    s = assemble_report(tr, huge_diffs, "https://drive/x", {"score": 91.0}, "tex")
    assert len(s) <= explain.MAX_REPORT_CHARS
    parsed = json.loads(s)
    assert parsed["ats"]["score"] == 91.0
    assert parsed["diff_pdf"] == "https://drive/x"
    assert parsed["precision"] == "tex"
    assert parsed["keywords"][0]["jd_quote"]  # quotes survive diff truncation


def test_latexdiff_pdf_none_on_failure(monkeypatch):
    monkeypatch.setattr(explain.subprocess, "run",
                        lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))
    assert latexdiff_pdf(BASE_TEX, TAILORED_TEX, "j") is None


def test_latexdiff_pdf_compiles_marked_tex(monkeypatch):
    class R:
        returncode = 0
        stdout = r"\DIFadd{Kafka} marked tex"

    monkeypatch.setattr(explain.subprocess, "run", lambda *a, **k: R())
    monkeypatch.setattr(explain, "compile_pdf", lambda tex, name: (b"%PDF", 1))
    assert latexdiff_pdf(BASE_TEX, TAILORED_TEX, "j") == b"%PDF"


def test_explain_job_row_reconstructs_from_pdfs(monkeypatch):
    from datetime import datetime, timezone

    import jobpilot.sheets as sh

    reports = []
    monkeypatch.setattr(sh, "append_report",
                        lambda c, s, kind, key, score, js, ts: reports.append((kind, key, js)))
    monkeypatch.setattr(explain, "compile_pdf", lambda tex, name: (b"%PDF", 1))
    monkeypatch.setattr(explain, "_drive_pdf_text", lambda creds, url: "tailored Kafka text")
    monkeypatch.setattr(explain, "_pdf_text", lambda b: "baseline text")
    monkeypatch.setattr(explain, "generate_report",
                        lambda p, llm: TransparencyReport(resume_rationale="legacy"))

    row = {"_row": 5, "Company": "Acme", "Title": "MLE", "Job ID": "abc",
           "Resume variant": "MLE", "JD excerpt": "desc", "URL": "https://x",
           "JD keywords": "Kafka, Airflow", "Resume ATS": "88",
           "Tailored resume": "https://drive.google.com/file/d/FILE123/view"}
    note = explain.explain_job_row("creds", "sid", row, None, lambda p: "{}",
                                   datetime(2026, 6, 11, tzinfo=timezone.utc))
    assert note.startswith("explained:")
    kind, key, js = reports[0]
    assert (kind, key) == ("tailor", "abc")
    parsed = json.loads(js)
    assert parsed["precision"] == "pdf"
    assert parsed["ats"]["score"] == 88.0


def test_explain_job_row_requires_tailored_url():
    from datetime import datetime, timezone

    note = explain.explain_job_row(
        "creds", "sid",
        {"Company": "Acme", "Title": "MLE", "Job ID": "a", "Tailored resume": ""},
        None, None, datetime(2026, 6, 11, tzinfo=timezone.utc))
    assert "FAILED" in note
