"""Portfolio knowledge graph: crawl the portfolio, extract per-project facts with
Gemini, assemble a nodes+edges graph, store it, and render it into the Knowledge pack.

Grounds the Assistant chat and the auto-apply answer engine in real project facts and
links. Spec: docs/superpowers/specs/2026-07-24-auto-apply-design.md
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urljoin, urlparse

import httpx
from pydantic import BaseModel, Field

from jobpilot import sheets
from jobpilot.config import Config
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


def _slug(text: str) -> str:
    """Convert text to URL-safe slug."""
    return re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")


def build_graph(extracts: list[PageExtract], sources: list[str],
                now_str: str) -> PortfolioGraph:
    """Merge per-page extracts into a deduped nodes+edges graph."""
    nodes: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []

    prefixes = {"project": "project", "skill": "skill", "technology": "tech",
                "company": "company", "outcome": "outcome"}

    def node(ntype: NodeType, label: str, data: dict | None = None) -> str:
        nid = f"{prefixes[ntype]}:{_slug(label)}"
        if nid not in nodes:
            nodes[nid] = GraphNode(id=nid, type=ntype, label=label, data=data or {})
        elif data:
            for k, v in data.items():
                if not v:
                    continue
                cur = nodes[nid].data.get(k)
                if isinstance(cur, list) and isinstance(v, list):
                    nodes[nid].data[k] = cur + [x for x in v if x not in cur]
                else:
                    nodes[nid].data[k] = v
        return nid

    def edge(src: str, dst: str, rel: EdgeRel) -> None:
        if not any(e.source == src and e.target == dst and e.rel == rel for e in edges):
            edges.append(GraphEdge(source=src, target=dst, rel=rel))

    for ex in extracts:
        for p in ex.projects:
            if not _slug(p.name):
                continue
            pid = node("project", p.name, {
                "one_line": p.one_line, "problem": p.problem, "approach": p.approach,
                "role": p.role, "dates": p.dates, "links": p.links,
                "metrics": p.metrics, "stack": p.stack})
            for tech in p.stack:
                if not _slug(tech):
                    continue
                edge(pid, node("technology", tech), "used-tech")
            if p.company and _slug(p.company):
                edge(pid, node("company", p.company), "built-at")
            for m in p.metrics:
                if not _slug(m):
                    continue
                edge(pid, node("outcome", m), "achieved")
            for url in p.links.values():
                edge(pid, node("outcome", url, {"url": url}), "links-to")
        for sk in ex.skills:
            if not _slug(sk):
                continue
            node("skill", sk)
        for tech in ex.technologies:
            if not _slug(tech):
                continue
            node("technology", tech)

    return PortfolioGraph(nodes=list(nodes.values()), edges=edges,
                          crawled_at=now_str, sources=sources)


def render_pack(graph: PortfolioGraph) -> str:
    """Flatten the graph into per-project Knowledge-pack text."""
    out: list[str] = []
    for n in graph.nodes:
        if n.type != "project":
            continue
        d = n.data
        parts = [f"## {n.label}"]
        if d.get("one_line"):
            parts.append(d["one_line"])
        if d.get("problem"):
            parts.append(f"Problem: {d['problem']}")
        if d.get("approach"):
            parts.append(f"Approach: {d['approach']}")
        if d.get("stack"):
            parts.append("Stack: " + ", ".join(d["stack"]))
        if d.get("metrics"):
            parts.append("Outcomes: " + "; ".join(d["metrics"]))
        links = d.get("links") or {}
        if links:
            parts.append("Links: " + " ".join(f"{k}={v}" for k, v in links.items()))
        out.append("\n".join(parts))
    return "\n\n".join(out)


def render_html(graph: PortfolioGraph) -> str:
    """Self-contained HTML map: embedded data, inline canvas layout, no external
    assets. Only id/type/label (nodes) and source/target/rel (edges) are embedded
    — the full node `data` blob (which may hold https:// portfolio links) is
    intentionally left out so the page stays free of any external-looking URLs."""
    data = json.dumps({
        "nodes": [{"id": n.id, "type": n.type, "label": n.label} for n in graph.nodes],
        "edges": [{"source": e.source, "target": e.target, "rel": e.rel}
                  for e in graph.edges],
    })
    # Escape HTML/JS-sensitive characters to prevent script breakout via embedded JSON
    data = (
        data
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace(" ", "\\u2028")
        .replace(" ", "\\u2029")
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Portfolio graph</title>"
        "<style>body{font:14px system-ui;margin:0;background:#0b0b0f;color:#e8e8ea}"
        "#c{display:block}#l{position:fixed;top:8px;left:8px;opacity:.7}</style></head>"
        "<body><div id='l'>Portfolio knowledge graph</div>"
        "<canvas id='c'></canvas><script>const G=" + data + ";"
        "const cv=document.getElementById('c'),x=cv.getContext('2d');"
        "cv.width=innerWidth;cv.height=innerHeight;"
        "const N=G.nodes.map((n,i)=>({...n,"
        "px:innerWidth/2+Math.cos(i)*Math.min(innerWidth,innerHeight)*0.35,"
        "py:innerHeight/2+Math.sin(i)*Math.min(innerWidth,innerHeight)*0.35}));"
        "const idx=Object.fromEntries(N.map(n=>[n.id,n]));"
        "x.strokeStyle='#334';G.edges.forEach(e=>{const a=idx[e.source],b=idx[e.target];"
        "if(a&&b){x.beginPath();x.moveTo(a.px,a.py);x.lineTo(b.px,b.py);x.stroke();}});"
        "N.forEach(n=>{x.fillStyle=n.type==='project'?'#7c9cff':'#3a3a44';"
        "x.beginPath();x.arc(n.px,n.py,n.type==='project'?8:4,0,7);x.fill();"
        "x.fillStyle='#e8e8ea';x.fillText(n.label,n.px+8,n.py+3);});"
        "</script></body></html>"
    )


def rebuild(creds, sid: str, cfg: Config, llm, client, now: datetime) -> list[str]:
    """Crawl portfolio -> extract -> graph -> store. Never raises."""
    notes: list[str] = []
    base = cfg.profile.portfolio
    if not base:
        return ["portfolio graph: no portfolio URL configured"]
    try:
        urls = discover_urls(base, client)
        pages = fetch_pages(urls, client)
        extracts = [extract_page(u, t, llm) for u, t in pages]
        graph = build_graph(extracts, [u for u, _ in pages],
                            now.strftime("%Y-%m-%d %H:%M"))
        sheets.write_portfolio_graph(creds, sid, graph.model_dump_json(),
                                     now.strftime("%Y-%m-%d %H:%M"))
        n_proj = sum(1 for x in graph.nodes if x.type == "project")
        notes.append(f"portfolio graph: {len(pages)} pages, {n_proj} projects")
        try:
            from jobpilot import tailor
            drive = tailor._drive(creds)
            folder = tailor._ensure_folder(drive, "JobPilot Applications")
            tailor.upload_bytes(creds, folder, "_portfolio_graph.html",
                                render_html(graph).encode("utf-8"), "text/html")
        except Exception as exc:  # noqa: BLE001 — optional viewer, never fails the run
            notes.append(f"portfolio graph html: skipped ({type(exc).__name__})")
    except Exception as exc:  # noqa: BLE001 — degrade to a note
        notes.append(f"portfolio graph: FAILED ({type(exc).__name__}: {exc})")
    return notes
