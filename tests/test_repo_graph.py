from __future__ import annotations

from datetime import datetime

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


def test_repo_sheet_storage_roundtrip(monkeypatch):
    import jobpilot.sheets as sh

    store = {"rows": []}

    class FakeValues:
        def get(self, **k):
            class R:
                def execute(self_):
                    return {"values": store["rows"]}
            return R()
        def update(self, **k):
            store["rows"] = k["body"]["values"]
            class R:
                def execute(self_):
                    return {}
            return R()
        def clear(self, **k):
            class R:
                def execute(self_):
                    return {}
            return R()

    class FakeSheets:
        def values(self):
            return FakeValues()
        def get(self, **k):
            class R:
                def execute(self_):
                    return {"sheets": [{"properties": {"title": "RepoGraph"}}]}
            return R()
        def batchUpdate(self, **k):
            class R:
                def execute(self_):
                    return {}
            return R()

    monkeypatch.setattr(sh, "_svc", lambda creds: type(
        "S", (), {"spreadsheets": lambda self_: FakeSheets()})())

    sh.write_repo_graph("creds", "sid", '{"nodes":[]}', "2026-07-24 12:00")
    assert sh.read_repo_graph("creds", "sid") == '{"nodes":[]}'


def test_render_repo_pack_lists_repo_with_url_and_languages():
    g = rg.build_repo_graph([_org_repo()], "2026-07-24 12:00")
    text = rg.render_repo_pack(g)
    assert "## acme-org/widget-lib" in text
    assert "Widgets for acme" in text
    assert "Languages: Python, Go" in text
    assert "Topics: widgets" in text
    assert "Commits: 12" in text
    assert "https://github.com/acme-org/widget-lib" in text
    assert "Private" in text


def test_render_repo_pack_skips_empty_fields():
    g = rg.build_repo_graph([_own_repo()], "2026-07-24 12:00")
    text = rg.render_repo_pack(g)
    assert "## sampreeth/my-tool" in text
    assert "Topics:" not in text  # own repo has no topics
    assert "Private" not in text  # own repo is not private


def test_rebuild_no_token_skips_write(monkeypatch):
    import jobpilot.sheets as sh

    monkeypatch.delenv("JOBPILOT_GITHUB_TOKEN", raising=False)
    write_calls = []
    monkeypatch.setattr(sh, "write_repo_graph", lambda c, s, j, ts: write_calls.append(j))

    notes = rg.rebuild("creds", "sid", object(), object(), datetime(2026, 7, 24, 12, 0))
    assert write_calls == []
    assert any("no JOBPILOT_GITHUB_TOKEN" in n for n in notes)


def test_rebuild_writes_and_notes_with_token(monkeypatch):
    import jobpilot.sheets as sh
    from jobpilot import github_repos

    monkeypatch.setenv("JOBPILOT_GITHUB_TOKEN", "tok")
    monkeypatch.setattr(github_repos, "fetch_contributed_repos",
                        lambda token, client: [_org_repo()])
    written = {}
    monkeypatch.setattr(sh, "write_repo_graph",
                        lambda c, s, j, ts: written.update({"json": j}))

    notes = rg.rebuild("creds", "sid", object(), object(), datetime(2026, 7, 24, 12, 0))
    assert "widget-lib" in written["json"]
    assert any("1 repos" in n for n in notes)


def test_rebuild_keeps_previous_graph_on_empty_fetch(monkeypatch):
    import jobpilot.sheets as sh
    from jobpilot import github_repos

    monkeypatch.setenv("JOBPILOT_GITHUB_TOKEN", "tok")
    monkeypatch.setattr(github_repos, "fetch_contributed_repos",
                        lambda token, client: [])
    write_calls = []
    monkeypatch.setattr(sh, "write_repo_graph", lambda c, s, j, ts: write_calls.append(j))

    notes = rg.rebuild("creds", "sid", object(), object(), datetime(2026, 7, 24, 12, 0))
    assert write_calls == []
    assert any("keeping previous graph" in n.lower() for n in notes)


def test_render_repo_html_is_self_contained():
    g = rg.build_repo_graph([_org_repo()], "2026-07-24 12:00")
    html = rg.render_repo_html(g)
    assert "<html" in html.lower()
    assert "widget-lib" in html
    assert "http://" not in html and "https://cdn" not in html  # no external assets


def test_render_repo_html_escapes_script_breakout():
    repo = RepoFacts(name="Evil</script><script>alert(1)</script>", owner="acme-org")
    g = rg.build_repo_graph([repo], "2026-07-24 12:00")
    html = rg.render_repo_html(g)
    assert "</script><script>" not in html, "Script breakout payload not escaped"
    assert html.count("</script>") == 1, "Should have exactly one legitimate closing script tag"
    assert "<html" in html.lower(), "HTML structure should be preserved"


def test_rebuild_uploads_repo_graph_html(monkeypatch):
    import jobpilot.sheets as sh
    from jobpilot import github_repos, tailor

    monkeypatch.setenv("JOBPILOT_GITHUB_TOKEN", "tok")
    monkeypatch.setattr(github_repos, "fetch_contributed_repos",
                        lambda token, client: [_org_repo()])
    monkeypatch.setattr(sh, "write_repo_graph", lambda c, s, j, ts: None)

    uploaded = {}
    monkeypatch.setattr(tailor, "_drive", lambda creds: "drive")
    monkeypatch.setattr(tailor, "_ensure_folder", lambda drive, name: "folder-id")
    monkeypatch.setattr(tailor, "upload_bytes", lambda creds, folder, filename, blob, mime:
                        uploaded.update({"filename": filename, "blob": blob, "mime": mime}))

    rg.rebuild("creds", "sid", object(), object(), datetime(2026, 7, 24, 12, 0))
    assert uploaded["filename"] == "_repo_graph.html"
    assert uploaded["mime"] == "text/html"
    assert b"<html" in uploaded["blob"].lower()


def test_rebuild_upload_failure_is_swallowed(monkeypatch):
    import jobpilot.sheets as sh
    from jobpilot import github_repos, tailor

    monkeypatch.setenv("JOBPILOT_GITHUB_TOKEN", "tok")
    monkeypatch.setattr(github_repos, "fetch_contributed_repos",
                        lambda token, client: [_org_repo()])
    monkeypatch.setattr(sh, "write_repo_graph", lambda c, s, j, ts: None)
    monkeypatch.setattr(tailor, "_drive", lambda creds: (_ for _ in ()).throw(RuntimeError("boom")))

    notes = rg.rebuild("creds", "sid", object(), object(), datetime(2026, 7, 24, 12, 0))
    assert any("1 repos" in n for n in notes)  # main rebuild note still present
    assert any("skipped" in n.lower() for n in notes)  # upload failure noted, not raised


def test_main_has_rebuild_repo_graph_flag():
    import inspect

    import jobpilot.__main__ as m

    src = inspect.getsource(m)
    assert "--rebuild-repo-graph" in src
    assert "repo_graph" in src
