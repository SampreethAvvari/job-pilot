"""Orchestrator: fetch → dedup → score → record → digest."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from jobpilot import dedup, digest, sheets
from jobpilot.config import Config
from jobpilot.models import Posting, posted_age
from jobpilot.scorer import Scored, make_gemini_llm, score
from jobpilot.sources import SourceSkipped, registry


def _stub_llm(prompt: str) -> str:
    """Dry-run scorer: deterministic, no API. Scores every job 70/MLE."""
    ids = re.findall(r'"id":\s*"([^"]+)"', prompt)
    return json.dumps(
        {
            "scores": [
                {
                    "id": pid,
                    "fit_score": 70,
                    "why": "dry-run stub score",
                    "sponsorship_signal": "unknown",
                    "resume_variant": "MLE",
                }
                for pid in ids
            ]
        }
    )


def fetch_all(cfg: Config, only: list[str] | None = None) -> tuple[list[Posting], list[str]]:
    client = httpx.Client(timeout=60, follow_redirects=True)
    postings: list[Posting] = []
    notes: list[str] = []
    for name, sc in cfg.enabled_sources().items():
        if only and name not in only:
            continue
        try:
            got = registry()[name](sc, cfg, client)
            postings.extend(got)
            notes.append(f"{name}: {len(got)} matching jobs")
        except SourceSkipped as exc:
            notes.append(f"{name}: skipped ({exc})")
        except Exception as exc:  # noqa: BLE001 — one bad source must not kill the run
            notes.append(f"{name}: FAILED ({type(exc).__name__}: {exc})")
    return postings, notes


def quality_filter(postings: list[Posting], cfg: Config, now: datetime) -> list[Posting]:
    """Drop stale postings, excluded seniority/role words, and citizenship/clearance JDs."""
    cutoff = now - timedelta(days=cfg.caps.freshness_days)
    jd_patterns = [re.compile(pat, re.IGNORECASE) for pat in cfg.exclude_jd_patterns]
    out = []
    for p in postings:
        if p.posted_at and p.posted_at < cutoff:
            continue
        title = p.title.lower()
        if any(re.search(rf"\b{re.escape(w)}\b", title) for w in cfg.exclude_title_words):
            continue
        text = f"{p.title}\n{p.description}"
        if any(pat.search(text) for pat in jd_patterns):
            continue  # citizenship / clearance / no-sponsorship — never show these
        out.append(p)
    return out


def run(cfg: Config, dry_run: bool = False, only: list[str] | None = None,
        fast: bool = False) -> list[Scored]:
    now = datetime.now(timezone.utc)
    postings, notes = fetch_all(cfg, only)
    fresh = quality_filter(postings, cfg, now)
    notes.append(
        f"freshness/seniority filter: kept {len(fresh)} of {len(postings)} "
        f"(window {cfg.caps.freshness_days}d)"
    )
    postings = fresh

    if dry_run:
        new = dedup.filter_new(postings, set())
        scored = score(new, cfg, _stub_llm)
        notes.append(f"dedup: {len(new)} new of {len(postings)} fetched (no sheet in dry-run)")
        _print_table(scored, now)
        html = digest.build_html(scored, "https://sheet.example", now, cfg.scoring.threshold, notes)
        Path("digest_preview.html").write_text(html, encoding="utf-8")
        print(f"\n{len(scored)} jobs; digest preview -> digest_preview.html")
        return scored

    from jobpilot import inboxwatch
    from jobpilot.gauth import credentials, inbox_credentials

    creds = credentials()
    sid = os.environ.get("JOBPILOT_SPREADSHEET_ID") or cfg.sheet.spreadsheet_id
    sid = sheets.ensure_dashboard(creds, sid)
    llm = make_gemini_llm(cfg)
    new = dedup.filter_new(postings, sheets.known_ids(creds, sid))
    notes.append(f"dedup: {len(new)} new of {len(postings)} fetched")
    scored = score(new, cfg, llm)
    sheets.append_jobs(creds, sid, scored, now)
    n_matches = sum(1 for s in scored if (s.fit_score or 0) >= cfg.scoring.threshold)

    watch_llm = make_gemini_llm(cfg, schema=inboxwatch.FindingBatch)
    watch_notes = inboxwatch.watch(creds, inbox_credentials(), sid, cfg, watch_llm, now)
    notes.extend(watch_notes)

    if fast:
        # Console-refresh mode: rows are in the sheet; tailoring/outreach/digest are
        # left to the next scheduled run. Inbox watch already ran (hourly alerts).
        print(f"fast run complete: {len(scored)} new jobs, {n_matches} matches, sheet {sid}")
        for note in watch_notes:
            print(note)
        return scored

    from jobpilot.outreach import auto_outreach
    from jobpilot.tailor import auto_tailor, make_tailor_llm

    tailor_llm = make_tailor_llm(cfg)
    notes.extend(auto_tailor(creds, sid, cfg, tailor_llm, now))
    notes.extend(auto_outreach(creds, sid, cfg, tailor_llm, now))
    html = digest.build_html(scored, sheets.url_for(sid), now, cfg.scoring.threshold, notes)
    digest.send(creds, cfg, html, now, n_matches)
    print(f"run complete: {len(scored)} new jobs, {n_matches} matches, sheet {sid}")
    return scored


def _print_table(scored: list[Scored], now: datetime) -> None:
    for s in sorted(scored, key=lambda s: s.fit_score or -1, reverse=True)[:40]:
        p = s.posting
        print(
            f"{s.fit_score or '—':>3} | {posted_age(p.posted_at, now):>7} | "
            f"{p.source:<10} | {p.company[:24]:<24} | {p.title[:48]}"
        )
