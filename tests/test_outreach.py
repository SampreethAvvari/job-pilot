import json
import re

import httpx
import pytest

from jobpilot.apollo import find_contacts, linkedin_people_search_url
from jobpilot.outreach import draft_outreach
from tests.test_sources import make_cfg

ROW = {
    "_row": 5, "Job ID": "abc", "Company": "Acme", "Title": "AI Engineer",
    "JD excerpt": "Build LLM systems with RAG on GCP", "Status": "Applied",
}


def test_draft_outreach_happy_path():
    cfg = make_cfg()
    seen = {}

    def llm(prompt):
        seen["p"] = prompt
        return json.dumps({"subject": "AI Engineer @ Acme", "body": "Hi — short note."})

    d = draft_outreach(ROW, cfg, llm, {"name": "Jane Doe", "title": "Recruiter"})
    assert d.subject.startswith("AI Engineer")
    assert "Acme" in seen["p"] and "Jane Doe" in seen["p"]
    assert "needs sponsorship" in seen["p"]  # candidate constraints come from the profile


def test_draft_outreach_fails_after_retries():
    cfg = make_cfg()
    with pytest.raises(RuntimeError):
        draft_outreach(ROW, cfg, lambda p: "garbage", None)


def test_apollo_skipped_without_key(monkeypatch):
    monkeypatch.delenv("APOLLO_API_KEY", raising=False)
    assert find_contacts("Acme", httpx.Client()) == []


def test_apollo_plan_limit_degrades(monkeypatch, httpx_mock):
    monkeypatch.setenv("APOLLO_API_KEY", "k")
    httpx_mock.add_response(method="POST", url=re.compile(r".*apollo.*"), status_code=403)
    assert find_contacts("Acme", httpx.Client()) == []


def test_apollo_parses_people(monkeypatch, httpx_mock):
    monkeypatch.setenv("APOLLO_API_KEY", "k")
    httpx_mock.add_response(
        method="POST", url=re.compile(r".*mixed_people/search.*"),
        json={"people": [{"id": "1", "name": "Jane", "title": "Recruiter",
                          "email": "jane@acme.com", "linkedin_url": "li"}]},
    )
    out = find_contacts("Acme", httpx.Client())
    assert out[0]["email"] == "jane@acme.com"


def test_linkedin_search_url():
    assert "linkedin.com/search" in linkedin_people_search_url("Acme Corp")
