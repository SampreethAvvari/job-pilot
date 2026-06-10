"""ATS gate for resume masters: 1 page exactly + per-variant keyword coverage.

Usage:
  1. Compile your resume .tex files with pdflatex (see docs/FORK-SETUP.md) into
     resumes/resume_<VARIANT>.pdf
  2. python scripts/ats_check.py

Exits non-zero if any resume is over one page or under 85% keyword coverage.
Customize KEYWORDS below for your own target roles — these sets define what
"ATS-ready" means for each of YOUR resume variants. Add/remove variants freely;
keep them in sync with VARIANT_FILES in src/jobpilot/tailor.py.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from pypdf import PdfReader

RESUMES = Path(__file__).parent.parent / "resumes"

CORE = [
    "Python", "SQL", "FastAPI", "PostgreSQL", "Docker", "Kubernetes", "CI/CD", "AWS", "GCP",
    "Kafka", "REST", "microservices", "Terraform", "monitoring",
]
KEYWORDS = {
    "FDE": CORE + [
        "Forward Deployed", "LLM", "RAG", "prompt", "stakeholder", "production",
        "Vertex AI", "fine-tuning", "RLHF", "TypeScript", "Next.js", "end to end",
    ],
    "MLE": CORE + [
        "PyTorch", "Transformers", "fine-tuning", "RLHF", "QLoRA", "reward model",
        "MLflow", "Airflow", "embeddings", "vector", "evaluation", "experiment tracking",
        "RAG", "LLM", "Spark",
    ],
    "SDE": CORE + [
        "distributed", "event-driven", "GraphQL", "Node.js", "React", "Next.js",
        "TypeScript", "latency", "scalability", "code review", "rollback", "testing",
    ],
    "AIE": CORE + [
        "LLM", "GenAI", "prompt engineering", "RAG", "agentic", "evaluation",
        "JSON Schema", "Vertex AI", "LangChain", "fine-tuning", "RLHF", "embeddings",
        "hallucinations",
    ],
}


def check(variant: str) -> bool:
    pdf = RESUMES / f"resume_{variant}.pdf"
    reader = PdfReader(pdf)
    pages = len(reader.pages)
    text = " ".join(page.extract_text() or "" for page in reader.pages)
    flat = re.sub(r"\s+", " ", text).lower()
    missing = [k for k in KEYWORDS[variant] if k.lower() not in flat]
    coverage = 1 - len(missing) / len(KEYWORDS[variant])
    ok = pages == 1 and coverage >= 0.85
    print(f"{variant}: {pages} page(s), keyword coverage {coverage:.0%}"
          + (f", MISSING: {missing}" if missing else "")
          + ("  OK" if ok else "  FAIL"))
    return ok


if __name__ == "__main__":
    results = [check(v) for v in KEYWORDS]
    sys.exit(0 if all(results) else 1)
