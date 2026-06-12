from datetime import datetime, timedelta, timezone

import jobpilot.pipeline as pipeline
from jobpilot.models import Posting
from tests.test_sources import make_cfg


def fake_registry():
    def fake_fetch(sc, cfg, client):
        return [
            Posting(title="ML Engineer", company="Acme", url="u1", source="greenhouse"),
            Posting(title="ML Engineer", company="Acme", url="u1", source="greenhouse"),
            Posting(title="Data Engineer", company="Beta", url="u2", source="greenhouse"),
            Posting(  # stale: outside freshness window
                title="AI Engineer", company="Old", url="u3", source="greenhouse",
                posted_at=datetime.now(timezone.utc) - timedelta(days=400),
            ),
            Posting(  # excluded seniority word
                title="Engineering Manager", company="Acme", url="u4", source="greenhouse",
            ),
            Posting(
                title="Staff Software Engineer", company="Beta", url="u5", source="greenhouse",
            ),
            Posting(  # citizenship requirement buried in the JD — must never appear
                title="ML Engineer", company="Defense Co", url="u6", source="greenhouse",
                description="Great role. Applicants must be a U.S. citizen due to contracts.",
            ),
            Posting(  # clearance requirement
                title="AI Engineer", company="Gov Co", url="u7", source="greenhouse",
                description="Requires an active TS/SCI security clearance.",
            ),
            Posting(  # no-sponsorship requirement
                title="Data Engineer", company="NoVisa Inc", url="u8", source="greenhouse",
                description="Must be authorized to work without sponsorship now and in the future.",
            ),
        ]

    def broken_fetch(sc, cfg, client):
        raise RuntimeError("boom")

    return {"greenhouse": fake_fetch, "lever": broken_fetch}


def test_quality_filter_board_sources_keep_older_postings():
    # a posting on the company's own board is open as long as it is listed —
    # only aggregator sources go stale at freshness_days
    now = datetime.now(timezone.utc)
    month_old = now - timedelta(days=30)
    cfg = make_cfg()
    postings = [
        Posting(title="ML Engineer", company="A", url="u1", source="greenhouse",
                posted_at=month_old),
        Posting(title="ML Engineer", company="B", url="u2", source="adzuna",
                posted_at=month_old),
        Posting(title="ML Engineer", company="C", url="u3", source="workday",
                posted_at=now - timedelta(days=90)),  # beyond even the board window
    ]
    out = pipeline.quality_filter(postings, cfg, now)
    assert [p.company for p in out] == ["A"]


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
