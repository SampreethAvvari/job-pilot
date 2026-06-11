"""Job source registry. Every module exposes fetch(sc, cfg, client) -> list[Posting]."""

from __future__ import annotations

from typing import Callable

import httpx

from jobpilot.config import Config, SourceCfg
from jobpilot.models import Posting


class SourceError(Exception):
    """A source failed; the pipeline records the failure and continues."""


class SourceSkipped(Exception):
    """A source was skipped (e.g. missing API key); noted in the digest."""


FetchFn = Callable[[SourceCfg, Config, httpx.Client], list[Posting]]


def registry() -> dict[str, FetchFn]:
    from jobpilot.sources import (
        adzuna,
        apify_linkedin,
        ashby,
        greenhouse,
        hn_hiring,
        lever,
        recruitee,
        remoteok,
        smartrecruiters,
        workable,
        workday,
    )

    return {
        "greenhouse": greenhouse.fetch,
        "lever": lever.fetch,
        "ashby": ashby.fetch,
        "workday": workday.fetch,
        "smartrecruiters": smartrecruiters.fetch,
        "workable": workable.fetch,
        "recruitee": recruitee.fetch,
        "remoteok": remoteok.fetch,
        "hn_hiring": hn_hiring.fetch,
        "adzuna": adzuna.fetch,
        "apify_linkedin": apify_linkedin.fetch,
    }
