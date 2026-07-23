import re
from datetime import datetime, timezone

import httpx

import jobpilot.knowledge as kn
from tests.test_sources import make_cfg

NOW = datetime(2026, 6, 12, 12, 0, tzinfo=timezone.utc)


def test_github_user_parsed_from_profile_link():
    cfg = make_cfg()
    assert kn._github_user(cfg) == "janedoe"


def test_profile_section_has_constraints():
    s = kn.profile_section(make_cfg())
    assert "Needs visa sponsorship: True" in s
    assert "Jane Doe Candidate" in s


def test_resumes_section_renders_single_aie_master():
    # Single-master mode: the pack grounds on the one AIE base under a single
    # accurate header, not four identical variant sections.
    s = kn.resumes_section()
    assert "Master resume (AIE)" in s
    assert s.count("factual source of truth") == 1
    for v in ("Resume variant FDE", "Resume variant MLE", "Resume variant SDE"):
        assert v not in s


def test_github_section_skips_forks_and_caps(httpx_mock):
    repos = [
        {"name": "rag-pipeline", "language": "Python", "stargazers_count": 5,
         "description": "RAG on GCP", "fork": False, "pushed_at": "2026-06-01"},
        {"name": "forked-thing", "fork": True, "stargazers_count": 99,
         "pushed_at": "2026-06-02"},
    ]
    httpx_mock.add_response(url=re.compile(r".*api\.github\.com/users/janedoe/repos.*"),
                            json=repos)
    httpx_mock.add_response(
        url=re.compile(r".*raw\.githubusercontent\.com/janedoe/rag-pipeline.*"),
        text="# RAG pipeline\nProduction retrieval.")
    s = kn.github_section(make_cfg(), httpx.Client())
    assert "rag-pipeline" in s and "Production retrieval." in s
    assert "forked-thing" not in s


def test_refresh_degrades_per_section_and_writes(monkeypatch):
    import jobpilot.sheets as sh

    written = {}
    monkeypatch.setattr(sh, "write_knowledge",
                        lambda c, s, sections, ts: written.update(sections))
    monkeypatch.setattr(kn, "github_section",
                        lambda cfg, client: (_ for _ in ()).throw(RuntimeError("rate limit")))
    monkeypatch.setattr(kn, "portfolio_section", lambda cfg, client: "portfolio text")

    notes = kn.refresh("creds", "sid", make_cfg(), NOW)
    assert written["portfolio"] == "portfolio text"
    assert written["profile"]  # built
    assert any("github: FAILED" in n for n in notes)
