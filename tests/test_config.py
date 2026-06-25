from pathlib import Path

import pytest
from pydantic import ValidationError

from jobpilot.config import Config

VALID = """
profile:
  name: Jane Doe
  headline: AI Engineer
  sponsorship_needed: true
  locations: [Brooklyn NY, Remote US, Anywhere US]
queries: [Forward Deployed Engineer, ML Engineer]
sources:
  greenhouse:
    enabled: true
    companies: [databricks]
  remoteok:
    enabled: false
digest:
  to: you@example.com
"""


def _write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "profile.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_loads_valid_config(tmp_path):
    cfg = Config.load(_write(tmp_path, VALID))
    assert cfg.profile.sponsorship_needed is True
    assert cfg.scoring.threshold == 60  # default
    assert cfg.sources["greenhouse"].companies == ["databricks"]
    assert list(cfg.enabled_sources()) == ["greenhouse"]


def test_rejects_unknown_keys(tmp_path):
    with pytest.raises(ValidationError):
        Config.load(_write(tmp_path, VALID + "\nunknown_key: 1\n"))


def test_repo_profile_template_is_valid():
    cfg = Config.load(Path(__file__).parent.parent / "profile.yaml")
    assert "@" in cfg.digest.to
    assert len(cfg.queries) >= 3
    assert cfg.sources["apify_linkedin"].actor_id


def test_inbox_watch_defaults(tmp_path):
    cfg = Config.load(_write(tmp_path, VALID))
    assert cfg.inbox_watch.enabled is True
    assert cfg.inbox_watch.lookback_days == 2
    assert cfg.inbox_watch.max_messages == 50


def test_env_override_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBPILOT_PROFILE_YAML", VALID)
    cfg = Config.load(tmp_path / "does-not-exist.yaml")
    assert cfg.profile.name == "Jane Doe"


def test_caps_per_company_default(tmp_path):
    cfg = Config.load(_write(tmp_path, VALID))
    assert cfg.caps.per_company == 25
