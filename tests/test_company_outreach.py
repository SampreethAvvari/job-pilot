import json
import re
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
    monkeypatch.setattr(co.website_email, "find_company_emails",
                        lambda company, domain, jd, client: [])
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
    assert captured["to"] == "careers@acme.com"  # no Hunter hit -> team-inbox fallback
    assert captured["subject"] == "AI engineer interested in Acme"  # no branding prefix
    assert "JobPilot" not in captured["subject"]
    assert "Jane Doe Candidate" in captured["body"]  # signature appended
    assert len(captured["attachments"]) == 2  # resume + cover letter
    assert appended["row"][1] == "Acme" and appended["row"][10] == "Drafted"


def test_run_degrades_without_attachments(monkeypatch):
    cfg = make_cfg()
    monkeypatch.setattr(co.sheets, "read_companies", lambda creds, sid: [])
    monkeypatch.setattr(co.website_email, "find_company_emails",
                        lambda company, domain, jd, client: [])
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


def test_run_addresses_from_published_email(monkeypatch):
    cfg = make_cfg()
    captured = {}
    appended = {}

    monkeypatch.setattr(co.sheets, "read_companies", lambda creds, sid: [])
    monkeypatch.setattr(co.website_email, "find_company_emails",
                        lambda company, domain, jd, client: ["careers@acme.com",
                                                              "jobs@acme.com"])
    monkeypatch.setattr(co, "_master_pdf", lambda creds, cfg, variant: b"%PDF")
    monkeypatch.setattr(co, "cover_letter_pdf", lambda *a, **k: b"%PDF")
    monkeypatch.setattr(co.sheets, "append_outreach_row",
                        lambda creds, sid, row: appended.update(row=row))

    def fake_draft(creds, to, subject, body, attachment=None, attachments=None):
        captured.update(to=to, body=body)
        return "url"

    monkeypatch.setattr(co, "create_gmail_draft", fake_draft)

    note = co.run(None, "sid", "Acme", "AIE", cfg,
                  lambda p: json.dumps({"subject": "AI engineer interested in Acme",
                                        "body": "Hi, I build ML systems."}),
                  httpx.Client(), NOW)
    assert captured["to"] == "careers@acme.com"  # best published email addressed
    assert "careers@acme.com" in appended["row"][12]  # Emails found column
    assert "jobs@acme.com" in appended["row"][12]  # all found emails recorded
    assert "->" in note


def test_run_skips_when_required_and_no_email(monkeypatch):
    cfg = make_cfg()
    drafts = []
    appended = {}
    monkeypatch.setattr(co.sheets, "read_companies", lambda creds, sid: [])
    monkeypatch.setattr(co.website_email, "find_company_emails",
                        lambda company, domain, jd, client: [])
    monkeypatch.setattr(co.sheets, "append_outreach_row",
                        lambda creds, sid, row: appended.update(row=row))
    monkeypatch.setattr(co, "create_gmail_draft",
                        lambda *a, **k: drafts.append(a) or "url")

    note = co.run(None, "sid", "Acme", "AIE", cfg, lambda p: "{}",
                  httpx.Client(), NOW, require_email=True)
    assert "skipped" in note and "no published email" in note
    assert drafts == []  # no draft created when a real email is required and absent
    assert appended["row"][10] == "No email"  # recorded so it is not re-checked


def test_auto_company_outreach_selects_fresh_real_companies(monkeypatch):
    cfg = make_cfg()
    calls = []
    rows = [
        {"Company": "Stripe", "Source": "greenhouse", "Fit": "85", "Status": "New",
         "Resume variant": "SDE", "Role": "SWE", "Posted": "2026-06-20 10:00"},
        {"Company": "Stripe", "Source": "greenhouse", "Fit": "70", "Status": "New",
         "Resume variant": "AIE", "Role": "AIE", "Posted": "2026-06-21 10:00"},  # dup
        {"Company": "RepostCo", "Source": "remoteok", "Fit": "90", "Status": "New",
         "Resume variant": "AIE", "Role": "AIE", "Posted": "2026-06-22"},  # aggregator
        {"Company": "LowFit", "Source": "lever", "Fit": "40", "Status": "New",
         "Resume variant": "SDE", "Role": "SWE", "Posted": "2026-06-22"},  # below min
        {"Company": "Notion", "Source": "ashby", "Fit": "75", "Status": "New",
         "Resume variant": "FDE", "Role": "FDE", "Posted": "2026-06-23 09:00"},
        {"Company": "DoneCo", "Source": "greenhouse", "Fit": "80", "Status": "New",
         "Resume variant": "MLE", "Role": "MLE", "Posted": "2026-06-23"},  # already done
        {"Company": "Dissed", "Source": "lever", "Fit": "95", "Status": "Dismissed",
         "Resume variant": "SDE", "Role": "SWE", "Posted": "2026-06-23"},  # dismissed
    ]
    monkeypatch.setattr(co.sheets, "read_rows", lambda creds, sid: rows)
    monkeypatch.setattr(co.sheets, "read_outreach",
                        lambda creds, sid: [{"Company": "DoneCo"}])
    monkeypatch.setattr(co, "run",
                        lambda creds, sid, company, variant, *a, **k:
                        calls.append((company, variant)) or f"drafted {company}")

    co.auto_company_outreach(None, "sid", cfg, lambda p: "{}", httpx.Client(), NOW)
    picked = dict(calls)
    assert set(picked) == {"Stripe", "Notion"}  # real, fresh, deduped, above fit
    assert picked["Stripe"] == "SDE"  # variant from the higher-fit Stripe row


def test_auto_company_outreach_respects_limit(monkeypatch):
    cfg = make_cfg()
    calls = []
    rows = [{"Company": f"C{i}", "Source": "greenhouse", "Fit": "80", "Status": "New",
             "Resume variant": "AIE", "Role": "AIE", "Posted": f"2026-06-{10 + i:02d}"}
            for i in range(8)]
    monkeypatch.setattr(co.sheets, "read_rows", lambda creds, sid: rows)
    monkeypatch.setattr(co.sheets, "read_outreach", lambda creds, sid: [])
    monkeypatch.setattr(co, "run", lambda *a, **k: calls.append(a[2]) or "ok")
    co.auto_company_outreach(None, "sid", cfg, lambda p: "{}", httpx.Client(), NOW, limit=3)
    assert len(calls) == 3


def test_website_emails_from_text_filters(monkeypatch):
    from jobpilot import website_email
    text = ("Apply: careers@acme.com or jobs@acme.com. Legal: legal@acme.com. "
            "Vendor: hi@other.com. Asset: logo%402x@acme.com")
    got = website_email.emails_from_text(text, "acme.com")
    assert "careers@acme.com" in got and "jobs@acme.com" in got
    assert "legal@acme.com" not in got  # deny-listed
    assert "hi@other.com" not in got  # off-domain


def test_website_find_company_emails_combines_and_skips_search(monkeypatch):
    from jobpilot import website_email
    monkeypatch.setattr(website_email, "find_careers_email",
                        lambda domain, client, max_pages=6: ["info@acme.com"])
    called = {"search": False}

    def no_search(company, domain, client):
        called["search"] = True
        return ["careers@acme.com"]

    monkeypatch.setattr(website_email, "search_emails", no_search)
    out = website_email.find_company_emails("Acme", "acme.com",
                                            "reach careers@acme.com", httpx.Client())
    assert "careers@acme.com" in out  # from job text, ranked above info@
    assert called["search"] is False  # search only fires when free sources are empty


def test_website_find_company_emails_hunter_fallback(monkeypatch):
    from jobpilot import hunter, website_email
    monkeypatch.setattr(website_email, "find_careers_email",
                        lambda d, c, max_pages=6: [])
    monkeypatch.setattr(website_email, "search_emails", lambda co, d, c: [])
    monkeypatch.setattr(hunter, "find_contacts", lambda co, d, c: (
        "", [{"name": "Riya", "email": "riya@acme.com", "confidence": 90}]))
    out = website_email.find_company_emails("Acme", "acme.com", "", httpx.Client())
    assert "riya@acme.com" in out  # Hunter fills in when free sources are empty


def test_hunter_verify_parses(monkeypatch, httpx_mock):
    from jobpilot import hunter
    monkeypatch.setenv("HUNTER_API_KEY", "k")
    httpx_mock.add_response(method="GET", url=re.compile(r".*email-verifier.*"),
                            json={"data": {"result": "deliverable", "score": 97}})
    assert hunter.verify("a@b.com", httpx.Client())["result"] == "deliverable"


def test_hunter_verify_skipped_without_key(monkeypatch):
    from jobpilot import hunter
    monkeypatch.delenv("HUNTER_API_KEY", raising=False)
    assert hunter.verify("a@b.com", httpx.Client()) == {}


def test_hunter_skipped_without_key(monkeypatch):
    from jobpilot import hunter
    monkeypatch.delenv("HUNTER_API_KEY", raising=False)
    assert hunter.find_contacts("Acme", "acme.com", httpx.Client()) == ("", [])


def test_hunter_parses_and_ranks_by_role(monkeypatch, httpx_mock):
    from jobpilot import hunter
    monkeypatch.setenv("HUNTER_API_KEY", "k")
    httpx_mock.add_response(method="GET", url=re.compile(r".*domain-search.*"), json={
        "data": {"pattern": "{first}", "emails": [
            {"value": "eng@acme.com", "first_name": "Eng", "last_name": "Person",
             "position": "Engineer", "department": "engineering", "confidence": 90},
            {"value": "riya@acme.com", "first_name": "Riya", "last_name": "P",
             "position": "Technical Recruiter", "department": "hr", "confidence": 80},
        ]},
    })
    pattern, contacts = hunter.find_contacts("Acme", "acme.com", httpx.Client())
    assert pattern == "{first}"
    assert contacts[0]["email"] == "riya@acme.com"  # recruiter outranks engineer

