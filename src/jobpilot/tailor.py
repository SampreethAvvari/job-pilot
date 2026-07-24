"""Per-job tailoring: JD keywords + tailored one-page resume + cover letter PDFs.

Truth guardrails live in prompts/tailor_v1.txt: the model may only reorder,
rephrase, and re-emphasize what the master resume already claims.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Callable

import httpx
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload
from pydantic import BaseModel, Field

from jobpilot import sheets
from jobpilot.config import Config
from jobpilot.latexpdf import CompileError, compile_pdf
from jobpilot.sources.common import strip_html

# Below this many JD characters, tailoring would just guess — recover the JD
# from the live posting page first, or refuse with a visible reason.
MIN_JD_CHARS = 200


def _fetch_jd(url: str) -> str:
    """Best-effort JD recovery: fetch the live posting page, strip to text."""
    if not url:
        return ""
    try:
        resp = httpx.get(url, timeout=20, follow_redirects=True,
                         headers={"User-Agent": "Mozilla/5.0 (compatible; JobPilot)"})
        resp.raise_for_status()
        return strip_html(resp.text)
    except httpx.HTTPError:
        return ""

RESUME_DIR = Path(__file__).parent / "resumes"
PROMPT = Path(__file__).parent / "prompts" / "tailor_v1.txt"
VARIANT_FILES = {
    "FDE": "resume_FDE.tex",
    "MLE": "resume_MLE.tex",
    "SDE": "resume_SDE.tex",
    "AIE": "resume_AIE.tex",
}


class TailorResult(BaseModel):
    keywords: list[str] = Field(min_length=3, max_length=25)
    tailored_tex: str
    cover_letter_tex: str
    changes: str = ""


def _resume_tex(variant: str) -> str:
    """Every tailored resume derives from the single AIE master (owner decision,
    2026-07-23 spec). The variant argument survives only as a report label; base
    selection ignores it. RESUME_TEX_AIE env (Secret Manager) wins; the repo
    template is the fallback."""
    import os

    env = os.environ.get("RESUME_TEX_AIE")
    if env:
        return env
    return (RESUME_DIR / VARIANT_FILES["AIE"]).read_text(encoding="utf-8")


def _build_prompt(company: str, title: str, description: str, variant: str) -> str:
    tex = _resume_tex(variant)
    template = PROMPT.read_text(encoding="utf-8")
    return template.format(
        company=company, title=title, description=description[:6000], resume_tex=tex
    )


def generate_from_prompt(prompt: str, llm: Callable[[str], str]) -> TailorResult:
    last_err: Exception | None = None
    for _ in range(2):
        try:
            return TailorResult.model_validate_json(llm(prompt))
        except Exception as exc:  # malformed output — retry once
            last_err = exc
    raise CompileError(f"tailor generation failed: {last_err}")


def generate(company: str, title: str, description: str, variant: str,
             llm: Callable[[str], str]) -> TailorResult:
    return generate_from_prompt(_build_prompt(company, title, description, variant), llm)


def _drive(creds):
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _ensure_folder(drive, name: str, parent: str | None = None) -> str:
    q = (f"name = '{name}' and mimeType = 'application/vnd.google-apps.folder' "
         "and trashed = false")
    if parent:
        q += f" and '{parent}' in parents"
    found = drive.files().list(q=q, fields="files(id)").execute().get("files", [])
    if found:
        return found[0]["id"]
    body: dict = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent:
        body["parents"] = [parent]
    return drive.files().create(body=body, fields="id").execute()["id"]


def upload_pdf(creds, folder_id: str, filename: str, pdf: bytes) -> str:
    f = _drive(creds).files().create(
        body={"name": filename, "parents": [folder_id]},
        media_body=MediaInMemoryUpload(pdf, mimetype="application/pdf"),
        fields="id",
    ).execute()
    return f"https://drive.google.com/file/d/{f['id']}/view"


def upload_bytes(creds, folder_id: str, filename: str, blob: bytes,
                 mimetype: str) -> str:
    f = _drive(creds).files().create(
        body={"name": filename, "parents": [folder_id]},
        media_body=MediaInMemoryUpload(blob, mimetype=mimetype),
        fields="id, webViewLink").execute()
    return f.get("webViewLink", "")


def tailor_row(creds, spreadsheet_id: str, row: dict, cfg: Config,
               llm: Callable[[str], str], now: datetime) -> str:
    """Tailor one sheet row through the judge-driven rewrite loop."""
    from jobpilot.judge import KEYWORDS
    from jobpilot.rewrite_loop import REWRITE_RULES, best_of_attempts, report_json

    company, title = row["Company"], row["Title"]
    variant = row.get("Resume variant") or "FDE"
    description = row.get("JD excerpt") or ""
    try:
        if len(description.strip()) < MIN_JD_CHARS:
            description = _fetch_jd(row.get("URL", ""))
            if len(description.strip()) >= MIN_JD_CHARS:
                # persist so scoring/outreach/explain see the recovered JD too
                sheets.update_cells(creds, spreadsheet_id,
                                    [(row["_row"], "JD excerpt", description[:5000])])
            else:
                sheets.update_cells(creds, spreadsheet_id, [(
                    row["_row"], "Tailored resume",
                    "FAILED: JD not accessible — the posting page gave no text; "
                    "open the apply link and retry later",
                )])
                return f"tailor SKIPPED for {company} — {title}: JD not accessible"
        base_prompt = _build_prompt(company, title, description, variant)
        extras: dict[int, TailorResult] = {}

        def run_llm(prompt: str) -> TailorResult:
            result = generate_from_prompt(prompt, llm)
            extras[id(result.tailored_tex)] = result
            return result

        first = run_llm(base_prompt + "\n" + REWRITE_RULES)

        def regen(prev_tex: str, issues: list[str]) -> str:
            fb = "\n".join(f"- {i}" for i in issues[:25])
            prompt = (base_prompt + "\n" + REWRITE_RULES
                      + "\nPREVIOUS DRAFT (revise it, do not start over):\n" + prev_tex
                      + "\nSCORER VIOLATIONS TO FIX (fix every one):\n" + fb)
            return run_llm(prompt).tailored_tex

        tex, resume_pdf, report, attempts = best_of_attempts(
            first.tailored_tex, KEYWORDS["AIE"], regen,
            f"{company}_{variant}", max_attempts=cfg.tailoring.attempts)
        result = extras.get(id(tex), first)
        cover_pdf, _ = compile_pdf(result.cover_letter_tex, f"{company}_cover")

        drive = _drive(creds)
        root = _ensure_folder(drive, "JobPilot Resumes")
        tailored = _ensure_folder(drive, "Tailored", root)
        day = _ensure_folder(drive, now.strftime("%Y-%m-%d"), tailored)
        slug = re.sub(r"[^A-Za-z0-9]+", "_", f"{company}_{title}")[:60]
        resume_url = upload_pdf(creds, day, f"{slug}_resume.pdf", resume_pdf)
        cover_url = upload_pdf(creds, day, f"{slug}_cover.pdf", cover_pdf)

        sheets.update_cells(creds, spreadsheet_id, [
            (row["_row"], "Tailored resume", resume_url),
            (row["_row"], "Cover letter", cover_url),
            (row["_row"], "JD keywords", ", ".join(result.keywords)),
            (row["_row"], "Resume ATS", report["score"]),
        ])
        sheets.append_report(creds, spreadsheet_id, "job", row["Job ID"],
                             report["score"], report_json(report),
                             now.strftime("%Y-%m-%d %H:%M"))

        note = (f"tailored: {company} — {title} ({variant}) "
                f"ATS {report['score']} in {attempts} attempt(s)")
        try:  # transparency report — best-effort, tailoring already succeeded
            from jobpilot import explain

            baseline = _resume_tex(variant)
            diff_url = ""
            diff_pdf = explain.latexdiff_pdf(baseline, tex, f"{company}_diff")
            if diff_pdf:
                diff_url = upload_pdf(creds, day, f"{slug}_diff.pdf", diff_pdf)
            tr = explain.generate_report(
                explain.build_explain_prompt(
                    company, title, description, row.get("URL", ""), baseline,
                    tex, result.cover_letter_tex, result.keywords,
                    report["issues"]),
                llm)
            sheets.append_report(
                creds, spreadsheet_id, "tailor", row["Job ID"], report["score"],
                explain.assemble_report(tr, explain.diff_sections(baseline, tex),
                                        diff_url, report),
                now.strftime("%Y-%m-%d %H:%M"))
        except Exception as exc:  # noqa: BLE001 — visible but never fatal (BL-18)
            note += f" | transparency report FAILED: {type(exc).__name__}: {exc}"
        return note
    except Exception as exc:  # noqa: BLE001 — one failure must not kill the batch
        err = f"{type(exc).__name__}: {exc}"
        try:  # surface on the row — otherwise the console button blinks and gives up silently
            sheets.update_cells(creds, spreadsheet_id,
                                [(row["_row"], "Tailored resume", f"FAILED: {err[:160]}")])
        except Exception:  # noqa: BLE001 — reporting must not mask the original error
            pass
        return f"tailor FAILED for {company} — {title}: {err}"


def auto_tailor(creds, spreadsheet_id: str, cfg: Config, llm: Callable[[str], str],
                now: datetime) -> list[str]:
    """Tailor every shortlisted, not-yet-tailored job (cost-capped per run)."""
    if not cfg.tailoring.enabled:
        return []
    rows = sheets.read_rows(creds, spreadsheet_id)
    todo = [
        r for r in rows
        if not r.get("Tailored resume")
        and r.get("Status") in ("New", "")
        and str(r.get("Fit", "")).isdigit()
        and int(r["Fit"]) >= cfg.tailoring.auto_threshold
    ][: cfg.tailoring.max_per_run]
    notes = [tailor_row(creds, spreadsheet_id, r, cfg, llm, now) for r in todo]
    return notes or ["tailor: nothing new to tailor"]


def make_tailor_llm(cfg: Config):
    """Plain-text Gemini call (the tailor validates JSON itself)."""
    import os

    from google import genai

    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    client = (
        genai.Client(vertexai=True, project=project,
                     location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"))
        if project else genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    )

    def llm(prompt: str) -> str:
        resp = client.models.generate_content(
            model=cfg.scoring.model,
            contents=prompt,
            config={"response_mime_type": "application/json"},
        )
        return resp.text

    return llm
