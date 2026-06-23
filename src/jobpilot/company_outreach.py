"""Company-centric cold outreach: search a company, draft a personalized email
with the best-fit master resume + a tailored cover letter, pool drafts by company
in Gmail (subject prefix), and surface people-search links so the user finds the
real recipient and sends one by one.

Built for the FREE Apollo plan: no verified email is assumed. NOTHING IS EVER SENT.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Callable
from urllib.parse import quote, urlparse

import httpx

from jobpilot import hunter, sheets
from jobpilot.config import Config
from jobpilot.outreach import (
    Draft,
    create_gmail_draft,
    signature,
    strip_closing,
)

EMAIL_PROMPT = Path(__file__).parent / "prompts" / "company_outreach_v1.txt"
COVER_PROMPT = Path(__file__).parent / "prompts" / "cover_letter_company_v1.txt"

FOCUS = "AI engineering and software development"

VARIANTS = ("AIE", "FDE", "MLE", "SDE")
VARIANT_FRAMING = {
    "AIE": "AI Engineer: LLM platforms, RAG, agents, prompt infrastructure, eval.",
    "FDE": "Forward Deployed Engineer: customer-facing, end-to-end ownership, shipping.",
    "MLE": "Machine Learning Engineer: training, fine-tuning, ML infrastructure, MLOps.",
    "SDE": "Software Engineer: backend, distributed systems, APIs, cloud.",
}

# People to find at a company, and the search each one needs (free-plan workflow).
TARGET_ROLES = [
    "technical recruiter",
    "recruiter",
    "talent acquisition",
    "hiring manager",
    "engineering manager",
]
GENERIC_INBOXES = ["careers", "recruiting", "talent", "jobs"]

# "Real hiring companies, not reposts": companies posting on their own ATS, as
# opposed to aggregators (RemoteOK/HN/Adzuna/LinkedIn) full of reposts + agencies.
DIRECT_BOARDS = {
    "greenhouse", "lever", "ashby", "workday", "smartrecruiters",
    "workable", "recruitee",
}


# --------------------------------------------------------------------------- #
# Text hygiene
# --------------------------------------------------------------------------- #
_DASHES = {"—": ", ", "–": ", ", "‒": ", ", "―": ", "}


def sanitize_text(text: str) -> str:
    """Guarantee the user's rule: no em/en dashes, no hyphen used as punctuation.

    Intra-word hyphens (end-to-end, full-stack) are preserved.
    """
    for ch, repl in _DASHES.items():
        text = text.replace(ch, repl)
    # " - " or " -- " used as a dash between clauses -> comma
    text = re.sub(r"\s+-{1,2}\s+", ", ", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r" +,", ",", text)
    return text.strip()


# --------------------------------------------------------------------------- #
# Contact discovery (free-plan safe — no API call, deterministic)
# --------------------------------------------------------------------------- #
def find_people_links(company: str) -> list[tuple[str, str]]:
    """(label, url) search links for finding real people + their emails by hand."""
    out: list[tuple[str, str]] = []
    for role in TARGET_ROLES:
        kw = quote(f'"{company}" {role}')
        out.append(
            (role, f"https://www.linkedin.com/search/results/people/?keywords={kw}")
        )
    out.append(
        ("Apollo search",
         f"https://app.apollo.io/#/people?qOrganizationName={quote(company)}")
    )
    out.append(
        ("Google", f"https://www.google.com/search?q={quote(company + ' recruiter email')}")
    )
    return out


def company_domain(company: str, creds, spreadsheet_id: str) -> str:
    """Best-effort email domain: the Companies-tab Careers URL host when the company
    is on the watchlist, else a <slug>.com guess (caller marks it unverified)."""
    try:
        for row in sheets.read_companies(creds, spreadsheet_id):
            if row.get("Company", "").strip().lower() == company.strip().lower():
                host = urlparse(row.get("Careers URL", "")).netloc.lower()
                host = host.removeprefix("www.")
                # careers boards live on third-party hosts — ignore those
                if host and not any(
                    b in host for b in ("greenhouse", "lever", "ashby", "workday",
                                        "smartrecruiters", "workable", "recruitee")
                ):
                    return host
    except Exception:  # noqa: BLE001 — domain is a hint, never fatal
        pass
    slug = re.sub(r"[^a-z0-9]", "", company.lower())
    return f"{slug}.com" if slug else ""


def guessed_inboxes(domain: str) -> list[str]:
    return [f"{box}@{domain}" for box in GENERIC_INBOXES] if domain else []


# --------------------------------------------------------------------------- #
# Resume variant + cover letter
# --------------------------------------------------------------------------- #
_PICK_PROMPT = (
    "Pick the single best resume variant for a candidate cold-emailing {company}. "
    "Options: AIE (AI/LLM platforms), FDE (forward deployed, customer-facing), "
    "MLE (ML training/infra), SDE (backend/software). Judge by what {company} is "
    "known for. Return JSON exactly: "
    '{{"variant": "AIE|FDE|MLE|SDE", "reason": "one short sentence, no dashes"}}'
)


def pick_variant(company: str, llm: Callable[[str], str]) -> tuple[str, str]:
    """LLM picks the best of the four variants; defaults to AIE on any failure."""
    try:
        data = json.loads(llm(_PICK_PROMPT.format(company=company)))
        variant = str(data.get("variant", "")).upper()
        if variant in VARIANTS:
            return variant, sanitize_text(str(data.get("reason", "")))[:200]
    except Exception:  # noqa: BLE001 — auto-pick is best-effort
        pass
    return "AIE", "Default AI Engineer framing for a broad AI and software pitch."


_LATEX_SPECIAL = {
    "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
    "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def _latex_escape(text: str) -> str:
    return "".join(_LATEX_SPECIAL.get(c, c) for c in text)


def _cover_tex(name: str, contact_line: str, company: str,
               paragraphs: list[str]) -> str:
    body = "\n\n".join(_latex_escape(sanitize_text(p)) for p in paragraphs if p.strip())
    return (
        "\\documentclass[11pt]{article}\n"
        "\\input{_preamble}\n"
        "\\setlength{\\parskip}{8pt}\n"
        "\\begin{document}\n"
        f"\\name{{{_latex_escape(name)}}}\n"
        f"\\contactline{{{contact_line}}}\n"
        "\\vspace{14pt}\n\n"
        f"Dear {_latex_escape(company)} team,\n\n"
        f"{body}\n\n"
        "\\vspace{10pt}\n"
        f"Best,\\\\\n{_latex_escape(name)}\n"
        "\\end{document}\n"
    )


def cover_letter_pdf(company: str, cfg: Config,
                     llm: Callable[[str], str], variant_reason: str) -> bytes | None:
    """Tailored one-page cover-letter PDF; None when generation/compile fails."""
    from jobpilot.latexpdf import CompileError, compile_pdf

    try:
        prompt = COVER_PROMPT.read_text(encoding="utf-8").format(
            name=cfg.profile.name,
            profile_summary=cfg.profile.summary,
            company=company,
            variant_reason=variant_reason,
        )
        data = json.loads(llm(prompt))
        paragraphs = [str(p) for p in data.get("paragraphs", []) if str(p).strip()]
        if not paragraphs:
            return None
        links = " \\textbar{} ".join(
            p for p in (cfg.profile.portfolio, cfg.profile.linkedin) if p
        )
        contact_line = _latex_escape(links) if links else ""
        tex = _cover_tex(cfg.profile.name, contact_line, company, paragraphs)
        pdf, _pages = compile_pdf(tex, f"{company}_cover")
        return pdf
    except (CompileError, json.JSONDecodeError, KeyError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# Email body
# --------------------------------------------------------------------------- #
def draft_company_email(company: str, variant_reason: str, contact_name: str,
                        cfg: Config, llm: Callable[[str], str]) -> Draft:
    first = (contact_name or "").split()[0] if contact_name else ""
    greeting = f"Hi {first}" if first else "Hi"
    prompt = EMAIL_PROMPT.read_text(encoding="utf-8").format(
        name=cfg.profile.name,
        greeting=greeting,
        focus=FOCUS,
        portfolio=cfg.profile.portfolio,
        github=cfg.profile.github,
        company=company,
        variant_reason=variant_reason,
        profile_summary=cfg.profile.summary,
    )
    last: Exception | None = None
    for _ in range(2):
        try:
            d = Draft.model_validate_json(llm(prompt))
            return Draft(subject=sanitize_text(d.subject),
                         body=sanitize_text(d.body))
        except Exception as exc:  # noqa: BLE001 — retry malformed output once
            last = exc
    raise RuntimeError(f"company outreach draft failed: {last}")


# --------------------------------------------------------------------------- #
# Resume attachment
# --------------------------------------------------------------------------- #
def _master_pdf(creds, cfg: Config, variant: str) -> bytes | None:
    from jobpilot.outreach import _drive_pdf_bytes

    file_id = cfg.masters.pdf_ids.get(variant)
    if not file_id:
        return None
    return _drive_pdf_bytes(creds, f"https://drive.google.com/file/d/{file_id}/view")


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def run(creds, spreadsheet_id: str, company: str, variant: str, cfg: Config,
        llm: Callable[[str], str], client: httpx.Client, now: datetime,
        reason: str = "") -> str:
    """Draft one pooled cold email for a company; record it on the Outreach tab."""
    company = company.strip()
    if not company:
        return "company outreach skipped: empty company name"
    try:
        if variant and variant.upper() in VARIANTS:
            variant, reason = variant.upper(), (reason or "Manually selected.")
        else:
            variant, reason = pick_variant(company, llm)

        domain = company_domain(company, creds, spreadsheet_id)
        inboxes = guessed_inboxes(domain)
        links = find_people_links(company)

        # Reliable emails via Hunter (free tier); ('', []) when no key or no hit.
        _pattern, contacts = hunter.find_contacts(company, domain, client)
        primary = contacts[0] if contacts else None
        contact_name = primary["name"] if primary else ""
        to, verify_note = "", ""
        if primary:  # verify the best contact (0.5 credit); use unless undeliverable
            result = (hunter.verify(primary["email"], client).get("result") or "").lower()
            if result == "undeliverable":
                verify_note = "top contact undeliverable"
            else:
                to = primary["email"]
                verify_note = f"verified {result}" if result else "unverified"
        if not to and inboxes:
            to = inboxes[0]  # team inbox so every draft has a recipient to review
            verify_note = (f"{verify_note}; " if verify_note else "") + f"team inbox {to}"
        people_found = "; ".join(
            f"{c['name'] or '?'} ({c['position'] or c['department'] or 'n/a'}) "
            f"<{c['email']}> {c['confidence']}%" for c in contacts[:6]
        )

        draft = draft_company_email(company, reason, contact_name, cfg, llm)
        body = (f"{strip_closing(draft.body, cfg.profile.name)}\n\n"
                f"{signature(cfg.profile)}\n")
        subject = draft.subject  # no internal branding in a sent email

        attachments: list[tuple[str, bytes]] = []
        name_slug = _slug(cfg.profile.name)
        resume = _master_pdf(creds, cfg, variant)
        notes: list[str] = []
        if resume:
            attachments.append((f"{name_slug}_{variant}.pdf", resume))
        else:
            notes.append(f"resume {variant} not attached (Drive id missing)")
        cover = cover_letter_pdf(company, cfg, llm, reason)
        if cover:
            attachments.append((f"{name_slug}_cover_{_slug(company)}.pdf", cover))
        else:
            notes.append("cover letter not generated (pdflatex/LLM unavailable)")

        # `to` is the best confident Hunter email, else blank for the user to fill.
        draft_url = create_gmail_draft(creds, to, subject, body,
                                       attachments=attachments)
        if not to:
            notes.append("no recipient found, add one manually before sending")
        if verify_note:
            notes.append(verify_note)

        sheets.append_outreach_row(creds, spreadsheet_id, [
            now.strftime("%Y-%m-%d %H:%M"),
            company,
            domain,
            variant,
            reason,
            subject,
            ", ".join(inboxes),
            draft_url,
            cfg.masters.pdf_ids.get(variant, ""),
            "yes" if cover else "no",
            "Drafted",
            "; ".join(notes) + (" | find: " + " ".join(u for _, u in links[:3])),
            people_found,
        ])
        sent_to = f" -> {to}" if to else " (recipient blank, verify)"
        return (f"company outreach drafted: {company} ({variant}){sent_to}"
                + (f" | {'; '.join(notes)}" if notes else ""))
    except Exception as exc:  # noqa: BLE001 — one failure must not crash the job
        return f"company outreach FAILED for {company}: {type(exc).__name__}: {exc}"


def _recency(row: dict) -> str:
    return row.get("Posted") or row.get("Date found") or ""


def auto_company_outreach(creds, spreadsheet_id: str, cfg: Config,
                          llm: Callable[[str], str], client: httpx.Client,
                          now: datetime, limit: int = 30, min_fit: int = 60) -> list[str]:
    """Batch-draft outreach for the freshest real-hiring companies on the Jobs tab.

    Selects direct-board (own-ATS) postings only, drops aggregator reposts, requires
    a decent fit, dedupes to one draft per company, skips companies already drafted,
    and uses each job's recommended resume variant so the pitch matches the field.
    One Hunter credit per company; capped at `limit`.
    """
    rows = sheets.read_rows(creds, spreadsheet_id)
    done = {
        (r.get("Company") or "").strip().lower()
        for r in sheets.read_outreach(creds, spreadsheet_id)
        if r.get("Company")
    }
    best: dict[str, dict] = {}
    for r in rows:
        company = (r.get("Company") or "").strip()
        if not company or company.lower() in done:
            continue
        if r.get("Source") not in DIRECT_BOARDS:
            continue  # aggregators carry reposts/agencies — skip
        if r.get("Status") in ("Rejected", "Dismissed"):
            continue
        fit = int(r["Fit"]) if str(r.get("Fit", "")).isdigit() else 0
        if fit < min_fit:
            continue
        key = company.lower()
        prev = best.get(key)
        if prev is None or (fit, _recency(r)) > (prev["_fit"], _recency(prev)):
            best[key] = {**r, "_fit": fit}

    chosen = sorted(best.values(), key=lambda r: (_recency(r), r["_fit"]),
                    reverse=True)[:limit]
    if not chosen:
        return [f"auto outreach: no fresh direct-board companies with fit >= {min_fit}"]

    notes = [f"auto outreach: drafting {len(chosen)} fresh companies (cap {limit})"]
    for r in chosen:
        company = r["Company"].strip()
        variant = (r.get("Resume variant") or "").upper()
        role = r.get("Role") or variant or "engineering"
        reason = (f"You have a fresh {role} opening; this is the strongest match of "
                  f"my four resumes for {company}.")
        notes.append(run(creds, spreadsheet_id, company, variant, cfg, llm, client,
                         now, reason=reason))
    return notes
