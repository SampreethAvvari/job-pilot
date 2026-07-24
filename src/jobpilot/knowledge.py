"""Knowledge pack: distilled work-ex corpus grounding the Assistant chat.

Auto sections (profile, resumes, github, portfolio) are rebuilt on refresh;
the user-edited ``extras`` row in the Knowledge sheet tab is always preserved
(it replaces LinkedIn, which has no read API).

Spec: docs/superpowers/specs/2026-06-12-assistant-chat-design.md
"""

from __future__ import annotations

import re
from datetime import datetime

import httpx

from jobpilot import sheets
from jobpilot.config import Config
from jobpilot.sources.common import strip_html

MAX_REPOS = 12
README_CHARS = 1500
PORTFOLIO_CHARS = 6000

UA = {"User-Agent": "Mozilla/5.0 (compatible; JobPilot)"}
AUTO_SECTIONS = ("profile", "resumes", "github", "portfolio")


def _github_user(cfg: Config) -> str:
    m = re.search(r"github\.com/([\w-]+)", cfg.profile.github or "")
    return m.group(1) if m else ""


def profile_section(cfg: Config) -> str:
    p = cfg.profile
    return (
        f"Name: {p.name}\nHeadline: {p.headline}\n"
        f"Locations: {', '.join(p.locations)}\n"
        f"Needs visa sponsorship: {p.sponsorship_needed}\n"
        f"Summary: {p.summary}\n"
        f"Links: {p.portfolio} {p.linkedin} {p.github}".strip()
    )


def resumes_section() -> str:
    from jobpilot.tailor import _resume_tex

    # Single-master mode (2026-07-23): every tailored resume derives from the one
    # AIE base, so the knowledge pack grounds the Assistant on that master once
    # rather than repeating identical content under four variant headers.
    return ("## Master resume (AIE): every tailored resume derives from this base "
            "(LaTeX, factual source of truth)\n" + _resume_tex("AIE"))


def github_section(cfg: Config, client: httpx.Client) -> str:
    user = _github_user(cfg)
    if not user:
        return ""
    resp = client.get(f"https://api.github.com/users/{user}/repos",
                      params={"sort": "pushed", "per_page": 30})
    resp.raise_for_status()
    repos = [r for r in resp.json() if not r.get("fork")]
    repos.sort(key=lambda r: (r.get("stargazers_count", 0), r.get("pushed_at", "")),
               reverse=True)
    out = []
    for r in repos[:MAX_REPOS]:
        head = (f"## {r['name']} ({r.get('language') or 'n/a'}, "
                f"{r.get('stargazers_count', 0)} stars)\n{r.get('description') or ''}")
        readme = ""
        try:
            rd = client.get(
                f"https://raw.githubusercontent.com/{user}/{r['name']}/HEAD/README.md")
            if rd.status_code == 200:
                readme = rd.text[:README_CHARS]
        except httpx.HTTPError:
            pass
        out.append(f"{head}\n{readme}".strip())
    return "\n\n".join(out)


def portfolio_section(cfg: Config, client: httpx.Client, creds=None,
                      spreadsheet_id: str = "") -> str:
    """Render the stored portfolio graph into pack text; fall back to homepage strip."""
    if creds and spreadsheet_id:
        from jobpilot import portfolio_graph as pgmod

        raw = sheets.read_portfolio_graph(creds, spreadsheet_id)
        if raw:
            try:
                return pgmod.render_pack(pgmod.PortfolioGraph.model_validate_json(raw))
            except Exception:  # noqa: BLE001 — fall through to homepage strip
                pass
    url = cfg.profile.portfolio
    if not url:
        return ""
    try:
        resp = client.get(url)
        resp.raise_for_status()
        return strip_html(resp.text)[:PORTFOLIO_CHARS]
    except httpx.HTTPError:
        return ""


def refresh(creds, spreadsheet_id: str, cfg: Config, now: datetime) -> list[str]:
    """Rebuild every auto section; never raises (digest-note degradation)."""
    client = httpx.Client(timeout=20, follow_redirects=True, headers=UA)
    sections: dict[str, str] = {}
    notes: list[str] = []
    builders = {
        "profile": lambda: profile_section(cfg),
        "resumes": resumes_section,
        "github": lambda: github_section(cfg, client),
        "portfolio": lambda: portfolio_section(cfg, client, creds, spreadsheet_id),
    }
    for name, build in builders.items():
        try:
            sections[name] = build()
            notes.append(f"knowledge {name}: {len(sections[name])} chars")
        except Exception as exc:  # noqa: BLE001 — one dark source must not block the rest
            sections[name] = ""
            notes.append(f"knowledge {name}: FAILED ({type(exc).__name__}: {exc})")
    try:
        sheets.write_knowledge(creds, spreadsheet_id, sections,
                               now.strftime("%Y-%m-%d %H:%M"))
    except Exception as exc:  # noqa: BLE001
        notes.append(f"knowledge write: FAILED ({type(exc).__name__}: {exc})")
    return notes
