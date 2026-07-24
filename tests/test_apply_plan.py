from __future__ import annotations

from jobpilot.apply import plan as pl


def _q(label, answer, required=True):
    return pl.Question(label=label, answer=answer, required=required)


def test_plan_needs_review_when_all_required_answered():
    p = pl.ApplicationPlan(job_id="j1", company="Acme", title="AIE", ats="greenhouse",
                           questions=[_q("Why us?", "Because I ship.")])
    assert p.next_status_after_fill() == "needs_review"


def test_plan_needs_input_when_required_unanswered():
    p = pl.ApplicationPlan(job_id="j1", company="Acme", title="AIE", ats="greenhouse",
                           questions=[_q("Security clearance?", ""), _q("Why us?", "x")])
    assert p.next_status_after_fill() == "needs_input"


def test_optional_blank_does_not_block():
    p = pl.ApplicationPlan(job_id="j1", company="Acme", title="AIE", ats="lever",
                           questions=[_q("Optional note", "", required=False)])
    assert p.next_status_after_fill() == "needs_review"


def test_plan_json_roundtrips():
    p = pl.ApplicationPlan(job_id="j1", company="Acme", title="AIE", ats="ashby",
                           questions=[_q("Q", "A")])
    assert pl.ApplicationPlan.model_validate_json(p.model_dump_json()).job_id == "j1"
