"""Find PUBLISHED careers/recruiting emails for a company, no guessing.

Three free-ish sources, combined and de-duped:
  1. the company's own website (/careers, /contact, ...),
  2. text we already hold (a job description that prints "email careers@..."),
  3. a web search (Serper.dev) that surfaces a published address elsewhere.

Only addresses that actually appear somewhere are returned; nothing is invented.
Every source degrades to nothing on error / missing key. Coverage is partial by
nature (many companies publish no email at all).
"""

from __future__ import annotations

import os
import re

import httpx

# Local-part must start alphanumeric; no '%' (kills URL-encoded false positives).
EMAIL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]*@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
PATHS = ["", "/careers", "/careers/", "/jobs", "/contact", "/contact-us",
         "/about", "/company"]

# Careers-relevant local-parts, best first.
RANK = ["careers", "jobs", "recruiting", "recruitment", "recruit", "talent",
        "hiring", "people", "joinus", "join", "work", "hr", "hello", "team",
        "contact", "hi", "info"]
# Never email these for a job pitch.
DENY = ("legal", "privacy", "abuse", "security", "dmca", "gdpr", "compliance",
        "press", "media", "investor", "ir@", "sales", "billing", "dpo",
        "copyright", "trademark", "noreply", "no-reply", "donotreply",
        "unsubscribe", "accommodation")
JUNK = ("example.com", "domain.com", "sentry", "wixpress", "@2x", ".png",
        ".jpg", ".gif", ".svg", ".webp", "your-email", "email@", "name@",
        "u00", "@sentry")


def _clean(domain: str) -> str:
    return (domain or "").strip().lower().removeprefix("https://").removeprefix(
        "http://").removeprefix("www.").split("/")[0]


def emails_from_text(text: str, domain: str) -> set[str]:
    """On-domain, career-relevant emails appearing in arbitrary text/HTML."""
    domain = _clean(domain)
    out: set[str] = set()
    for raw in EMAIL_RE.findall(text or ""):
        e = raw.strip().strip(".").lower()
        if any(j in e for j in JUNK) or any(d in e for d in DENY):
            continue
        if domain and not (e.endswith("@" + domain) or e.endswith("." + domain)):
            continue
        out.add(e)
    return out


def rank_emails(emails: set[str]) -> list[str]:
    def score(e: str) -> int:
        local = e.split("@", 1)[0]
        for i, kw in enumerate(RANK):
            if kw in local:
                return len(RANK) - i
        return 0
    return sorted(emails, key=score, reverse=True)


def find_careers_email(domain: str, client: httpx.Client,
                       max_pages: int = 6) -> list[str]:
    """Career emails published on the company's own site, best first; [] if none."""
    domain = _clean(domain)
    if not domain:
        return []
    found: set[str] = set()
    headers = {"User-Agent": "Mozilla/5.0 (compatible; JobPilot/1.0)"}
    for path in PATHS[:max_pages]:
        try:
            resp = client.get(f"https://{domain}{path}", headers=headers,
                              timeout=12, follow_redirects=True)
            if resp.status_code == 200 and resp.text:
                found |= emails_from_text(resp.text, domain)
        except httpx.HTTPError:
            continue
        if any(e.split("@", 1)[0] in ("careers", "jobs", "recruiting", "talent")
               for e in found):
            break
    return rank_emails(found)


def search_emails(company: str, domain: str, client: httpx.Client) -> list[str]:
    """Web search (Serper.dev) for a published careers email; [] without a key."""
    key = os.environ.get("SERPER_API_KEY")
    if not key:
        return []
    domain = _clean(domain)
    q = f'"{company}" careers OR recruiting email' + (f" {domain}" if domain else "")
    try:
        resp = client.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": key, "Content-Type": "application/json"},
            json={"q": q, "num": 10}, timeout=20)
        if resp.status_code != 200:
            return []
        blob = " ".join(
            (r.get("snippet", "") + " " + r.get("title", "") + " " + r.get("link", ""))
            for r in resp.json().get("organic", []))
    except (httpx.HTTPError, ValueError):
        return []
    return rank_emails(emails_from_text(blob, domain))


def find_company_emails(company: str, domain: str, jd_text: str,
                        client: httpx.Client) -> list[str]:
    """All published career emails for a company across the three sources, ranked.

    Website first (most authoritative), then any in the job text we already have,
    then a web search. De-duped; [] when nothing is published anywhere.
    """
    found: set[str] = set()
    found |= set(find_careers_email(domain, client))
    found |= emails_from_text(jd_text or "", domain)
    if not found:  # only spend a search query when the free sources came up empty
        found |= set(search_emails(company, domain, client))
    return rank_emails(found)
