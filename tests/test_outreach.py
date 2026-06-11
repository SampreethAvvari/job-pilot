import json
import re

import httpx
import pytest

from jobpilot.apollo import find_contacts, linkedin_people_search_url
from jobpilot.outreach import draft_outreach, signature
from tests.test_sources import make_cfg

ROW = {
    "_row": 5, "Job ID": "abc", "Company": "Acme", "Title": "AI Engineer",
    "JD excerpt": "Build LLM systems with RAG on GCP", "Status": "Applied",
    "Tailored resume": "https://drive.google.com/file/d/F1/view",
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
    assert "Jane Doe Candidate" in seen["p"]  # the candidate's own name reaches the LLM
    assert "revenue" in seen["p"].lower()  # the no-business-metrics rule is in the prompt


def test_draft_outreach_fails_after_retries():
    cfg = make_cfg()
    with pytest.raises(RuntimeError):
        draft_outreach(ROW, cfg, lambda p: "garbage", None)


def test_signature_has_name_and_links():
    cfg = make_cfg()
    s = signature(cfg.profile)
    assert "Jane Doe Candidate" in s
    assert "https://janedoe.dev" in s
    assert "https://linkedin.com/in/janedoe" in s
    assert "https://github.com/janedoe" in s


def test_signature_skips_empty_links():
    cfg = make_cfg()
    cfg.profile.portfolio = ""
    s = signature(cfg.profile)
    assert "Portfolio" not in s and "Jane Doe Candidate" in s


def test_apollo_skipped_without_key(monkeypatch):
    monkeypatch.delenv("APOLLO_API_KEY", raising=False)
    assert find_contacts("Acme", httpx.Client()) == []


def test_apollo_plan_limit_degrades(monkeypatch, httpx_mock):
    monkeypatch.setenv("APOLLO_API_KEY", "k")
    httpx_mock.add_response(method="POST", url=re.compile(r".*apollo.*"), status_code=403)
    assert find_contacts("Acme", httpx.Client()) == []


def test_apollo_uses_api_search_and_reveals_email(monkeypatch, httpx_mock):
    # search returns locked person (no name/email on free tier); match reveals both
    monkeypatch.setenv("APOLLO_API_KEY", "k")
    httpx_mock.add_response(
        method="POST", url=re.compile(r".*mixed_people/api_search.*"),
        json={"people": [{"id": "p1", "name": None, "title": "Recruiter",
                          "email": None, "linkedin_url": None}]},
    )
    httpx_mock.add_response(
        method="POST", url=re.compile(r".*people/match.*"),
        json={"person": {"name": "Reuben R", "email": "reuben@acme.com",
                         "linkedin_url": "li", "title": "Recruiter"}},
    )
    out = find_contacts("Acme", httpx.Client())
    assert out[0]["email"] == "reuben@acme.com" and out[0]["name"] == "Reuben R"


def test_apollo_drops_contacts_without_email(monkeypatch, httpx_mock):
    monkeypatch.setenv("APOLLO_API_KEY", "k")
    httpx_mock.add_response(
        method="POST", url=re.compile(r".*mixed_people/api_search.*"),
        json={"people": [{"id": "p1", "name": "Jane", "title": "Recruiter"}]},
    )
    httpx_mock.add_response(
        method="POST", url=re.compile(r".*people/match.*"),
        json={"person": {"name": "Jane", "email": "email_not_unlocked@domain.com"}},
    )
    assert find_contacts("Acme", httpx.Client()) == []


def test_outreach_row_skips_draft_without_email(monkeypatch):
    import jobpilot.outreach as o
    import jobpilot.sheets as sh

    cells = []
    drafts = []
    monkeypatch.setattr(o, "find_contacts", lambda c, cl, max_contacts=2: [])
    monkeypatch.setattr(o, "create_gmail_draft",
                        lambda *a, **k: drafts.append(a) or "url")
    monkeypatch.setattr(sh, "update_cells", lambda c, s, u: cells.extend(u))

    note = o.outreach_row("creds", "sid", dict(ROW), make_cfg(), None, httpx.Client())
    assert "skipped" in note and "no recruiter email" in note
    assert drafts == []  # NO draft without a recipient email
    assert any("Find people" in c[1] for c in cells)


def test_outreach_row_drafts_with_signature_and_attachment(monkeypatch):
    import jobpilot.outreach as o
    import jobpilot.sheets as sh

    captured = {}

    def fake_create(creds, to, subject, body, attachment=None):
        captured.update(to=to, body=body, attachment=attachment)
        return "https://mail.google.com/draft"

    monkeypatch.setattr(o, "find_contacts", lambda c, cl, max_contacts=2: [
        {"name": "Jane", "title": "Recruiter", "email": "jane@acme.com",
         "linkedin_url": ""}])
    monkeypatch.setattr(o, "create_gmail_draft", fake_create)
    monkeypatch.setattr(o, "_drive_pdf_bytes", lambda creds, url: b"%PDF-resume")
    monkeypatch.setattr(sh, "update_cells", lambda c, s, u: None)

    def llm(p):
        return json.dumps({"subject": "s", "body": "Short technical note."})

    note = o.outreach_row("creds", "sid", dict(ROW), make_cfg(), llm, httpx.Client())
    assert note.startswith("outreach drafted")
    assert captured["to"] == "jane@acme.com"
    assert "Jane Doe Candidate" in captured["body"]  # signature appended
    assert captured["attachment"][1] == b"%PDF-resume"
    assert captured["attachment"][0].endswith(".pdf")


def test_linkedin_search_url():
    assert "linkedin.com/search" in linkedin_people_search_url("Acme Corp")
