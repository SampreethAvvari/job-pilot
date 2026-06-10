import json

from jobpilot.scanner import _forward_only, classify


def llm_returning(matches):
    return lambda prompt: json.dumps({"matches": matches})


TRACKED = [
    {"_row": 2, "Job ID": "abc", "Company": "Acme", "Title": "ML Engineer", "Status": "Applied"},
]
MESSAGES = [
    {"from": "recruiting@acme.com", "subject": "Your application", "snippet": "interview"},
]


def test_classify_matches():
    out = classify(
        TRACKED, MESSAGES,
        llm_returning([{"job_id": "abc", "message_index": 0, "classification": "interview"}]),
    )
    assert out[0].classification == "interview"


def test_classify_garbage_degrades_to_empty():
    assert classify(TRACKED, MESSAGES, lambda p: "nope") == []


def test_classify_empty_inputs_skip_llm():
    assert classify([], MESSAGES, None) == []
    assert classify(TRACKED, [], None) == []


def test_forward_only_transitions():
    assert _forward_only("Applied", "Interview") == "Interview"
    assert _forward_only("Interview", "Response") is None  # never downgrade
    assert _forward_only("Applied", "Rejected") == "Rejected"  # terminal always allowed
    assert _forward_only("Applied", None) is None
