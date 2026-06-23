"""Upload the four master resume PDFs to Drive and print the relink config.

Run after replacing your resume PDFs (the old Drive files were deleted, so the
console links and outreach attachments dangle). It uploads each
``Sampreeth_Avvari_<VARIANT>.pdf`` from the repo root into
``JobPilot Resumes/Masters`` (idempotent: updates the file in place when it
already exists) and prints:

  * the ``masters.pdf_ids`` block for ``private/profile.yaml`` (resume attachments)
  * a ready ``RESUMES_JSON`` value for the UI service (Resumes tab + downloads)

Usage:  python scripts/relink_resumes.py
Auth:   token.json (local) or GOOGLE_OAUTH_* env, same as the pipeline.
"""

from __future__ import annotations

import json
from pathlib import Path

from googleapiclient.http import MediaInMemoryUpload

from jobpilot.gauth import credentials
from jobpilot.tailor import _drive, _ensure_folder

ROOT = Path(__file__).resolve().parent.parent
# Prefer the one-page masters in resumes/; fall back to the repo root.
RESUME_DIRS = [ROOT / "resumes", ROOT]
VARIANTS = {
    "FDE": ("Forward Deployed Engineer", "Customer-facing, end-to-end ownership framing."),
    "AIE": ("AI Engineer", "GenAI / LLM-platform framing."),
    "MLE": ("ML Engineer", "Training, RAG, ML-infrastructure framing."),
    "SDE": ("Software Engineer", "Backend / distributed-systems framing."),
}
FILENAME = "Sampreeth_Avvari_{variant}.pdf"


def _upload(drive, folder_id: str, name: str, pdf: bytes) -> str:
    """Create or update a PDF by name inside the folder; return its file id."""
    q = (f"name = '{name}' and '{folder_id}' in parents and trashed = false")
    found = drive.files().list(q=q, fields="files(id)").execute().get("files", [])
    media = MediaInMemoryUpload(pdf, mimetype="application/pdf")
    if found:
        file_id = found[0]["id"]
        drive.files().update(fileId=file_id, media_body=media).execute()
        return file_id
    return drive.files().create(
        body={"name": name, "parents": [folder_id]}, media_body=media, fields="id",
    ).execute()["id"]


def main() -> None:
    creds = credentials()
    drive = _drive(creds)
    root = _ensure_folder(drive, "JobPilot Resumes")
    masters = _ensure_folder(drive, "Masters", root)

    pdf_ids: dict[str, str] = {}
    resumes_json: list[dict] = []
    for variant, (title, blurb) in VARIANTS.items():
        name = FILENAME.format(variant=variant)
        path = next((d / name for d in RESUME_DIRS if (d / name).exists()), None)
        if path is None:
            print(f"SKIP {variant}: {name} not found in resumes/ or repo root")
            continue
        file_id = _upload(drive, masters, path.name, path.read_bytes())
        pdf_ids[variant] = file_id
        resumes_json.append(
            {"variant": variant, "title": title, "blurb": blurb, "pdfId": file_id}
        )
        print(f"OK   {variant}: {file_id}  ({path.name})")

    print("\n--- paste into private/profile.yaml under masters: ---")
    print("masters:\n  pdf_ids:")
    for variant, file_id in pdf_ids.items():
        print(f"    {variant}: {file_id}")

    print("\n--- set RESUMES_JSON on the UI service (and locally in ui/.env.local) ---")
    print("RESUMES_JSON=" + json.dumps(resumes_json))


if __name__ == "__main__":
    main()
