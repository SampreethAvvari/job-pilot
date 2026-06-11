import json

from jobpilot.inboxwatch import Finding, classify, forward_only, status_for

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


def test_status_for_mapping():
    assert status_for(Finding(message_index=0, classification="rejection")) == "Rejected"
    assert status_for(Finding(message_index=0, classification="next_step",
                              is_interview=True)) == "Interview"
    assert status_for(Finding(message_index=0, classification="next_step")) == "Response"
    assert status_for(Finding(message_index=0, classification="automated_ack")) is None
    assert status_for(Finding(message_index=0, classification="unrelated")) is None
