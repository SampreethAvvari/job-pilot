"""High-standard resume judge — ResumeWorded-grade, deterministic, offline.

Usage:
  1. Compile your variants to resumes/resume_<VARIANT>.pdf (pdflatex; see FORK-SETUP)
     keeping the .tex sources next to them or in src/jobpilot/resumes/ (or pass --dir).
  2. python scripts/ats_check.py [--dir <tex+pdf dir>] [--min 90]

Scores each variant 0-100 across five categories and prints every violation:
  Structure (15) - one page, contact info, required sections, word budget
  Impact    (25) - share of bullets carrying a real number/metric
  Language  (25) - strong verb first, no weak/vague phrasing, no buzzwords,
                   no pronouns, no filler, no passive voice
  Repetition(15) - no overused verbs, no repeated phrases, no near-duplicate bullets
  Keywords  (20) - role-keyword coverage measured on the PDF's extracted text
                   (what ATS parsers actually see)

Exit non-zero if any resume scores under --min (default 90) or exceeds one page.
Customize KEYWORDS per variant for your target roles.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).parent.parent
DEFAULT_DIRS = [ROOT / "private", ROOT / "src" / "jobpilot" / "resumes"]
PDF_DIR = ROOT / "resumes"

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

STRONG_VERBS = {
    "accelerated", "architected", "authored", "automated", "benchmarked", "built",
    "caught", "championed", "consolidated", "constrained", "containerized",
    "coordinated", "created", "processed", "served",
    "cut", "debugged", "delivered", "deployed", "designed", "developed", "devised",
    "diagnosed", "drove", "eliminated", "embedded", "engineered", "established",
    "evaluated", "fine-tuned", "gated", "grew", "hardened", "implemented", "improved",
    "increased", "instrumented", "integrated", "launched", "led", "migrated",
    "modeled", "monitored", "operationalized", "optimized", "orchestrated", "owned",
    "packaged", "partnered", "prevented", "productionized", "profiled", "prototyped",
    "provisioned", "published", "raised", "ran", "rebuilt", "recovered", "reduced",
    "refactored", "replaced", "resolved", "scaled", "secured", "shipped", "solved",
    "streamlined", "surfaced", "tested", "trained", "transformed", "tuned", "turned",
    "unified", "validated", "wrote",
}
WEAK_PHRASES = [
    "worked on", "helped", "responsible for", "assisted", "participated in",
    "involved in", "tasked with", "duties included", "familiar with", "exposure to",
    "worked with", "was part of", "utilized", "leveraged",
]
BUZZWORDS = [
    "passionate", "results-driven", "results driven", "team player", "synergy",
    "go-getter", "detail-oriented", "detail oriented", "hard-working", "hardworking",
    "proven track record", "highly accomplished", "dynamic", "self-starter",
    "motivated", "fast-paced", "thought leader", "best-in-class", "world-class",
    "cutting-edge", "state-of-the-art", "innovative",
]
FILLER = ["successfully", "effectively", "seamlessly", "efficiently", "various", "numerous"]
PRONOUNS = re.compile(r"\b(I|my|we|our|me)\b")
PASSIVE = re.compile(r"\b(was|were|been|being)\s+\w+(ed|en)\b")
NUMBERY = re.compile(
    r"(\d|%|\$|\bzero\b|half a day|\bone\b\s+(?:page|retry|click)|"
    r"\b(?:million|billion|thousand)\b)", re.IGNORECASE,
)


def detex(s: str) -> str:
    s = re.sub(r"\\href\{[^}]*\}\{([^}]*)\}", r"\1", s)
    s = re.sub(r"\\textbf\{([^}]*)\}", r"\1", s)
    s = re.sub(r"\\textbar\{\}", "|", s)
    s = s.replace(r"\%", "%").replace(r"\$", "$").replace(r"\&", "&").replace(r"\#", "#")
    s = s.replace("---", "—").replace("--", "–").replace("~", " ")
    s = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?(\{[^{}]*\})?", " ", s)
    s = re.sub(r"[{}]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def parse_tex(tex: str) -> dict:
    sections = [m.group(1).lower() for m in re.finditer(r"\\section\{([^}]*)\}", tex)]
    contact = " ".join(re.findall(r"\\contactline\{(.*)\}", tex))
    items = re.findall(r"\\item\s+(.*)", tex)
    bullets = [detex(i) for i in items if detex(i)]
    summary = ""
    m = re.search(r"\\section\{Summary\}(.*?)\\section", tex, re.S | re.I)
    if m:
        summary = detex(m.group(1))
    # role entries in Work Experience: \entry{role}{org}{dates}{} followed by itemize
    roles = []
    for em in re.finditer(r"\\entry\{([^}]*)\}\{([^}]*)\}[^\n]*\n(.*?)(?=\\entry|\\section|\\end\{document\})",
                          tex, re.S):
        role_bullets = [detex(i) for i in re.findall(r"\\item\s+(.*)", em.group(3))]
        roles.append({"title": detex(em.group(1)), "org": detex(em.group(2)),
                      "bullets": [b for b in role_bullets if b]})
    return {"sections": sections, "contact": detex(contact), "bullets": bullets,
            "summary": summary, "roles": roles, "fulltext": detex(tex)}


def first_verb(bullet: str) -> str:
    words = re.findall(r"[A-Za-z][A-Za-z\-]*", bullet)
    return words[0].lower() if words else ""


def ngrams(tokens: list[str], n: int):
    return [" ".join(tokens[i:i + n]) for i in range(len(tokens) - n + 1)]


def judge(variant: str, tex_path: Path, pdf_path: Path) -> tuple[float, list[str]]:
    issues: list[str] = []
    parsed = parse_tex(tex_path.read_text(encoding="utf-8"))
    bullets = parsed["bullets"]
    words_total = len(parsed["fulltext"].split())

    # ---- Structure (15)
    structure = 15.0
    reader = PdfReader(pdf_path)
    pages = len(reader.pages)
    if pages != 1:
        structure -= 6
        issues.append(f"STRUCTURE: {pages} pages — must be exactly 1")
    contact = parsed["contact"].lower()
    for marker, label in [("@", "email"), (re.compile(r"\d{3}"), "phone"),
                          ("linkedin", "LinkedIn")]:
        ok = marker.search(contact) if hasattr(marker, "search") else marker in contact
        if not ok:
            structure -= 1
            issues.append(f"STRUCTURE: contact line missing {label}")
    need = {"summary", "skills", "education"}
    have = set()
    for s in parsed["sections"]:
        for n in need:
            if n in s:
                have.add(n)
    if not any("experience" in s for s in parsed["sections"]):
        structure -= 2
        issues.append("STRUCTURE: no Experience section")
    for missing in sorted(need - have):
        structure -= 1
        issues.append(f"STRUCTURE: no {missing.title()} section")
    if not 380 <= words_total <= 720:
        structure -= 2
        issues.append(f"STRUCTURE: {words_total} words (target 380-720 for one page)")
    # Summary quality — a weak summary hurts more than none
    summary = parsed["summary"]
    if summary:
        sw = len(summary.split())
        if not 25 <= sw <= 65:
            structure -= 2
            issues.append(f"STRUCTURE: summary is {sw} words (target 25-65)")
        if not NUMBERY.search(summary):
            structure -= 2
            issues.append("STRUCTURE: summary carries no concrete fact/metric")
        low = summary.lower()
        for w in BUZZWORDS:
            if w in low:
                structure -= 2
                issues.append(f"STRUCTURE: buzzword in summary: '{w}'")
        if PRONOUNS.search(summary):
            structure -= 1
            issues.append("STRUCTURE: personal pronoun in summary")
    # Role depth — every role must tell a quantified story
    for role in parsed["roles"]:
        if len(role["bullets"]) < 2:
            structure -= 3
            issues.append(f"STRUCTURE: role under-described (<2 bullets): {role['title']} @ {role['org']}")
        elif not any(NUMBERY.search(b) for b in role["bullets"]):
            structure -= 3
            issues.append(f"STRUCTURE: role has no quantified outcome: {role['title']} @ {role['org']}")

    # ---- Impact (25): bullets carrying a real number/metric
    quantified = sum(1 for b in bullets if NUMBERY.search(b))
    ratio = quantified / len(bullets) if bullets else 0
    impact = 25.0 * min(1.0, ratio / 0.85)
    for b in bullets:
        if not NUMBERY.search(b):
            issues.append(f"IMPACT: no metric → \"{b[:80]}…\"")

    # ---- Language (25)
    language = 25.0
    for b in bullets:
        v = first_verb(b)
        if v not in STRONG_VERBS:
            language -= 3
            issues.append(f"LANGUAGE: weak/non-action opener '{v}' → \"{b[:70]}…\"")
        low = b.lower()
        for w in WEAK_PHRASES:
            if w in low:
                language -= 4
                issues.append(f"LANGUAGE: weak phrase '{w}' → \"{b[:70]}…\"")
        for w in BUZZWORDS:
            if w in low:
                language -= 3
                issues.append(f"LANGUAGE: buzzword '{w}' → \"{b[:70]}…\"")
        for w in FILLER:
            if re.search(rf"\b{w}\b", low):
                language -= 2
                issues.append(f"LANGUAGE: filler '{w}' → \"{b[:70]}…\"")
        if PRONOUNS.search(b):
            language -= 3
            issues.append(f"LANGUAGE: personal pronoun → \"{b[:70]}…\"")
        if PASSIVE.search(low):
            language -= 2
            issues.append(f"LANGUAGE: passive voice → \"{b[:70]}…\"")
        wc = len(b.split())
        if wc > 40:  # recruiters skim bullets in ~2 seconds — length decides read vs skip
            language -= 2
            issues.append(f"LANGUAGE: bullet too long ({wc} words, max 40) → \"{b[:60]}…\"")
        elif wc < 8:
            language -= 2
            issues.append(f"LANGUAGE: bullet too thin ({wc} words) → \"{b[:60]}…\"")

    # ---- Repetition (15)
    repetition = 15.0
    verb_counts = Counter(first_verb(b) for b in bullets)
    for v, c in verb_counts.items():
        if c > 2:
            repetition -= 3 * (c - 2)
            issues.append(f"REPETITION: opener '{v}' used {c}x (max 2)")
    all_tokens = [re.findall(r"[a-z0-9\-]+", b.lower()) for b in bullets]
    gram_counts = Counter(g for toks in all_tokens for g in set(ngrams(toks, 4)))
    for g, c in gram_counts.items():
        if c > 1:
            repetition -= 3
            issues.append(f"REPETITION: phrase repeated {c}x: \"{g}\"")
    for i in range(len(bullets)):
        for j in range(i + 1, len(bullets)):
            a, b_ = set(all_tokens[i]), set(all_tokens[j])
            if a and b_ and len(a & b_) / len(a | b_) > 0.55:
                repetition -= 5
                issues.append(f"REPETITION: near-duplicate bullets {i + 1} & {j + 1}")

    # ---- Keywords (20) on PDF-extracted text
    pdf_text = re.sub(r"\s+", " ", " ".join(p.extract_text() or "" for p in reader.pages)).lower()
    kws = KEYWORDS.get(variant, CORE)
    missing = [k for k in kws if k.lower() not in pdf_text]
    coverage = 1 - len(missing) / len(kws)
    keywords = 20.0 * min(1.0, coverage / 0.9)
    if missing:
        issues.append(f"KEYWORDS: {coverage:.0%} coverage, missing {missing}")

    score = max(0.0, structure) + max(0.0, impact) + max(0.0, language) \
        + max(0.0, repetition) + max(0.0, keywords)
    return round(score, 1), issues


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="", help="directory holding resume_<V>.tex files")
    ap.add_argument("--min", type=float, default=90.0)
    ap.add_argument("--verbose", action="store_true", help="print all issues, not just first 12")
    args = ap.parse_args()

    tex_dirs = [Path(args.dir)] if args.dir else DEFAULT_DIRS
    ok_all = True
    for variant in KEYWORDS:
        tex = next((d / f"resume_{variant}.tex" for d in tex_dirs
                    if (d / f"resume_{variant}.tex").exists()), None)
        pdf = PDF_DIR / f"resume_{variant}.pdf"
        if tex is None or not pdf.exists():
            print(f"{variant}: SKIPPED (need {('tex' if tex is None else 'pdf')})")
            continue
        score, issues = judge(variant, tex, pdf)
        ok = score >= args.min
        ok_all = ok_all and ok
        print(f"\n{variant}: {score}/100  {'OK' if ok else 'FAIL'}  ({tex})")
        shown = issues if args.verbose else issues[:12]
        for i in shown:
            print("   -", i)
        if len(issues) > len(shown):
            print(f"   … {len(issues) - len(shown)} more (use --verbose)")
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
