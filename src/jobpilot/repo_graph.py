"""Repo knowledge graph: assemble GitHub contribution facts into a nodes+edges
graph, mirroring the shape of portfolio_graph.PortfolioGraph but for repos.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

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
