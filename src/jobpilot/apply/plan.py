"""ApplicationPlan: the reviewable artifact of a fill. Serialized to plan.json in
Drive and mirrored to the Applications Sheet tab. Spec: 2026-07-24-auto-apply-design.md
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ApplicationStatus = Literal[
    "queued", "filling", "needs_review", "needs_input", "approved", "submitting",
    "submitted", "failed", "captcha_blocked", "manual_required", "check_email",
]


class Question(BaseModel):
    label: str
    answer: str = ""
    required: bool = True
    char_limit: int | None = None
    kind: str = "text"  # text | textarea | select | file | eeo | boolean
    screenshot: str = ""  # Drive/URL of the per-question screenshot


class ApplicationPlan(BaseModel):
    job_id: str
    company: str
    title: str
    ats: str
    location_key: str = "ny"
    cover_letter_pdf_url: str = ""
    questions: list[Question] = Field(default_factory=list)
    status: ApplicationStatus = "queued"
    evidence_folder: str = ""
    notes: list[str] = Field(default_factory=list)

    def next_status_after_fill(self) -> ApplicationStatus:
        if any(q.required and not q.answer.strip() for q in self.questions):
            return "needs_input"
        return "needs_review"
