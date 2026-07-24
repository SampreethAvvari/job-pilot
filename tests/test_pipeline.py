from datetime import datetime, timedelta, timezone

import pytest

import jobpilot.pipeline as pipeline
from jobpilot.models import Posting
from tests.test_sources import make_cfg


@pytest.fixture
def base_cfg():
    return make_cfg()


def fake_registry():
    def fake_fetch(sc, cfg, client):
        recent = datetime.now(timezone.utc) - timedelta(days=1)
        return [
            Posting(title="ML Engineer", company="Acme", url="u1", source="greenhouse",
                    posted_at=recent),
            Posting(title="ML Engineer", company="Acme", url="u1", source="greenhouse",
                    posted_at=recent),
            Posting(title="Data Engineer", company="Beta", url="u2", source="greenhouse",
                    posted_at=recent),
            Posting(  # stale: outside freshness window
                title="AI Engineer", company="Old", url="u3", source="greenhouse",
                posted_at=datetime.now(timezone.utc) - timedelta(days=400),
            ),
            Posting(  # excluded seniority word
                title="Engineering Manager", company="Acme", url="u4", source="greenhouse",
                posted_at=recent,
            ),
            Posting(
                title="Staff Software Engineer", company="Beta", url="u5", source="greenhouse",
                posted_at=recent,
            ),
            Posting(  # citizenship requirement buried in the JD — must never appear
                title="ML Engineer", company="Defense Co", url="u6", source="greenhouse",
                description="Great role. Applicants must be a U.S. citizen due to contracts.",
                posted_at=recent,
            ),
            Posting(  # clearance requirement
                title="AI Engineer", company="Gov Co", url="u7", source="greenhouse",
                description="Requires an active TS/SCI security clearance.",
                posted_at=recent,
            ),
            Posting(  # no-sponsorship requirement
                title="Data Engineer", company="NoVisa Inc", url="u8", source="greenhouse",
                description="Must be authorized to work without sponsorship now and in the future.",
                posted_at=recent,
            ),
        ]

    def broken_fetch(sc, cfg, client):
        raise RuntimeError("boom")

    return {"greenhouse": fake_fetch, "lever": broken_fetch}


def test_quality_filter_board_sources_keep_older_postings():
    # a posting on the company's own board is open longer than an aggregator
    # listing, so boards get their own (still finite) 14 day freshness window
    now = datetime.now(timezone.utc)
    ten_days_old = now - timedelta(days=10)
    cfg = make_cfg()
    postings = [
        Posting(title="ML Engineer", company="A", url="u1", source="greenhouse",
                posted_at=ten_days_old),
        Posting(title="ML Engineer", company="B", url="u2", source="adzuna",
                posted_at=ten_days_old),
        Posting(title="ML Engineer", company="C", url="u3", source="workday",
                posted_at=now - timedelta(days=20)),  # beyond even the board window
    ]
    out = pipeline.quality_filter(postings, cfg, now)
    assert [p.company for p in out] == ["A"]


def test_quality_filter_drops_non_us_locations():
    cfg = make_cfg()
    now = datetime.now(timezone.utc)
    recent = now - timedelta(days=1)
    postings = [
        Posting(title="ML Engineer", company="A", url="u1", source="greenhouse",
                posted_at=recent, location="New York, NY"),
        Posting(title="ML Engineer", company="B", url="u2", source="greenhouse",
                posted_at=recent, location="Sydney, Australia"),
        Posting(title="ML Engineer", company="C", url="u3", source="ashby",
                posted_at=recent, location="Bengaluru, India"),
        Posting(title="ML Engineer", company="D", url="u4", source="ashby", posted_at=recent,
                location="London, UK or Remote (US)"),  # US option present — keep
        Posting(title="ML Engineer", company="E", url="u5", source="recruitee",
                posted_at=recent, location="Amsterdam, Netherlands"),
        Posting(title="ML Engineer", company="F", url="u6", source="lever",
                posted_at=recent, location="Remote"),  # ambiguous — keep, the scorer judges
        Posting(title="ML Engineer", company="G", url="u7", source="lever",
                posted_at=recent, location=""),  # unknown — keep
        Posting(title="ML Engineer", company="H", url="u8", source="lever", posted_at=recent,
                location="Vancouver, WA"),  # US state code beats city collision
    ]
    out = pipeline.quality_filter(postings, cfg, now)
    assert [p.company for p in out] == ["A", "D", "F", "G", "H"]


def test_quality_filter_us_only_can_be_disabled():
    cfg = make_cfg()
    cfg.us_only = False
    now = datetime.now(timezone.utc)
    postings = [Posting(title="ML Engineer", company="B", url="u", source="greenhouse",
                        posted_at=now - timedelta(days=1), location="Sydney, Australia")]
    out = pipeline.quality_filter(postings, cfg, now)
    assert len(out) == 1


def test_dry_run_end_to_end(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(pipeline, "registry", fake_registry)
    monkeypatch.chdir(tmp_path)
    cfg = make_cfg()
    for name in list(cfg.sources):
        cfg.sources[name].enabled = name in ("greenhouse", "lever")

    scored = pipeline.run(cfg, dry_run=True)

    assert len(scored) == 2  # self-dup collapsed; stale/senior/citizenship/clearance dropped
    assert {s.posting.company for s in scored} == {"Acme", "Beta"}
    assert all(s.fit_score == 70 for s in scored)
    assert (tmp_path / "digest_preview.html").exists()
    out = capsys.readouterr().out
    assert "lever: FAILED" in out or "FAILED" in (tmp_path / "digest_preview.html").read_text(
        encoding="utf-8"
    )


def _posting(source="adzuna", days_old=1, undated=False, **kw):
    now = datetime(2026, 7, 23, tzinfo=timezone.utc)
    return Posting(
        id="", title=kw.get("title", "AI Engineer"), company=kw.get("company", "Acme"),
        location=kw.get("location", "New York, NY"), url="https://x.example/j",
        source=source, description=kw.get("description", "build llm products"),
        posted_at=None if undated else now - timedelta(days=days_old),
    )


def test_quality_filter_drops_undated_postings(base_cfg):
    from jobpilot.sources import common

    now = datetime(2026, 7, 23, tzinfo=timezone.utc)
    common.RUN_STATS.clear()
    kept = pipeline.quality_filter([_posting(undated=True), _posting(days_old=1)], base_cfg, now)
    assert len(kept) == 1 and kept[0].posted_at is not None
    assert common.RUN_STATS["dropped_undated"] == 1


def test_quality_filter_board_window_is_14_days(base_cfg):
    now = datetime(2026, 7, 23, tzinfo=timezone.utc)
    fresh_board = _posting(source="greenhouse", days_old=10)
    stale_board = _posting(source="greenhouse", days_old=20)
    kept = pipeline.quality_filter([fresh_board, stale_board], base_cfg, now)
    assert kept == [fresh_board]


def _patch_full_run(monkeypatch, calls):
    """Stub every dependency the full (non-fast) `run()` path touches, past
    fetch/score/record, so the test can observe call order without hitting
    Google/Gemini. Returns nothing; mutates `calls` as a side effect."""
    import jobpilot.archiver as archiver
    import jobpilot.companies as companies
    import jobpilot.gauth as gauth
    import jobpilot.inboxwatch as inboxwatch
    import jobpilot.knowledge as knowledge
    import jobpilot.outreach as outreach_mod
    import jobpilot.portfolio_graph as portfolio_graph
    import jobpilot.resolver as resolver
    import jobpilot.tailor as tailor_mod

    monkeypatch.setattr(gauth, "credentials", lambda: "creds")
    monkeypatch.setattr(gauth, "inbox_credentials", lambda: {})
    monkeypatch.setattr(pipeline, "fetch_all", lambda cfg, only=None: ([], ["fetch: 0"]))
    monkeypatch.setattr(pipeline.sheets, "ensure_dashboard", lambda creds, sid: "SID")
    monkeypatch.setattr(pipeline.sheets, "ensure_archive_tab", lambda creds, sid: None)
    monkeypatch.setattr(pipeline.sheets, "update_company_rows",
                        lambda creds, sid, updates: None)
    monkeypatch.setattr(pipeline.sheets, "known_ids", lambda creds, sid: set())
    monkeypatch.setattr(pipeline.sheets, "route_jobs", lambda scored, min_fit: (scored, []))
    monkeypatch.setattr(pipeline.sheets, "append_jobs",
                        lambda creds, sid, scored, now, min_fit: (0, 0))
    monkeypatch.setattr(pipeline.sheets, "refresh_stats", lambda creds, sid: None)
    monkeypatch.setattr(pipeline.sheets, "url_for", lambda sid: "https://sheet.example")
    monkeypatch.setattr(companies, "load", lambda creds, sid: [])
    monkeypatch.setattr(companies, "merge_into_sources", lambda cfg, rows: None)
    monkeypatch.setattr(companies, "status_updates", lambda rows, stats, ts: [])
    monkeypatch.setattr(resolver, "resolve_pending", lambda rows: [])
    monkeypatch.setattr(inboxwatch, "watch", lambda *a, **k: [])
    monkeypatch.setattr(archiver, "sweep", lambda creds, sid, cfg, now: [])
    monkeypatch.setattr(tailor_mod, "auto_tailor", lambda creds, sid, cfg, llm, now: [])
    monkeypatch.setattr(tailor_mod, "make_tailor_llm", lambda cfg: (lambda p: ""))
    monkeypatch.setattr(outreach_mod, "auto_outreach", lambda creds, sid, cfg, llm, now: [])
    monkeypatch.setattr(pipeline, "make_gemini_llm", lambda cfg, schema=None: (lambda p: "{}"))
    monkeypatch.setattr(pipeline, "score", lambda postings, cfg, llm: [])
    monkeypatch.setattr(pipeline.digest, "build_html", lambda *a, **k: "<html></html>")
    monkeypatch.setattr(pipeline.digest, "send", lambda *a, **k: None)

    def fake_rebuild(creds, sid, cfg_, llm, client, now):
        calls.append("portfolio_graph")
        return ["portfolio graph: rebuilt"]

    def fake_knowledge_refresh(creds, sid, cfg_, now):
        calls.append("knowledge")
        return ["knowledge: refreshed"]

    monkeypatch.setattr(portfolio_graph, "rebuild", fake_rebuild)
    monkeypatch.setattr(knowledge, "refresh", fake_knowledge_refresh)


def test_full_run_rebuilds_portfolio_graph_before_knowledge_refresh(monkeypatch, base_cfg):
    calls: list[str] = []
    _patch_full_run(monkeypatch, calls)

    pipeline.run(base_cfg, dry_run=False, fast=False)

    assert calls == ["portfolio_graph", "knowledge"]


def test_fast_run_skips_portfolio_graph_rebuild(monkeypatch, base_cfg):
    calls: list[str] = []
    _patch_full_run(monkeypatch, calls)

    pipeline.run(base_cfg, dry_run=False, fast=True)

    assert calls == []
