from __future__ import annotations

import jobpilot.repo_graph as rg
from jobpilot.github_repos import RepoFacts


def _org_repo() -> RepoFacts:
    return RepoFacts(
        name="widget-lib",
        owner="acme-org",
        is_org=True,
        is_private=True,
        description="Widgets for acme",
        primary_language="Python",
        languages=["Python", "Go"],
        topics=["widgets"],
        stars=5,
        url="https://github.com/acme-org/widget-lib",
        contribution_commits=12,
    )


def _own_repo() -> RepoFacts:
    return RepoFacts(
        name="my-tool",
        owner="sampreeth",
        is_org=False,
        is_private=False,
        description="A personal tool",
        primary_language="Rust",
        languages=["Rust"],
        topics=[],
        stars=1,
        url="https://github.com/sampreeth/my-tool",
        contribution_commits=3,
    )


def test_build_repo_graph_creates_repo_org_language_topic_nodes():
    g = rg.build_repo_graph([_org_repo(), _own_repo()], "2026-07-24 12:00")

    repo_nodes = [n for n in g.nodes if n.type == "repo"]
    assert len(repo_nodes) == 2
    labels = {n.label for n in repo_nodes}
    assert labels == {"acme-org/widget-lib", "sampreeth/my-tool"}

    org_nodes = [n for n in g.nodes if n.type == "org"]
    assert len(org_nodes) == 1
    assert org_nodes[0].label == "acme-org"

    owned_by_org_edges = [e for e in g.edges if e.rel == "owned-by-org"]
    assert len(owned_by_org_edges) == 1
    org_repo_id = next(n.id for n in repo_nodes if n.label == "acme-org/widget-lib")
    assert owned_by_org_edges[0].source == org_repo_id
    assert owned_by_org_edges[0].target == org_nodes[0].id

    lang_labels = {n.label for n in g.nodes if n.type == "language"}
    assert lang_labels == {"Python", "Go", "Rust"}

    uses_lang_edges = [e for e in g.edges if e.rel == "uses-language"]
    assert len(uses_lang_edges) == 3  # Python, Go (org repo) + Rust (own repo)

    tagged_edges = [e for e in g.edges if e.rel == "tagged"]
    assert len(tagged_edges) == 1
    topic_node = next(n for n in g.nodes if n.type == "topic")
    assert topic_node.label == "widgets"
    assert tagged_edges[0].target == topic_node.id

    assert all(n.id for n in g.nodes)  # no empty ids
    assert g.built_at == "2026-07-24 12:00"
    assert g.source == "github"


def test_build_repo_graph_dedupes_repo_and_unions_languages_topics():
    r1 = RepoFacts(name="widget-lib", owner="acme-org", is_org=True,
                   languages=["Python"], topics=["widgets"])
    r2 = RepoFacts(name="widget-lib", owner="acme-org", is_org=True,
                   languages=["Go"], topics=["infra"])
    g = rg.build_repo_graph([r1, r2], "2026-07-24 12:00")

    repo_nodes = [n for n in g.nodes if n.type == "repo"]
    assert len(repo_nodes) == 1
    assert set(repo_nodes[0].data.get("languages", [])) >= {"Python", "Go"}

    lang_labels = {n.label for n in g.nodes if n.type == "language"}
    assert lang_labels == {"Python", "Go"}

    topic_labels = {n.label for n in g.nodes if n.type == "topic"}
    assert topic_labels == {"widgets", "infra"}

    # no duplicate edges
    uses_lang_edges = [(e.source, e.target) for e in g.edges if e.rel == "uses-language"]
    assert len(uses_lang_edges) == len(set(uses_lang_edges))


def test_build_repo_graph_no_org_node_or_edge_for_own_repo():
    g = rg.build_repo_graph([_own_repo()], "2026-07-24 12:00")
    assert not any(n.type == "org" for n in g.nodes)
    assert not any(e.rel == "owned-by-org" for e in g.edges)


def test_build_repo_graph_drops_punctuation_only_language_label():
    repo = RepoFacts(name="widget-lib", owner="acme-org",
                     primary_language="...", languages=["...", "Python"])
    g = rg.build_repo_graph([repo], "2026-07-24 12:00")

    assert all(n.id for n in g.nodes)  # no empty-id nodes
    lang_labels = {n.label for n in g.nodes if n.type == "language"}
    assert lang_labels == {"Python"}
    assert "..." not in lang_labels
