from jobpilot import companies
from jobpilot.companies import CompanyRow
from tests.test_sources import make_cfg


def test_merge_into_sources_adds_creates_and_dedupes():
    cfg = make_cfg()  # greenhouse already has ["stripe"]; no workday source yet
    rows = [
        CompanyRow(row=2, company="Nvidia", ats="workday",
                   slug="nvidia/wd5/Ext", status="active"),
        CompanyRow(row=3, company="Stripe", ats="greenhouse", slug="stripe",
                   status="active"),
        CompanyRow(row=4, company="Mystery", status="unsupported"),
        CompanyRow(row=5, company="Typo Co", ats="linkedin", slug="x", status="active"),
    ]
    companies.merge_into_sources(cfg, rows)
    assert cfg.sources["workday"].companies == ["nvidia/wd5/Ext"]
    assert cfg.sources["workday"].enabled
    assert cfg.sources["greenhouse"].companies.count("stripe") == 1
    assert "linkedin" not in cfg.sources


def test_status_updates_counts_404s_and_skips_untouched():
    rows = [
        CompanyRow(row=2, company="A", ats="greenhouse", slug="a", status="active"),
        CompanyRow(row=3, company="B", ats="greenhouse", slug="b", status="active"),
        CompanyRow(row=4, company="C", ats="lever", slug="c", status="active"),
        CompanyRow(row=5, company="D", status="unsupported",
                   notes="no public ATS API found", dirty=True),
        CompanyRow(row=6, company="E", ats="greenhouse", slug="e",
                   status="error: 404 since 2026-06-01"),
    ]
    stats = {"greenhouse": {"a": "3", "b": "404", "e": "404"}}
    ups = dict(companies.status_updates(rows, stats, "2026-06-11 12:00"))
    assert ups[2] == ["greenhouse", "a", "active", "2026-06-11 12:00", "3", ""]
    assert ups[3][2] == "error: 404 since 2026-06-11"
    assert 4 not in ups  # no stats, not dirty -> row untouched
    assert ups[5][2] == "unsupported"
    assert ups[6][2] == "error: 404 since 2026-06-01"  # original since-date kept
