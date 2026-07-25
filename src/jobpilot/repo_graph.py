"""Repo knowledge graph: assemble GitHub contribution facts into a nodes+edges
graph, mirroring the shape of portfolio_graph.PortfolioGraph but for repos.
"""

from __future__ import annotations

import json
import os
from datetime import datetime

from pydantic import BaseModel, Field

from jobpilot import github_repos, sheets
from jobpilot.config import Config
from jobpilot.github_repos import RepoFacts
from jobpilot.portfolio_graph import _slug


class RepoGraphNode(BaseModel):
    id: str
    type: str
    label: str
    data: dict = Field(default_factory=dict)


class RepoGraphEdge(BaseModel):
    source: str
    target: str
    rel: str


class RepoGraph(BaseModel):
    nodes: list[RepoGraphNode] = Field(default_factory=list)
    edges: list[RepoGraphEdge] = Field(default_factory=list)
    built_at: str = ""
    source: str = "github"


def build_repo_graph(repos: list[RepoFacts], now_str: str) -> RepoGraph:
    """Merge per-repo facts into a deduped nodes+edges graph."""
    nodes: dict[str, RepoGraphNode] = {}
    edges: list[RepoGraphEdge] = []

    def node(ntype: str, prefix: str, label: str, data: dict | None = None) -> str | None:
        slug = _slug(label)
        if not slug:
            return None
        nid = f"{prefix}:{slug}"
        if nid not in nodes:
            nodes[nid] = RepoGraphNode(id=nid, type=ntype, label=label, data=data or {})
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

    def edge(src: str | None, dst: str | None, rel: str) -> None:
        if not src or not dst:
            return
        if not any(e.source == src and e.target == dst and e.rel == rel for e in edges):
            edges.append(RepoGraphEdge(source=src, target=dst, rel=rel))

    for r in repos:
        label = f"{r.owner}/{r.name}"
        rid = node("repo", "repo", label, {
            "description": r.description,
            "stars": r.stars,
            "url": r.url,
            "languages": r.languages,
            "primary_language": r.primary_language,
            "commits": r.contribution_commits,
            "private": r.is_private,
        })
        if rid is None:
            continue

        all_langs = ([r.primary_language] if r.primary_language else []) + r.languages
        seen_langs: list[str] = []
        for lang in all_langs:
            if lang in seen_langs:
                continue
            seen_langs.append(lang)
            lid = node("language", "language", lang)
            edge(rid, lid, "uses-language")

        if r.is_org and r.owner:
            oid = node("org", "org", r.owner)
            edge(rid, oid, "owned-by-org")

        for topic in r.topics:
            tid = node("topic", "topic", topic)
            edge(rid, tid, "tagged")

    return RepoGraph(nodes=list(nodes.values()), edges=edges, built_at=now_str)


def _cap_graph_json(graph: RepoGraph, limit: int = 45000) -> tuple[str, int]:
    """Serialize the graph; if the result exceeds `limit` chars, drop whole
    repo nodes (and their incident edges + any nodes left with no edges) from
    the end until it fits. Always returns valid, parseable JSON — never a
    mid-string slice. Returns (json_str, dropped_repo_count)."""
    dropped = 0
    nodes = list(graph.nodes)
    edges = list(graph.edges)
    while True:
        g = RepoGraph(nodes=nodes, edges=edges, built_at=graph.built_at,
                      source=graph.source)
        js = g.model_dump_json()
        if len(js) <= limit or not any(n.type == "repo" for n in nodes):
            return js, dropped
        # drop the last repo node + its incident edges + now-orphaned nodes
        last_repo = next(n for n in reversed(nodes) if n.type == "repo")
        nodes = [n for n in nodes if n.id != last_repo.id]
        edges = [e for e in edges if e.source != last_repo.id and e.target != last_repo.id]
        referenced = {e.source for e in edges} | {e.target for e in edges}
        nodes = [n for n in nodes if n.type == "repo" or n.id in referenced]
        dropped += 1


def render_repo_pack(graph: RepoGraph) -> str:
    """Flatten the graph into per-repo Knowledge-pack text."""
    node_by_id = {n.id: n for n in graph.nodes}
    out: list[str] = []
    for n in graph.nodes:
        if n.type != "repo":
            continue
        d = n.data
        parts = [f"## {n.label}"]
        if d.get("description"):
            parts.append(d["description"])
        langs = d.get("languages") or []
        if langs:
            parts.append("Languages: " + ", ".join(langs))
        topics = [
            node_by_id[e.target].label for e in graph.edges
            if e.source == n.id and e.rel == "tagged" and e.target in node_by_id
        ]
        if topics:
            parts.append("Topics: " + ", ".join(topics))
        if d.get("commits"):
            parts.append(f"Commits: {d['commits']}")
        if d.get("url"):
            parts.append(f"URL: {d['url']}")
        if d.get("private"):
            parts.append("Private")
        out.append("\n".join(parts))
    return "\n\n".join(out)


def render_repo_html(graph: RepoGraph) -> str:
    """Self-contained HTML map: embedded data, inline canvas layout, no external
    assets. Only id/type/label (nodes) and source/target/rel (edges) are embedded
    — the full node `data` blob (which may hold https:// repo URLs) is
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
        .replace(" ", "\\u2028")
        .replace(" ", "\\u2029")
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Repo graph</title>"
        "<style>body{font:14px system-ui;margin:0;background:#0b0b0f;color:#e8e8ea}"
        "#c{display:block}#l{position:fixed;top:8px;left:8px;opacity:.7}</style></head>"
        "<body><div id='l'>Repo knowledge graph</div>"
        "<canvas id='c'></canvas><script>const G=" + data + ";"
        "const cv=document.getElementById('c'),x=cv.getContext('2d');"
        "cv.width=innerWidth;cv.height=innerHeight;"
        "const N=G.nodes.map((n,i)=>({...n,"
        "px:innerWidth/2+Math.cos(i)*Math.min(innerWidth,innerHeight)*0.35,"
        "py:innerHeight/2+Math.sin(i)*Math.min(innerWidth,innerHeight)*0.35}));"
        "const idx=Object.fromEntries(N.map(n=>[n.id,n]));"
        "x.strokeStyle='#334';G.edges.forEach(e=>{const a=idx[e.source],b=idx[e.target];"
        "if(a&&b){x.beginPath();x.moveTo(a.px,a.py);x.lineTo(b.px,b.py);x.stroke();}});"
        "N.forEach(n=>{x.fillStyle=n.type==='repo'?'#7cffb0':'#3a3a44';"
        "x.beginPath();x.arc(n.px,n.py,n.type==='repo'?8:4,0,7);x.fill();"
        "x.fillStyle='#e8e8ea';x.fillText(n.label,n.px+8,n.py+3);});"
        "</script></body></html>"
    )


def rebuild(creds, sid: str, cfg: Config, client, now: datetime) -> list[str]:
    """Fetch contributed repos -> graph -> store. Never raises."""
    token = os.environ.get("JOBPILOT_GITHUB_TOKEN", "")
    if not token:
        return ["repo graph: no JOBPILOT_GITHUB_TOKEN, skipped"]
    try:
        repos = github_repos.fetch_contributed_repos(token, client)
        if not repos:
            # An empty fetch is almost always a transient token/rate-limit issue,
            # not "the account really has zero repos now" — don't let it clobber
            # a previously-good stored graph.
            return ["repo graph: 0 repos fetched, keeping previous graph"]
        graph = build_repo_graph(repos, now.strftime("%Y-%m-%d %H:%M"))
        n_orgs = sum(1 for n in graph.nodes if n.type == "org")
        capped_json, dropped = _cap_graph_json(graph)
        sheets.write_repo_graph(creds, sid, capped_json,
                                now.strftime("%Y-%m-%d %H:%M"))
        note = f"repo graph: {len(repos)} repos, {n_orgs} orgs"
        if dropped:
            note += f" ({dropped} repos omitted for size cap)"
        notes = [note]
        try:
            from jobpilot import tailor
            drive = tailor._drive(creds)
            folder = tailor._ensure_folder(drive, "JobPilot Applications")
            tailor.upload_bytes(creds, folder, "_repo_graph.html",
                                render_repo_html(graph).encode("utf-8"), "text/html")
        except Exception as exc:  # noqa: BLE001 — optional viewer, never fails the run
            notes.append(f"repo graph html: skipped ({type(exc).__name__})")
        return notes
    except Exception as exc:  # noqa: BLE001 — degrade to a note
        return [f"repo graph: FAILED ({type(exc).__name__}: {exc})"]
