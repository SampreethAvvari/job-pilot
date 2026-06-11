import json
import re
from pathlib import Path

import httpx
import pytest

from jobpilot.config import Config
from jobpilot.sources import SourceSkipped, registry
from jobpilot.sources import adzuna, apify_linkedin, ashby, greenhouse, hn_hiring, lever, remoteok

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def make_cfg(**source_overrides) -> Config:
    sources = {
        "greenhouse": {"companies": ["stripe"]},
        "lever": {"companies": ["palantir"]},
        "ashby": {"companies": ["notion"]},
        "remoteok": {},
        "hn_hiring": {"max_items": 50},
        "adzuna": {},
        "apify_linkedin": {"actor_id": "x~y", "max_items": 10},
    }
    sources.update(source_overrides)
    return Config.model_validate(
        {
            "profile": {
                "name": "S",
                "headline": "AI Engineer",
                "sponsorship_needed": True,
                "locations": ["NYC"],
                "summary": "AI Engineer building production ML systems; needs sponsorship",
            },
            "queries": ["Engineer", "Data Scientist"],
            "sources": sources,
            "digest": {"to": "x@y.z"},
        }
    )


def _assert_valid(postings, source_name):
    assert postings, f"{source_name} returned nothing"
    for p in postings:
        assert p.title and p.company and p.url
        assert p.source == source_name


def test_greenhouse(httpx_mock):
    httpx_mock.add_response(url=re.compile(r".*greenhouse.*"), json=load("greenhouse"))
    cfg = make_cfg()
    out = greenhouse.fetch(cfg.sources["greenhouse"], cfg, httpx.Client())
    _assert_valid(out, "greenhouse")
    assert any(p.posted_at for p in out)


def test_lever(httpx_mock):
    httpx_mock.add_response(url=re.compile(r".*lever.*"), json=load("lever"))
    cfg = make_cfg()
    out = lever.fetch(cfg.sources["lever"], cfg, httpx.Client())
    _assert_valid(out, "lever")
    assert any(p.posted_at for p in out)


def test_ashby(httpx_mock):
    httpx_mock.add_response(url=re.compile(r".*ashbyhq.*"), json=load("ashby"))
    cfg = make_cfg()
    out = ashby.fetch(cfg.sources["ashby"], cfg, httpx.Client())
    _assert_valid(out, "ashby")


def test_remoteok(httpx_mock):
    httpx_mock.add_response(url=re.compile(r".*remoteok.*"), json=load("remoteok"))
    cfg = make_cfg()
    out = remoteok.fetch(cfg.sources["remoteok"], cfg, httpx.Client())
    _assert_valid(out, "remoteok")
    assert all(p.remote for p in out)


def test_hn_hiring(httpx_mock):
    story = load("hn_story")
    story_id = next(
        h["objectID"] for h in story["hits"] if "who is hiring" in h["title"].lower()
    )
    httpx_mock.add_response(url=re.compile(r".*author_whoishiring.*"), json=story)
    httpx_mock.add_response(url=re.compile(rf".*story_{story_id}.*"), json=load("hn_comments"))
    cfg = make_cfg()
    out = hn_hiring.fetch(cfg.sources["hn_hiring"], cfg, httpx.Client())
    _assert_valid(out, "hn_hiring")


def test_adzuna_skipped_without_keys(monkeypatch):
    monkeypatch.delenv("ADZUNA_APP_ID", raising=False)
    monkeypatch.delenv("ADZUNA_APP_KEY", raising=False)
    cfg = make_cfg()
    with pytest.raises(SourceSkipped):
        adzuna.fetch(cfg.sources["adzuna"], cfg, httpx.Client())


def test_adzuna(httpx_mock, monkeypatch):
    monkeypatch.setenv("ADZUNA_APP_ID", "id")
    monkeypatch.setenv("ADZUNA_APP_KEY", "key")
    httpx_mock.add_response(
        url=re.compile(r".*adzuna.*"),
        json={
            "results": [
                {
                    "title": "ML Engineer",
                    "company": {"display_name": "Acme"},
                    "location": {"display_name": "New York, NY"},
                    "redirect_url": "https://adzuna.com/x",
                    "created": "2026-06-09T12:00:00Z",
                    "description": "desc",
                    "salary_min": 150000.0,
                    "salary_max": 200000.0,
                }
            ]
        },
        is_reusable=True,
    )
    cfg = make_cfg()
    out = adzuna.fetch(cfg.sources["adzuna"], cfg, httpx.Client())
    _assert_valid(out, "adzuna")
    assert out[0].salary == "$150,000–$200,000"


def test_apify_skipped_without_token(monkeypatch):
    monkeypatch.delenv("APIFY_TOKEN", raising=False)
    cfg = make_cfg()
    with pytest.raises(SourceSkipped):
        apify_linkedin.fetch(cfg.sources["apify_linkedin"], cfg, httpx.Client())


def test_apify(httpx_mock, monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "t")
    httpx_mock.add_response(
        method="POST",
        url=re.compile(r".*apify.*/acts/.*"),
        json={"data": {"id": "r1", "status": "SUCCEEDED", "defaultDatasetId": "d1"}},
    )
    httpx_mock.add_response(
        url=re.compile(r".*apify.*/datasets/d1/items.*"),
        json=[
            {
                "title": "Forward Deployed Engineer",
                "companyName": "Palantir",
                "location": "New York, NY",
                "jobUrl": "https://linkedin.com/jobs/1",
                "publishedAt": "2026-06-10T01:00:00Z",
                "description": "<p>desc</p>",
            }
        ],
    )
    cfg = make_cfg()
    out = apify_linkedin.fetch(cfg.sources["apify_linkedin"], cfg, httpx.Client())
    _assert_valid(out, "linkedin")
    assert out[0].description == "desc"


def test_fetch_many_isolates_errors_caps_and_records_stats(httpx_mock):
    from jobpilot.models import Posting
    from jobpilot.sources import common

    httpx_mock.add_response(url="https://x.test/good", json={})
    httpx_mock.add_response(url="https://x.test/bad", status_code=404)
    client = httpx.Client()

    def one(slug):
        client.get(f"https://x.test/{slug}").raise_for_status()
        return [
            Posting(title=f"Engineer {i}", company=slug, url="u", source="t")
            for i in range(3)
        ]

    common.RUN_STATS.clear()
    out = common.fetch_many("t", ["good", "bad"], one, per_company=2)
    assert len(out) == 2  # capped per company
    assert common.RUN_STATS["t"] == {"good": "2", "bad": "404"}


def test_registry_covers_all_profile_sources():
    real_cfg = Config.load(Path(__file__).parent.parent / "profile.yaml")
    assert set(real_cfg.sources) <= set(registry())
