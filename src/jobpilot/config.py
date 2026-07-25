"""Load and validate profile.yaml — the single source of truth for every stage.

The JOBPILOT_PROFILE_YAML env var (e.g. mounted from Secret Manager) overrides the
file, letting deployments keep personal data out of the repo entirely.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

from jobpilot.apply.profile import ApplicationProfile


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Profile(_Strict):
    name: str
    headline: str
    sponsorship_needed: bool
    locations: list[str]
    summary: str = ""
    portfolio: str = ""  # outreach signature links
    linkedin: str = ""
    github: str = ""


class SourceCfg(_Strict):
    enabled: bool = True
    companies: list[str] = []  # greenhouse/lever/ashby board slugs
    actor_id: str = ""  # apify
    max_items: int = 100


class Scoring(_Strict):
    threshold: int = 75
    model: str = "gemini-flash-latest"


class Tailoring(_Strict):
    enabled: bool = True
    auto_threshold: int = 75  # auto-tailor jobs scoring at/above this
    max_per_run: int = 15  # compute cap per pipeline run
    attempts: int = 10  # judge-driven rewrite loop: best of up to N attempts
    drive_folder: str = "JobPilot Resumes/Tailored"


class Masters(_Strict):
    """Drive file ids of the master resume PDFs, per variant (for regeneration)."""
    pdf_ids: dict[str, str] = {}


class Caps(_Strict):
    shortlist: int = 25
    per_source: int = 100
    per_company: int = 25  # max matched jobs per company per run (board sources)
    freshness_days: int = 7  # drop postings older than this
    # Board sources list a job only while it is open, but the console promises a
    # fresh list, so boards get 14 days and aggregators keep 7.
    board_freshness_days: int = 14


class SheetCfg(_Strict):
    spreadsheet_id: str = ""


class DigestCfg(_Strict):
    to: str


class InboxWatchCfg(_Strict):
    """Multi-account reply detection (docs/superpowers/specs/2026-06-10-inbox-watch-design.md)."""

    enabled: bool = True
    lookback_days: int = 2
    max_messages: int = 50


DEFAULT_EXCLUDES = [
    "manager", "director", "principal", "staff", "distinguished", "vp",
    "intern", "internship", "phd",
]

# Jobs whose description matches any of these are dropped before scoring —
# citizenship/clearance/no-sponsorship requirements the candidate can never meet.
DEFAULT_JD_EXCLUDES = [
    r"\bU\.?S\.?\s+citizen(ship)?\b",
    r"\bcitizenship\s+(is\s+)?required\b",
    r"\bmust\s+be\s+(a\s+)?(U\.?S\.?\s+)?citizen\b",
    r"\bgreen\s*card\b",
    r"\bpermanent\s+resident(s|cy)?\s+(only|required)\b",
    r"\bsecurity\s+clearance\b",
    r"\b(TS/?SCI|top\s+secret|secret\s+clearance)\b",
    r"\bpolygraph\b",
    r"\bpublic\s+trust\b",
    r"\bITAR\b",
    r"\bU\.?S\.?\s+persons?\s+(only|requirement)\b",
    r"\b(no|not\s+offer(ing)?|unable\s+to\s+(provide|offer))\s+(visa\s+)?sponsorship\b",
    r"\bwithout\s+(the\s+need\s+for\s+)?(visa\s+)?sponsorship\b",
    r"\bnot\s+able\s+to\s+sponsor\b",
    r"\bcannot\s+sponsor\b",
    r"\bwill\s+not\s+sponsor\b",
]


class Config(_Strict):
    profile: Profile
    queries: list[str]
    us_only: bool = True  # drop postings whose location is clearly outside the US
    exclude_title_words: list[str] = DEFAULT_EXCLUDES
    exclude_jd_patterns: list[str] = DEFAULT_JD_EXCLUDES
    sources: dict[str, SourceCfg]
    scoring: Scoring = Scoring()
    tailoring: Tailoring = Tailoring()
    masters: Masters = Masters()
    caps: Caps = Caps()
    sheet: SheetCfg = SheetCfg()
    digest: DigestCfg
    inbox_watch: InboxWatchCfg = InboxWatchCfg()
    application: ApplicationProfile | None = None

    @classmethod
    def load(cls, path: str | Path) -> "Config":
        raw = os.environ.get("JOBPILOT_PROFILE_YAML")
        text = raw if raw else Path(path).read_text(encoding="utf-8")
        return cls.model_validate(yaml.safe_load(text))

    def enabled_sources(self) -> dict[str, SourceCfg]:
        return {name: sc for name, sc in self.sources.items() if sc.enabled}
