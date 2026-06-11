"""Gemini fit-scoring with a JSON-schema contract and one retry per batch."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, Literal

from pydantic import BaseModel, Field

from jobpilot.config import Config
from jobpilot.models import Posting

BATCH_SIZE = 10
PROMPT_PATH = Path(__file__).parent / "prompts" / "score_v1.txt"

LlmFn = Callable[[str], str]  # prompt -> raw JSON text


class _ScoreItem(BaseModel):
    id: str
    fit_score: int = Field(ge=0, le=100)
    why: str = Field(max_length=200)
    sponsorship_signal: Literal["likely", "unlikely", "unknown"]
    resume_variant: Literal["FDE", "MLE", "SDE", "AIE"]
    role_category: Literal["FDE", "AIE", "MLE", "DE", "DS", "SWE", "Other"] = "Other"


class _ScoreBatch(BaseModel):
    scores: list[_ScoreItem]


class Scored(BaseModel):
    posting: Posting
    fit_score: int | None = None
    why: str = ""
    sponsorship_signal: str = "unknown"
    resume_variant: str = "FDE"
    role_category: str = "Other"


def make_gemini_llm(cfg: Config, schema: type[BaseModel] | None = None) -> LlmFn:
    """Gemini client: Vertex AI when GOOGLE_CLOUD_PROJECT is set, else AI Studio key.

    schema constrains the JSON response; defaults to the scoring contract.
    """
    from google import genai

    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if project:
        client = genai.Client(
            vertexai=True,
            project=project,
            location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
        )
    else:
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    def llm(prompt: str) -> str:
        resp = client.models.generate_content(
            model=cfg.scoring.model,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": schema or _ScoreBatch,
            },
        )
        return resp.text

    return llm


def _build_prompt(batch: list[Posting], cfg: Config) -> str:
    jobs = [
        {
            "id": p.id,
            "title": p.title,
            "company": p.company,
            "location": p.location,
            "description": p.description[:1500],
        }
        for p in batch
    ]
    template = PROMPT_PATH.read_text(encoding="utf-8")
    return template.format(
        profile_summary=cfg.profile.summary, jobs_json=json.dumps(jobs, ensure_ascii=False)
    )


def score(postings: list[Posting], cfg: Config, llm: LlmFn) -> list[Scored]:
    """Score all postings. Failures degrade to fit_score=None, never raise."""
    results: dict[str, Scored] = {p.id: Scored(posting=p) for p in postings}
    for i in range(0, len(postings), BATCH_SIZE):
        batch = postings[i : i + BATCH_SIZE]
        prompt = _build_prompt(batch, cfg)
        for attempt in (1, 2):
            try:
                parsed = _ScoreBatch.model_validate_json(llm(prompt))
            except Exception:  # malformed output, schema mismatch, or API error
                if attempt == 2:
                    break  # leave batch unscored
                continue
            for item in parsed.scores:
                if item.id in results:
                    s = results[item.id]
                    s.fit_score = item.fit_score
                    s.why = item.why
                    s.sponsorship_signal = item.sponsorship_signal
                    s.resume_variant = item.resume_variant
                    s.role_category = item.role_category
            break
    return list(results.values())
