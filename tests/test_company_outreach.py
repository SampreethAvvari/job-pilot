import json
from datetime import datetime, timezone

import httpx

from jobpilot import company_outreach as co
from tests.test_sources import make_cfg

NOW = datetime(2026, 6, 18, tzinfo=timezone.utc)


def test_sanitize_strips_dashes_but_keeps_word_hyphens():
    out = co.sanitize_text("I build LLM systems — fast - and at scale, end-to-end.")
    assert "—" not in out and " - " not in out
    assert "end-to-end" in out  # intra-word hyphen survives


def test_find_people_links_cover_recruiters_and_managers():
    links = co.find_people_links("Acme Corp")
    labels = [label for label, _ in links]
    assert "recruiter" in labels and "engineering manager" in labels
    assert all(url.startswith("http") for _, url in links)
    assert any("linkedin.com/search" in url for _, url in links)


def test_company_domain_falls_back_to_slug(monkeypatch):
    monkeypatch.setattr(co.sheets, "read_companies", lambda creds, sid: [])
    assert co.company_domain("Acme Corp", None, "sid") == "acmecorp.com"


def test_company_domain_uses_watchlist_careers_host(monkeypatch):
    monkeypatch.setattr(co.sheets, "read_companies", lambda creds, sid: [
        {"Company": "Acme", "Careers URL": "https://www.acme.io/careers"},
    ])
    assert co.company_domain("acme", None, "sid") == "acme.io"


def test_company_domain_ignores_third_party_boards(monkeypatch):
    monkeypatch.setattr(co.sheets, "read_companies", lambda creds, sid: [
        {"Company": "Acme", "Careers URL": "https://boards.greenhouse.io/acme"},
    ])
    assert co.company_domain("acme", None, "sid") == "acme.com"  # falls back to guess


def test_pick_variant_uses_llm_then_defaults():
    assert co.pick_variant("X", lambda p: json.dumps(
        {"variant": "mle", "reason": "ML shop"}))[0] == "MLE"
    assert co.pick_variant("X", lambda p: "garbage")[0] == "AIE"


def test_draft_company_email_sanitizes_body_and_subject():
    cfg = make_cfg()

    def llm(prompt):
        assert "Acme" in prompt and "janedoe.dev" in prompt  # links reach the model
        return json.dumps({"subject": "AI engineer — Acme",
                           "body": "Hi,\n\nI ship ML systems — fast."})

    d = co.draft_company_email("Acme", "AI shop", "", cfg, llm)
    assert "—" not in d.subject and "—" not in d.body


def test_run_creates_pooled_draft_with_resume_and_cover(monkeypatch):
    cfg = make_cfg()
    captured = {}
    appended = {}

    monkeypatch.setattr(co.sheets, "read_companies", lambda creds, sid: [])
    monkeypatch.setattr(co, "_master_pdf", lambda creds, cfg, variant: b"%PDF-resume")
    monkeypatch.setattr(co, "cover_letter_pdf",
                        lambda company, cfg, llm, reason: b"%PDF-cover")
    monkeypatch.setattr(co.sheets, "append_outreach_row",
                        lambda creds, sid, row: appended.update(row=row))

    def fake_draft(creds, to, subject, body, attachment=None, attachments=None):
        captured.update(to=to, subject=subject, body=body, attachments=attachments)
        return "https://mail.google.com/draft"

    monkeypatch.setattr(co, "create_gmail_draft", fake_draft)

    note = co.run(None, "sid", "Acme", "AIE", cfg,
                  lambda p: json.dumps({"subject": "AI engineer interested in Acme",
                                        "body": "Hi,\n\nI build ML systems."}),
                  httpx.Client(), NOW)

    assert note.startswith("company outreach drafted")
    assert captured["to"] == ""  # recipient left blank for the user to fill
    assert captured["subject"].startswith("[JobPilot · Acme]")
    assert "Jane Doe Candidate" in captured["body"]  # signature appended
    assert len(captured["attachments"]) == 2  # resume + cover letter
    assert appended["row"][1] == "Acme" and appended["row"][10] == "Drafted"


def test_run_degrades_without_attachments(monkeypatch):
    cfg = make_cfg()
    monkeypatch.setattr(co.sheets, "read_companies", lambda creds, sid: [])
    monkeypatch.setattr(co, "_master_pdf", lambda creds, cfg, variant: None)
    monkeypatch.setattr(co, "cover_letter_pdf",
                        lambda company, cfg, llm, reason: None)
    monkeypatch.setattr(co.sheets, "append_outreach_row", lambda creds, sid, row: None)
    monkeypatch.setattr(co, "create_gmail_draft",
                        lambda *a, **k: "https://mail.google.com/draft")

    note = co.run(None, "sid", "Acme", "FDE", cfg,
                  lambda p: json.dumps({"subject": "s", "body": "Hi, short note."}),
                  httpx.Client(), NOW)
    assert note.startswith("company outreach drafted")  # still drafts, never crashes
