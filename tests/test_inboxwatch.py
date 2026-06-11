import base64
import json
from datetime import datetime, timezone

import jobpilot.inboxwatch as iw
from jobpilot.inboxwatch import (
    Finding,
    body_text,
    build_alert,
    classify,
    forward_only,
    process,
    status_for,
    watch,
)
from tests.test_sources import make_cfg

NOW = datetime(2026, 6, 10, 15, 0, tzinfo=timezone.utc)

MESSAGES = [
    {"id": "m1", "from": "recruiter@acme.com", "subject": "Interview availability",
     "snippet": "s", "body": "Are you free Tuesday for a phone screen?"},
    {"id": "m2", "from": "no-reply@ats.io", "subject": "Application received",
     "snippet": "s", "body": "Thanks for applying to Beta."},
]
TRACKED = [
    {"_row": 2, "Job ID": "abc", "Company": "Acme", "Title": "ML Engineer", "Status": "Applied"},
]


def llm_returning(findings):
    return lambda prompt: json.dumps({"findings": findings})


def test_classify_parses_findings():
    out = classify(MESSAGES, TRACKED, llm_returning([
        {"message_index": 0, "classification": "next_step", "is_interview": True,
         "company": "Acme", "reason": "asks availability", "job_id": "abc"},
        {"message_index": 1, "classification": "automated_ack", "company": "Beta"},
    ]))
    assert out[0].classification == "next_step" and out[0].is_interview
    assert out[1].classification == "automated_ack" and out[1].job_id == ""


def test_classify_garbage_degrades_to_empty():
    assert classify(MESSAGES, TRACKED, lambda p: "nope") == []


def test_classify_empty_messages_skip_llm():
    assert classify([], TRACKED, None) == []


def test_classify_prompt_includes_tracked_and_bodies():
    seen = {}

    def spy(prompt):
        seen["p"] = prompt
        return json.dumps({"findings": []})

    classify(MESSAGES, TRACKED, spy)
    assert "ML Engineer" in seen["p"] and "phone screen" in seen["p"]


def test_forward_only_transitions():
    assert forward_only("Applied", "Interview") == "Interview"
    assert forward_only("Interview", "Response") is None  # never downgrade
    assert forward_only("Applied", "Rejected") == "Rejected"  # terminal always allowed
    assert forward_only("Applied", None) is None


MSG = {"id": "18c2a", "from": "Recruiter <r@acme.com>", "subject": "Next steps & <interview>",
       "snippet": "s", "body": "Are you free Tuesday?"}
NEXT_STEP = Finding(message_index=0, classification="next_step", is_interview=True,
                    company="Acme", reason="asks availability")


def test_build_alert_subject_and_link():
    subject, body = build_alert("me@gmail.com", MSG, NEXT_STEP)
    assert subject == "🎯 Acme responded — check me@gmail.com"
    assert "https://mail.google.com/mail/?authuser=me@gmail.com#all/18c2a" in body
    assert "Are you free Tuesday?" in body


def test_build_alert_escapes_html_and_handles_unknown_company():
    anon = Finding(message_index=0, classification="next_step", reason="r")
    subject, body = build_alert("me@gmail.com", MSG, anon)
    assert subject.startswith("🎯 A company responded")
    assert "<interview>" not in body and "&lt;interview&gt;" in body


def b64(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode()).decode()


def test_body_text_plain():
    payload = {"mimeType": "text/plain", "body": {"data": b64("hello")}}
    assert body_text(payload) == "hello"


def test_body_text_nested_multipart():
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {"mimeType": "text/html", "body": {"data": b64("<b>hi</b>")}},
            {"mimeType": "multipart/mixed",
             "parts": [{"mimeType": "text/plain", "body": {"data": b64("inner text")}}]},
        ],
    }
    assert body_text(payload) == "inner text"


def test_body_text_html_only_returns_empty():
    payload = {"mimeType": "text/html", "body": {"data": b64("<b>hi</b>")}}
    assert body_text(payload) == ""


def test_status_for_mapping():
    assert status_for(Finding(message_index=0, classification="rejection")) == "Rejected"
    assert status_for(Finding(message_index=0, classification="next_step",
                              is_interview=True)) == "Interview"
    assert status_for(Finding(message_index=0, classification="next_step")) == "Response"
    assert status_for(Finding(message_index=0, classification="automated_ack")) is None
    assert status_for(Finding(message_index=0, classification="unrelated")) is None


BY_ID = {"abc": {"_row": 2, "Job ID": "abc", "Company": "Acme",
                 "Title": "ML Engineer", "Status": "Applied"}}


def findings_pair():
    return [
        Finding(message_index=0, classification="next_step", is_interview=True,
                company="Acme", reason="availability", job_id="abc"),
        Finding(message_index=1, classification="automated_ack", company="Beta"),
    ]


def test_process_alerts_updates_and_logs():
    log_rows, updates, alerts = process("me@gmail.com", MESSAGES, findings_pair(), BY_ID, NOW)
    assert len(alerts) == 1 and "Acme" in alerts[0][0]
    assert (2, "Status", "Interview") in updates
    assert (2, "Reply class", "next_step") in updates
    assert len(log_rows) == 2
    assert log_rows[0][1] == "me@gmail.com:m1" and log_rows[0][7] == "yes"
    assert log_rows[1][5] == "automated_ack" and log_rows[1][7] == ""


def test_process_unjudged_messages_not_logged():
    # LLM omitted message 1 → no log row, so it is re-judged next run
    only_first = [findings_pair()[0]]
    log_rows, _, _ = process("me@gmail.com", MESSAGES, only_first, BY_ID, NOW)
    assert len(log_rows) == 1


def test_process_rejection_updates_status_without_alert():
    rej = [Finding(message_index=1, classification="rejection", company="Acme", job_id="abc")]
    log_rows, updates, alerts = process("me@gmail.com", MESSAGES, rej, BY_ID, NOW)
    assert alerts == []  # rejections never alert...
    assert (2, "Status", "Rejected") in updates  # ...but the sheet still moves
    assert log_rows[0][5] == "rejection"


def test_process_out_of_range_index_ignored():
    bogus = [Finding(message_index=9, classification="next_step")]
    log_rows, updates, alerts = process("me@gmail.com", MESSAGES, bogus, BY_ID, NOW)
    assert log_rows == [] and updates == [] and alerts == []


OTP_MSG = {"id": "m3", "from": "Ford Careers <RecruitingNoReply@ford.com>",
           "subject": "Confirm your identity for job Full-Stack Software Engineer - 63783",
           "snippet": "s", "body": "Use this one-time passcode to continue: 482913"}


def test_is_verification_matches_transactional_mail():
    for subject in ["Confirm your identity", "Your verification code is 123456",
                    "Your one-time passcode", "Verify your email address",
                    "Password reset requested"]:
        assert iw.is_verification({"subject": subject, "body": ""}), subject
    for subject in ["Interview availability", "Next steps for your application",
                    "Please send your portfolio"]:
        assert not iw.is_verification({"subject": subject, "body": ""}), subject


def test_process_verification_email_never_alerts():
    # the Ford bug: LLM says next_step, but an OTP email must not alert
    llm_says = [Finding(message_index=0, classification="next_step",
                        company="Ford Motor", reason="asks to confirm identity")]
    log_rows, updates, alerts = process("me@gmail.com", [OTP_MSG], llm_says, BY_ID, NOW)
    assert alerts == []
    assert log_rows[0][5] == "automated_ack" and log_rows[0][7] == ""


def test_prompt_forbids_verification_as_next_step():
    assert "passcode" in iw.PROMPT and "NEVER next_step" in iw.PROMPT


class _FakeGmail:
    def users(self):
        return self

    def getProfile(self, userId):
        return self

    def execute(self):
        return {"emailAddress": "primary@nyu.edu"}


def test_watch_isolates_account_failures(monkeypatch):
    monkeypatch.setattr(iw, "build", lambda *a, **k: _FakeGmail())
    monkeypatch.setattr(iw.sheets, "inboxwatch_keys", lambda c, s: set())
    monkeypatch.setattr(iw.sheets, "read_rows", lambda c, s: [])
    monkeypatch.setattr(iw.sheets, "update_cells", lambda c, s, u: None)
    monkeypatch.setattr(iw.sheets, "append_inboxwatch_rows", lambda c, s, r: None)

    def boom(creds, lookback_days, max_messages):
        raise RuntimeError("token expired")

    monkeypatch.setattr(iw, "fetch_messages", boom)
    notes = watch("creds", {"extra@gmail.com": "c2"}, "sid", make_cfg(), None, NOW)
    assert len(notes) == 2 and all("FAILED" in n for n in notes)


def test_watch_dedups_seen_messages_and_alerts(monkeypatch):
    sent = []
    appended = []
    monkeypatch.setattr(iw, "build", lambda *a, **k: _FakeGmail())
    monkeypatch.setattr(iw.sheets, "inboxwatch_keys",
                        lambda c, s: {"primary@nyu.edu:m2"})
    monkeypatch.setattr(iw.sheets, "read_rows", lambda c, s: list(BY_ID.values()))
    monkeypatch.setattr(iw.sheets, "update_cells", lambda c, s, u: None)
    monkeypatch.setattr(iw.sheets, "append_inboxwatch_rows",
                        lambda c, s, r: appended.extend(r))
    monkeypatch.setattr(iw, "fetch_messages", lambda c, d, m: list(MESSAGES))
    monkeypatch.setattr(iw, "send_alert", lambda c, to, s, b: sent.append(s))

    def llm(prompt):
        # m2 was already judged → only m1 survives dedup, at index 0
        assert "Thanks for applying to Beta." not in prompt
        return json.dumps({"findings": [
            {"message_index": 0, "classification": "next_step", "is_interview": True,
             "company": "Acme", "reason": "availability", "job_id": "abc"}]})

    notes = watch("creds", {}, "sid", make_cfg(), llm, NOW)
    assert sent == ["🎯 Acme responded — check primary@nyu.edu"]
    assert len(appended) == 1
    assert notes == ["inbox-watch primary@nyu.edu: 1 new emails, 1 alerts"]


def test_watch_writes_dedup_log_even_when_jobs_update_fails(monkeypatch):
    # if the dedup log is not written before the Jobs-sheet update, a transient
    # update failure makes every alerted email alert again next run
    appended = []
    monkeypatch.setattr(iw, "build", lambda *a, **k: _FakeGmail())
    monkeypatch.setattr(iw.sheets, "inboxwatch_keys", lambda c, s: set())
    monkeypatch.setattr(iw.sheets, "read_rows", lambda c, s: list(BY_ID.values()))
    monkeypatch.setattr(iw.sheets, "append_inboxwatch_rows",
                        lambda c, s, r: appended.extend(r))

    def boom(creds, sid, updates):
        raise RuntimeError("Sheets quota")

    monkeypatch.setattr(iw.sheets, "update_cells", boom)
    monkeypatch.setattr(iw, "fetch_messages", lambda c, d, m: list(MESSAGES))
    monkeypatch.setattr(iw, "send_alert", lambda c, to, s, b: None)
    llm = llm_returning([
        {"message_index": 0, "classification": "next_step", "is_interview": True,
         "company": "Acme", "reason": "availability", "job_id": "abc"},
        {"message_index": 1, "classification": "automated_ack", "company": "Beta"}])
    notes = watch("creds", {}, "sid", make_cfg(), llm, NOW)
    assert "FAILED" in notes[0]
    assert len(appended) == 2  # both judged messages logged despite the failure


def test_watch_disabled_returns_empty():
    cfg = make_cfg()
    cfg.inbox_watch.enabled = False
    assert watch("creds", {}, "sid", cfg, None, NOW) == []
