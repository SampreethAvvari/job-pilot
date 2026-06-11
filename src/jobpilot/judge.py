"""Resume judge — calibrated replica of ResumeWorded-style industry scoring.

Rubric (researched from ResumeWorded's published checks, help center, and
documented score reports):
  Impact      (35): quantified bullets, weak/responsibility verbs, action-verb
                    repetition (max 2 uses), non-action openers, tense mixing,
                    repeated phrases
  Brevity     (20): 2-line bullet budget (<=26 words), bullets-per-role bands,
                    total word budget, filler words, thin bullets
  Style       (15): buzzwords/cliches, pronouns, passive voice, date consistency,
                    contact completeness, AI-tell punctuation (em/en dashes)
  Sections    (15): standard headers, summary quality, education dates, one page
  Soft skills (15): leadership, communication, initiative, teamwork EVIDENCED in
                    bullets (not listed) — the most-missed category for engineers

Keyword coverage is reported separately (ResumeWorded's general score has no JD
keywords; relevancy is a different engine). Gate = score >= min AND coverage >= 0.85.
"""

from __future__ import annotations

import io
import re
from collections import Counter

from pypdf import PdfReader

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
        "TypeScript", "latency", "code review", "rollback", "testing",
    ],
    "AIE": CORE + [
        "LLM", "GenAI", "prompt engineering", "RAG", "agentic", "evaluation",
        "JSON Schema", "Vertex AI", "LangChain", "fine-tuning", "RLHF", "embeddings",
        "hallucinations",
    ],
}

STRONG_VERBS = {
    "accelerated", "architected", "authored", "automated", "benchmarked", "built",
    "caught", "coached", "conceived", "consolidated", "constrained", "containerized",
    "coordinated", "created", "cut", "debugged", "delivered", "deployed", "designed",
    "developed", "devised", "diagnosed", "directed", "drove", "eliminated",
    "embedded", "engineered", "established", "evaluated", "fine-tuned", "gated",
    "grew", "hardened", "implemented", "improved", "increased", "initiated",
    "instrumented", "integrated", "introduced", "launched", "led", "managed",
    "mentored", "migrated", "modeled", "monitored", "negotiated", "operationalized",
    "optimized", "orchestrated", "overhauled", "owned", "packaged", "partnered",
    "pioneered", "presented", "prevented", "processed", "productionized", "profiled",
    "proposed", "prototyped", "provisioned", "published", "raised", "ran", "rebuilt",
    "recovered", "redesigned", "reduced", "refactored", "replaced", "resolved",
    "scaled", "secured", "served", "shipped", "solved", "spearheaded", "streamlined",
    "supervised", "surfaced", "tested", "trained", "transformed", "tripled", "tuned",
    "turned", "unified", "validated", "wrote",
}
WEAK_PHRASES = [
    "responsible for", "worked with", "worked on", "assisted", "helped", "supported",
    "participated in", "involved in", "experienced in", "tasked with",
    "duties included", "handled", "utilized", "leveraged", "familiar with",
    "exposure to", "watched", "tried",
]
BUZZWORDS = [
    "results-driven", "results driven", "passionate", "dynamic", "proactive",
    "highly qualified", "top performer", "think outside the box", "value add",
    "synergy", "go-to person", "thought leader", "industry expert", "bottom line",
    "big picture", "motivated", "track record", "seasoned", "action-oriented",
    "customer-focused", "strong work ethic", "cutting-edge", "groundbreaking",
    "hit the ground running", "game-changer", "guru", "ninja", "rockstar",
    "world-class", "paradigm shift", "robust", "scalable", "disruptive",
    "innovative", "holistic", "team player", "detail-oriented", "detail oriented",
    "good communication skills", "hardworking", "hard-working", "problem solver",
    "strategic thinker", "self-starter", "go-getter", "highly skilled",
    "best-in-class", "state-of-the-art", "fast-paced",
]
FILLER = [
    "in order to", "as needed", "various", "several", "a large number",
    "a wide variety", "quickly", "successfully", "efficiently", "diligently",
    "frequently", "thoroughly", "very", "really",
]
LEADERSHIP = re.compile(
    r"\b(led|managed|directed|supervised|mentored|coached|oversaw|"
    r"direct reports?|team of \d|cross-functional)\b", re.I)
COMMUNICATION = re.compile(
    r"\b(presented|authored|wrote|negotiated|facilitated|stakeholders?|"
    r"c-suite|ceo|clinicians?|partnered|clients?|customers?)\b", re.I)
INITIATIVE = re.compile(
    r"\b(launched|spearheaded|pioneered|initiated|proposed|founded|built|"
    r"shipped|created|introduced|conceived)\b", re.I)
TEAMWORK = re.compile(
    r"\b(collaborated|coordinated|partnered|cross-functional|paired)\b", re.I)

PRONOUNS = re.compile(r"\b(I|me|my|we|our)\b")
PASSIVE = re.compile(r"\b(was|were|been|being)\s+\w+(ed|en)\b")
NUMBERY = re.compile(
    r"(\d|%|\$|\bzero\b|half a day|\b(?:million|billion|thousand)\b)", re.IGNORECASE)
AI_TELL_DASH = re.compile(r"[—–]")
DATE_RANGE = re.compile(r"\{([A-Z][a-z]{2,8} \d{4})\s*--\s*([A-Z][a-z]{2,8} \d{4}|Present)\}")
MAX_BULLET_WORDS = 24  # ~2 rendered lines; recruiters skim each bullet in ~2s


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
    summary = ""
    m = re.search(r"\\section\{Summary\}(.*?)\\section", tex, re.S | re.I)
    if m:
        summary = detex(m.group(1))
    roles = []
    for em in re.finditer(
        r"\\entry\{([^}]*)\}\{([^}]*)\}\{([^}]*)\}[^\n]*\n(.*?)(?=\\entry|\\section|\\end\{document\})",
        tex, re.S,
    ):
        role_bullets = [detex(i) for i in re.findall(r"\\item\s+(.*)", em.group(4))]
        roles.append({
            "title": detex(em.group(1)), "org": detex(em.group(2)),
            "dates": em.group(3), "current": "Present" in em.group(3),
            "bullets": [b for b in role_bullets if b],
        })
    bullets = [detex(i) for i in re.findall(r"\\item\s+(.*)", tex) if detex(i)]
    return {"sections": sections, "contact": detex(contact), "bullets": bullets,
            "summary": summary, "roles": roles, "fulltext": detex(tex), "raw": tex}


def first_verb(bullet: str) -> str:
    words = re.findall(r"[A-Za-z][A-Za-z\-]*", bullet)
    return words[0].lower() if words else ""


def _ngrams(tokens: list[str], n: int):
    return [" ".join(tokens[i:i + n]) for i in range(len(tokens) - n + 1)]


def judge(tex_source: str, pdf_bytes: bytes, keywords: list[str]) -> dict:
    issues: list[str] = []
    p = parse_tex(tex_source)
    bullets = p["bullets"]
    n_bullets = max(len(bullets), 1)
    words_total = len(p["fulltext"].split())
    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages = len(reader.pages)

    # ---------- Impact (35)
    impact = 35.0
    unq = [b for b in bullets if not NUMBERY.search(b)]
    impact -= min(15.0, 1.5 * len(unq))
    for b in unq:
        issues.append(f"IMPACT: no measurable result: \"{b[:75]}\"")
    if (len(bullets) - len(unq)) / n_bullets < 0.33:
        impact -= 5
        issues.append("IMPACT: under a third of bullets are quantified")
    weak_hits = 0
    for b in bullets:
        low = b.lower()
        for w in WEAK_PHRASES:
            if re.search(rf"\b{re.escape(w)}\b", low):
                weak_hits += 1
                issues.append(f"IMPACT: weak/responsibility phrase '{w}': \"{b[:65]}\"")
    impact -= min(8.0, 2.0 * weak_hits)
    openers = Counter(first_verb(b) for b in bullets)
    rep_pen = 0.0
    for v, c in openers.items():
        if c > 2:
            rep_pen += (c - 2)
            issues.append(f"IMPACT: action verb '{v}' opens {c} bullets (max 2)")
    impact -= min(5.0, rep_pen)
    non_action = [b for b in bullets if first_verb(b) not in STRONG_VERBS]
    impact -= min(4.0, 1.0 * len(non_action))
    for b in non_action:
        issues.append(f"IMPACT: doesn't open with an action verb: \"{b[:65]}\"")
    tense_pen = 0
    for role in p["roles"]:
        vs = [first_verb(b) for b in role["bullets"]]
        past = sum(1 for v in vs if v.endswith("ed") or v in
                   {"ran", "cut", "built", "rebuilt", "led", "wrote", "grew",
                    "drove", "oversaw", "kept", "won", "made", "set"})
        present = len(vs) - past
        if past and present:
            tense_pen += 1
            issues.append(f"IMPACT: mixed verb tense within role: {role['title']}")
    impact -= min(3.0, float(tense_pen))
    all_tokens = [re.findall(r"[a-z0-9\-]+", b.lower()) for b in bullets]
    gram_counts = Counter(g for toks in all_tokens for g in set(_ngrams(toks, 4)))
    for g, c in gram_counts.items():
        if c > 1:
            impact -= 2
            issues.append(f"IMPACT: phrase repeated {c}x across bullets: \"{g}\"")

    # ---------- Brevity (20)
    brevity = 20.0
    long_b = [b for b in bullets if len(b.split()) > MAX_BULLET_WORDS]
    brevity -= min(7.0, 1.0 * len(long_b))
    for b in long_b:
        issues.append(
            f"BREVITY: over 2 lines ({len(b.split())} words, max {MAX_BULLET_WORDS}): \"{b[:60]}\"")
    if len(long_b) / n_bullets > 0.4:
        brevity -= 2
        issues.append("BREVITY: over 40% of bullets exceed the 2-line budget")
    role_pen = 0.0
    for idx, role in enumerate(p["roles"]):
        nb = len(role["bullets"])
        if idx == 0 and nb < 4:
            role_pen += 2
            issues.append(
                f"BREVITY: most recent role has only {nb} bullets (aim 4-6): {role['title']}")
        if nb > 8:
            role_pen += 2
            issues.append(f"BREVITY: {nb} bullets under one role (max 8): {role['title']}")
    brevity -= min(4.0, role_pen)
    if not 420 <= words_total <= 700:
        brevity -= 3
        issues.append(f"BREVITY: {words_total} words (target 420-700 for one page)")
    fill_hits = 0
    for b in bullets + [p["summary"]]:
        low = (b or "").lower()
        for w in FILLER:
            n = len(re.findall(rf"\b{re.escape(w)}\b", low))
            if n:
                fill_hits += n
                issues.append(f"BREVITY: filler '{w}': \"{b[:60]}\"")
    brevity -= min(4.0, 0.5 * fill_hits)
    thin = [b for b in bullets if len(b.split()) < 8]
    brevity -= min(3.0, 1.0 * len(thin))
    for b in thin:
        issues.append(f"BREVITY: bullet too thin: \"{b[:60]}\"")

    # ---------- Style (15)
    style = 15.0
    text_zones = bullets + [p["summary"]]
    buzz_seen = set()
    for chunk in text_zones:
        low = (chunk or "").lower()
        for w in BUZZWORDS:
            if w in low and w not in buzz_seen:
                buzz_seen.add(w)
                issues.append(f"STYLE: buzzword/cliche '{w}': \"{chunk[:60]}\"")
    style -= min(5.0, 1.0 * len(buzz_seen))
    pron = sum(1 for c in text_zones if c and PRONOUNS.search(c))
    if pron:
        style -= min(3.0, 2.0 + 0.5 * (pron - 1))
        issues.append(f"STYLE: personal pronouns in {pron} place(s)")
    pas = sum(1 for c in text_zones if c and PASSIVE.search(c.lower()))
    style -= min(3.0, 1.0 * pas)
    if pas:
        issues.append(f"STYLE: passive voice in {pas} place(s)")
    dash_hits = sum(len(AI_TELL_DASH.findall(c or "")) for c in text_zones)
    style -= min(4.0, 1.0 * dash_hits)
    if dash_hits:
        issues.append(
            f"STYLE: {dash_hits} em/en dash(es) read machine-written; use commas or periods")
    dates = DATE_RANGE.findall(p["raw"])
    months = ({d[0].split()[0] for d in dates}
              | {d[1].split()[0] for d in dates if d[1] != "Present"})
    if len({len(m) for m in months}) > 1:
        style -= 2
        issues.append("STYLE: inconsistent date formats (mix of abbreviated and full months)")
    contact = p["contact"].lower()
    for marker, label in [("@", "email"), ("linkedin", "LinkedIn")]:
        if marker not in contact:
            style -= 1
            issues.append(f"STYLE: contact line missing {label}")
    if not re.search(r"\d{3}", contact):
        style -= 1
        issues.append("STYLE: contact line missing phone")

    # ---------- Sections / ATS (15)
    sections = 15.0
    if not any("experience" in s for s in p["sections"]):
        sections -= 3
        issues.append("SECTIONS: no Experience section header")
    for needed in ("skills", "education"):
        if not any(needed in s for s in p["sections"]):
            sections -= 3
            issues.append(f"SECTIONS: no {needed.title()} section header")
    if not p["summary"]:
        sections -= 1
        issues.append("SECTIONS: no summary")
    else:
        sw = len(p["summary"].split())
        if not 25 <= sw <= 65:
            sections -= 2
            issues.append(f"SECTIONS: summary is {sw} words (target 25-65)")
        if not NUMBERY.search(p["summary"]):
            sections -= 2
            issues.append("SECTIONS: summary carries no concrete fact/metric")
    edu = re.search(r"\\section\{Education\}(.*?)(\\section|\\end\{document\})",
                    p["raw"], re.S | re.I)
    if edu and not re.search(r"\d{4}", edu.group(1)):
        sections -= 2
        issues.append("SECTIONS: education missing graduation dates")
    if pages != 1:
        sections -= 5
        issues.append(f"SECTIONS: {pages} pages, must be exactly 1")

    # ---------- Soft skills (15) — evidence in bullets, not lists
    soft = 15.0
    blob = " ".join(bullets)
    lead_hits = len(set(m.group(0).lower() for m in LEADERSHIP.finditer(blob)))
    if lead_hits == 0:
        soft -= 6
        issues.append("SOFT SKILLS: no leadership/management evidence "
                      "(led/managed/mentored/direct reports/cross-functional ownership)")
    elif lead_hits == 1:
        soft -= 3
        issues.append("SOFT SKILLS: only one leadership signal; add a second "
                      "(led/managed/mentored/coordinated ownership)")
    if not COMMUNICATION.search(blob):
        soft -= 3
        issues.append("SOFT SKILLS: no communication/stakeholder evidence")
    if not INITIATIVE.search(blob):
        soft -= 3
        issues.append("SOFT SKILLS: no initiative evidence (launched/spearheaded/proposed)")
    if not TEAMWORK.search(blob):
        soft -= 3
        issues.append("SOFT SKILLS: no collaboration evidence (partnered/coordinated)")

    pdf_text = re.sub(r"\s+", " ",
                      " ".join(pg.extract_text() or "" for pg in reader.pages)).lower()
    missing = [k for k in keywords if k.lower() not in pdf_text]
    coverage = round(1 - len(missing) / len(keywords), 3) if keywords else 1.0
    if missing:
        issues.append(
            f"KEYWORDS (reported separately): {coverage:.0%} coverage, missing {missing}")

    breakdown = {
        "impact": round(max(0.0, impact), 1),
        "brevity": round(max(0.0, brevity), 1),
        "style": round(max(0.0, style), 1),
        "sections": round(max(0.0, sections), 1),
        "soft_skills": round(max(0.0, soft), 1),
    }
    return {
        "score": round(sum(breakdown.values()), 1),
        "breakdown": breakdown,
        "issues": issues,
        "keyword_coverage": coverage,
        "pages": pages,
        "words": words_total,
    }


def passes(report: dict, min_score: float = 90.0, min_coverage: float = 0.85) -> bool:
    return (report["score"] >= min_score and report["pages"] == 1
            and report["keyword_coverage"] >= min_coverage)
