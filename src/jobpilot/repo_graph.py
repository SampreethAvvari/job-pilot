"""Repo knowledge graph: assemble GitHub contribution facts into a nodes+edges
graph, mirroring the shape of portfolio_graph.PortfolioGraph but for repos.
"""

from __future__ import annotations

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
        sheets.write_repo_graph(creds, sid, graph.model_dump_json(),
                                now.strftime("%Y-%m-%d %H:%M"))
        return [f"repo graph: {len(repos)} repos, {n_orgs} orgs"]
    except Exception as exc:  # noqa: BLE001 — degrade to a note
        return [f"repo graph: FAILED ({type(exc).__name__}: {exc})"]
