"""Compile LaTeX source to a one-page PDF with pdflatex (must be on PATH)."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from pypdf import PdfReader

PREAMBLE = Path(__file__).parent / "resumes" / "_preamble.tex"


class CompileError(Exception):
    pass


def compile_pdf(tex_source: str, jobname: str = "doc") -> tuple[bytes, int]:
    """Return (pdf_bytes, page_count). Raises CompileError on failure."""
    if shutil.which("pdflatex") is None:
        raise CompileError("pdflatex not installed in this environment")
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", jobname)[:60] or "doc"
    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td)
        (tdir / "_preamble.tex").write_text(
            PREAMBLE.read_text(encoding="utf-8"), encoding="utf-8"
        )
        (tdir / f"{safe}.tex").write_text(tex_source, encoding="utf-8")
        proc = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", f"{safe}.tex"],
            cwd=tdir, capture_output=True, text=True, timeout=120,
        )
        pdf_path = tdir / f"{safe}.pdf"
        if not pdf_path.exists():
            tail = proc.stdout[-800:] if proc.stdout else proc.stderr[-800:]
            raise CompileError(f"pdflatex failed: {tail}")
        pdf = pdf_path.read_bytes()
        return pdf, len(PdfReader(pdf_path).pages)
