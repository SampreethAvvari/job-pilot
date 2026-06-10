import json

from jobpilot.models import Posting
from jobpilot.scorer import score
from tests.test_sources import make_cfg


def make_posting(pid: str) -> Posting:
    return Posting(
        id=pid, title="ML Engineer", company="Acme", url="u", source="greenhouse",
        description="Build ML systems",
    )


def valid_response(pids):
    return json.dumps(
        {
            "scores": [
                {
                    "id": pid,
                    "fit_score": 85,
                    "why": "Strong stack overlap",
                    "sponsorship_signal": "likely",
                    "resume_variant": "MLE",
                }
                for pid in pids
            ]
        }
    )


def test_happy_path():
    cfg = make_cfg()
    postings = [make_posting("a"), make_posting("b")]
    out = score(postings, cfg, lambda prompt: valid_response(["a", "b"]))
    assert all(s.fit_score == 85 for s in out)
    assert out[0].resume_variant == "MLE"


def test_retry_then_success():
    cfg = make_cfg()
    calls = []

    def flaky(prompt):
        calls.append(1)
        if len(calls) == 1:
            return "not json {"
        return valid_response(["a"])

    out = score([make_posting("a")], cfg, flaky)
    assert len(calls) == 2
    assert out[0].fit_score == 85


def test_total_failure_degrades_to_unscored():
    cfg = make_cfg()
    out = score([make_posting("a")], cfg, lambda p: "garbage")
    assert out[0].fit_score is None
    assert out[0].posting.id == "a"


def test_prompt_contains_profile_and_jobs():
    cfg = make_cfg()
    seen = {}

    def capture(prompt):
        seen["prompt"] = prompt
        return valid_response(["a"])

    score([make_posting("a")], cfg, capture)
    assert "AI Engineer" in seen["prompt"]  # profile headline-derived summary
    assert "Acme" in seen["prompt"]
