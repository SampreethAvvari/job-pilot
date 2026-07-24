"""Portfolio knowledge graph: crawl the portfolio, extract per-project facts with
Gemini, assemble a nodes+edges graph, store it, and render it into the Knowledge pack.

Grounds the Assistant chat and the auto-apply answer engine in real project facts and
links. Spec: docs/superpowers/specs/2026-07-24-auto-apply-design.md
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urljoin, urlparse

import httpx
from pydantic import BaseModel, Field

from jobpilot.scorer import LlmFn
from jobpilot.sources.common import strip_html

NodeType = Literal["project", "skill", "technology", "company", "outcome"]
EdgeRel = Literal["used-tech", "solved-problem", "built-at", "achieved", "links-to"]


class ProjectFacts(BaseModel):
    name: str
    one_line: str = ""
    problem: str = ""
    approach: str = ""
    stack: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    role: str = ""
    company: str = ""
    dates: str = ""
    links: dict[str, str] = Field(default_factory=dict)


class PageExtract(BaseModel):
    """Per-page LLM output under the extraction schema."""
    projects: list[ProjectFacts] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)


class GraphNode(BaseModel):
    id: str
    type: NodeType
    label: str
    data: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    source: str
    target: str
    rel: EdgeRel


class PortfolioGraph(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    crawled_at: str = ""
    sources: list[str] = Field(default_factory=list)


UA = {"User-Agent": "Mozilla/5.0 (compatible; JobPilot)"}
SEED_PATHS = ("/", "/projects", "/posts", "/work")
_HREF_RE = re.compile(r'href=["\'](.*?)["\']', re.I)
MAX_PAGES = 40
PAGE_CHARS = 8000


def _same_host(url: str, base: str) -> bool:
    return urlparse(url).netloc == urlparse(base).netloc


def discover_urls(base: str, client: httpx.Client) -> list[str]:
    """Seed pages plus same-host links found on them. Base first, deduped, capped."""
    base = base.rstrip("/")
    seeds = [base + p for p in SEED_PATHS]
    seen: list[str] = []
    order: list[str] = []

    def add(u: str) -> None:
        u_normalized = u.split("#")[0].rstrip("/")
        if u_normalized and u_normalized not in seen and _same_host(u_normalized, base):
            seen.append(u_normalized)
            order.append(u)  # keep original u

    add(base + "/")  # add base with trailing slash
    for seed in seeds:
        try:
            resp = client.get(seed, headers=UA)
            resp.raise_for_status()
        except httpx.HTTPError:
            continue
        add(seed)
        for href in _HREF_RE.findall(resp.text):
            add(urljoin(seed.rstrip("/") + "/", href))
    # Base must sort first; keep discovery order otherwise.
    order.sort(key=lambda u: (u.rstrip("/") != base,))
    return order[:MAX_PAGES]


def fetch_pages(urls: list[str], client: httpx.Client) -> list[tuple[str, str]]:
    """(url, stripped text) for each page that loads; dead pages skipped."""
    out: list[tuple[str, str]] = []
    for url in urls:
        try:
            resp = client.get(url, headers=UA)
            resp.raise_for_status()
        except httpx.HTTPError:
            continue
        text = strip_html(resp.text)[:PAGE_CHARS]
        if text:
            out.append((url, text))
    return out


EXTRACT_PROMPT = Path(__file__).parent / "prompts" / "portfolio_extract_v1.txt"


def extract_page(url: str, text: str, llm: LlmFn) -> PageExtract:
    """Extract project facts from one page. Degrades to empty on any failure."""
    prompt = EXTRACT_PROMPT.read_text(encoding="utf-8").format(url=url, content=text)
    for attempt in (1, 2):
        try:
            return PageExtract.model_validate_json(llm(prompt))
        except Exception:  # malformed output, schema mismatch, or API error
            if attempt == 2:
                return PageExtract()
    return PageExtract()
