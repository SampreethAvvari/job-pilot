"""Master-resume regeneration: judge-driven rewrite loop, accept only if better.

Triggered via `python -m jobpilot --rebuild-resume <VARIANT>` (the console's
Regenerate button). Loads the current master from the RESUME_TEX_<V> env secret,
iterates up to N rewrites against the judge, and only publishes when the best
attempt scores at least as high as the current master:
  - new Secret Manager version of RESUME_TEX_<V> (runner has versionAdder)
  - Drive master PDF updated in place (same link everywhere)
  - report appended to the Sheet's Reports tab
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Callable

from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload

from jobpilot import sheets
from jobpilot.config import Config
from jobpilot.judge import KEYWORDS, judge
from jobpilot.latexpdf import compile_pdf
from jobpilot.rewrite_loop import REWRITE_RULES, best_of_attempts, report_json

PROMPT = Path(__file__).parent / "prompts" / "rebuild_v1.txt"


def _publish_secret(variant: str, tex: str) -> None:
    from google.cloud import secretmanager

    project = os.environ["GOOGLE_CLOUD_PROJECT"]
    client = secretmanager.SecretManagerServiceClient()
    client.add_secret_version(
        parent=f"projects/{project}/secrets/RESUME_TEX_{variant}",
        payload={"data": tex.encode("utf-8")},
    )


def rebuild_master(creds, spreadsheet_id: str, variant: str, cfg: Config,
                   llm: Callable[[str], str], now: datetime) -> str:
    if variant != "AIE":
        return f"rebuild skipped: single master mode, only AIE is maintained (got {variant})"
    # Past this guard variant is always "AIE", so the per-variant parameters below
    # (RESUME_TEX_<V>, KEYWORDS[<V>], pdf_ids[<V>]) all resolve to the AIE master.
    current_tex = os.environ.get(f"RESUME_TEX_{variant}")
    if not current_tex:
        return f"rebuild FAILED: RESUME_TEX_{variant} not mounted"
    keywords = KEYWORDS.get(variant, [])
    current_pdf, _ = compile_pdf(current_tex, f"master_{variant}")
    current_report = judge(current_tex, current_pdf, keywords)

    template = PROMPT.read_text(encoding="utf-8")

    def regen(prev_tex: str, issues: list[str]) -> str:
        fb = "\n".join(f"- {i}" for i in issues[:30])
        prompt = template.format(resume_tex=prev_tex, violations=fb or "(none)") \
            + "\n" + REWRITE_RULES
        out = llm(prompt)
        import json as _json
        return _json.loads(out)["tex"]

    tex, pdf, report, attempts = best_of_attempts(
        current_tex, keywords, regen, f"master_{variant}",
        max_attempts=cfg.tailoring.attempts)

    sheets.append_report(creds, spreadsheet_id, "master", variant,
                         report["score"], report_json(report),
                         now.strftime("%Y-%m-%d %H:%M"))

    if report["score"] < current_report["score"]:
        return (f"rebuild kept current master: best attempt {report['score']} "
                f"< current {current_report['score']} after {attempts} attempts")
    if tex != current_tex:
        _publish_secret(variant, tex)
    pdf_id = cfg.masters.pdf_ids.get(variant)
    if pdf_id:
        build("drive", "v3", credentials=creds, cache_discovery=False).files().update(
            fileId=pdf_id,
            media_body=MediaInMemoryUpload(pdf, mimetype="application/pdf"),
        ).execute()
    return (f"rebuilt {variant}: ATS {current_report['score']} -> {report['score']} "
            f"in {attempts} attempt(s)")
