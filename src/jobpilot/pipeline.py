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
from jobpilot.sources import common as sources_common


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
    from jobpilot.sources import common

    common.RUN_STATS.clear()
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


# Clearly-non-US location markers (countries, hub cities, regions). A posting is
# dropped only when one of these matches AND no US hint is present, so
# "London or Remote (US)" survives. Empty/ambiguous locations are kept — the
# scorer judges those.
NON_US_RE = re.compile(
    r"\b(Canada|Toronto|Montreal|Ottawa|Calgary|Vancouver|"
    r"UK|U\.K\.|United Kingdom|England|Scotland|London|Ireland|Dublin|"
    r"Germany|Berlin|Munich|France|Paris|Netherlands|Amsterdam|Belgium|Brussels|"
    r"Spain|Madrid|Barcelona|Portugal|Lisbon|Italy|Milan|Rome|"
    r"Poland|Warsaw|Krakow|Czech|Prague|Hungary|Budapest|Romania|Bucharest|"
    r"Sweden|Stockholm|Denmark|Copenhagen|Norway|Oslo|Finland|Helsinki|"
    r"Switzerland|Zurich|Geneva|Austria|Vienna|Greece|Athens|Estonia|Tallinn|"
    r"Ukraine|Kyiv|Turkey|Istanbul|Israel|Tel Aviv|UAE|Dubai|Abu Dhabi|"
    r"Saudi|Riyadh|Egypt|Cairo|Nigeria|Lagos|South Africa|Cape Town|Johannesburg|"
    r"India|Bengaluru|Bangalore|Hyderabad|Pune|Mumbai|Delhi|Gurgaon|Gurugram|"
    r"Noida|Chennai|Singapore|Japan|Tokyo|China|Shanghai|Beijing|Shenzhen|"
    r"Hong Kong|Taiwan|Taipei|Korea|Seoul|Vietnam|Indonesia|Jakarta|Thailand|"
    r"Bangkok|Malaysia|Kuala Lumpur|Philippines|Manila|"
    r"Australia|Sydney|Melbourne|Brisbane|New Zealand|Auckland|"
    r"Brazil|S[aã]o Paulo|Mexico City|Argentina|Buenos Aires|Colombia|Bogot[aá]|"
    r"Chile|Santiago|Costa Rica|EMEA|APAC|LATAM|Europe)\b",
    re.IGNORECASE,
)
US_HINT_RE = re.compile(
    r"\b(US|USA|U\.S\.|United States|America|Remote)\b"
    # ", XX" US state code — keeps "Vancouver, WA" and friends
    r"|,\s*(A[KLRZ]|C[AOT]|D[CE]|FL|GA|HI|I[ADLN]|K[SY]|LA|M[ADEINOST]"
    r"|N[CDEHJMVY]|O[HKR]|PA|RI|S[CD]|T[NX]|UT|V[AT]|W[AIVY])\b",
    re.IGNORECASE)


def is_non_us(location: str) -> bool:
    return bool(NON_US_RE.search(location)) and not US_HINT_RE.search(location)


def quality_filter(postings: list[Posting], cfg: Config, now: datetime) -> list[Posting]:
    """Drop undated/stale postings, excluded seniority/role words, non-US
    locations, and citizenship/clearance JDs."""
    from jobpilot.companies import ATS_SOURCES

    cutoff = now - timedelta(days=cfg.caps.freshness_days)
    board_cutoff = now - timedelta(days=cfg.caps.board_freshness_days)
    jd_patterns = [re.compile(pat, re.IGNORECASE) for pat in cfg.exclude_jd_patterns]
    out = []
    for p in postings:
        limit = board_cutoff if p.source in ATS_SOURCES else cutoff
        if p.posted_at is None:
            # No trustworthy date, no entry: the job never reaches dedup memory,
            # so a later run that does get a date can still admit it.
            sources_common.RUN_STATS["dropped_undated"] = (
                sources_common.RUN_STATS.get("dropped_undated", 0) + 1)
            continue
        if p.posted_at < limit:
            sources_common.RUN_STATS["dropped_stale"] = (
                sources_common.RUN_STATS.get("dropped_stale", 0) + 1)
            continue
        if cfg.us_only and is_non_us(p.location):
            continue
        title = p.title.lower()
        if any(re.search(rf"\b{re.escape(w)}\b", title) for w in cfg.exclude_title_words):
            continue
        text = f"{p.title}\n{p.description}"
        if any(pat.search(text) for pat in jd_patterns):
            continue  # citizenship / clearance / no-sponsorship — never show these
        out.append(p)
    return out


def _apply_quality_filter(postings: list[Posting], cfg: Config, now: datetime,
                          notes: list[str]) -> list[Posting]:
    fresh = quality_filter(postings, cfg, now)
    stats = sources_common.RUN_STATS
    notes.append(
        f"freshness/seniority filter: kept {len(fresh)} of {len(postings)} "
        f"(windows {cfg.caps.freshness_days}d/{cfg.caps.board_freshness_days}d board, "
        f"dropped undated {stats.get('dropped_undated', 0)}, "
        f"stale {stats.get('dropped_stale', 0)})"
    )
    return fresh


def run(cfg: Config, dry_run: bool = False, only: list[str] | None = None,
        fast: bool = False) -> list[Scored]:
    now = datetime.now(timezone.utc)

    if dry_run:
        postings, notes = fetch_all(cfg, only)
        postings = _apply_quality_filter(postings, cfg, now, notes)
        new = dedup.filter_new(postings, set())
        scored = score(new, cfg, _stub_llm)
        notes.append(f"dedup: {len(new)} new of {len(postings)} fetched (no sheet in dry-run)")
        _print_table(scored, now)
        html = digest.build_html(scored, "https://sheet.example", now, cfg.scoring.threshold, notes)
        Path("digest_preview.html").write_text(html, encoding="utf-8")
        print(f"\n{len(scored)} jobs; digest preview -> digest_preview.html")
        return scored

    from jobpilot import companies, inboxwatch, resolver
    from jobpilot.gauth import credentials, inbox_credentials

    creds = credentials()
    sid = os.environ.get("JOBPILOT_SPREADSHEET_ID") or cfg.sheet.spreadsheet_id
    sid = sheets.ensure_dashboard(creds, sid)
    sheets.ensure_archive_tab(creds, sid)

    watchlist = companies.load(creds, sid)
    resolver_notes = resolver.resolve_pending(watchlist)
    companies.merge_into_sources(cfg, watchlist)

    postings, notes = fetch_all(cfg, only)
    notes.extend(resolver_notes)
    sheets.update_company_rows(
        creds, sid,
        companies.status_updates(watchlist, sources_common.RUN_STATS,
                                 now.strftime("%Y-%m-%d %H:%M")),
    )
    postings = _apply_quality_filter(postings, cfg, now, notes)

    llm = make_gemini_llm(cfg)
    new = dedup.filter_new(postings, sheets.known_ids(creds, sid))
    notes.append(f"dedup: {len(new)} new of {len(postings)} fetched")
    scored = score(new, cfg, llm)
    # route_jobs is the single source of truth for the Jobs/Archive split, so
    # n_matches and the digest below can never describe a job that append_jobs
    # actually routed to Archive (e.g. a high-fit sponsorship auto-reject).
    to_jobs, _ = sheets.route_jobs(scored, cfg.scoring.threshold)
    n_jobs, n_archived = sheets.append_jobs(creds, sid, scored, now,
                                            min_fit=cfg.scoring.threshold)
    notes.append(f"write gate: {n_jobs} to Jobs, {n_archived} archived "
                f"(low fit or auto-rejected)")
    n_matches = len(to_jobs)

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

    from jobpilot import archiver, knowledge
    from jobpilot.outreach import auto_outreach
    from jobpilot.tailor import auto_tailor, make_tailor_llm

    # Nightly aging sweep: full runs only (fast/console-refresh already returned
    # above). Runs before tailoring/outreach so their per-run compute caps are
    # spent on rows that survive as fresh and actionable, not ones about to be
    # archived; its note is folded into `notes`, which reaches tonight's digest.
    notes.extend(archiver.sweep(creds, sid, cfg, now))
    sheets.refresh_stats(creds, sid)  # live tab decays to literal zeros otherwise

    tailor_llm = make_tailor_llm(cfg)
    notes.extend(auto_tailor(creds, sid, cfg, tailor_llm, now))
    notes.extend(auto_outreach(creds, sid, cfg, tailor_llm, now))

    from jobpilot import portfolio_graph
    pg_llm = make_gemini_llm(cfg, schema=portfolio_graph.PageExtract)
    pg_client = httpx.Client(timeout=20, follow_redirects=True, headers=portfolio_graph.UA)
    notes.extend(portfolio_graph.rebuild(creds, sid, cfg, pg_llm, pg_client, now))

    notes.extend(knowledge.refresh(creds, sid, cfg, now))  # keeps the Assistant grounded
    # Only the Jobs-bound list: the digest must describe what the owner will
    # actually see in the Jobs tab, not rows route_jobs sent to Archive.
    html = digest.build_html(to_jobs, sheets.url_for(sid), now, cfg.scoring.threshold, notes)
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
