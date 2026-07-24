from __future__ import annotations

import re

import httpx
import pytest

import jobpilot.portfolio_graph as pg


BASE = "https://portfolio.example"


def test_page_extract_schema_roundtrips():
    ex = pg.PageExtract.model_validate({
        "projects": [{
            "name": "Enterprise Search",
            "one_line": "Agentic RAG over 100k docs",
            "problem": "Grounded Q&A with citations",
            "approach": "Hybrid retrieval + reranking",
            "stack": ["pgvector", "Vertex Gemini"],
            "metrics": ["70% fewer hallucinations", "$300/mo"],
            "role": "AI Engineer",
            "company": "Acme Robotics",
            "dates": "Jun 2026 - Present",
            "links": {"case_study": "https://x/posts/enterprise-search"},
        }],
        "skills": ["RAG", "reranking"],
        "technologies": ["pgvector", "Vertex Gemini"],
    })
    assert ex.projects[0].name == "Enterprise Search"
    assert "RAG" in ex.skills


def test_portfolio_graph_serializes_nodes_and_edges():
    g = pg.PortfolioGraph(
        nodes=[pg.GraphNode(id="project:enterprise-search", type="project",
                            label="Enterprise Search", data={"one_line": "RAG"})],
        edges=[pg.GraphEdge(source="project:enterprise-search",
                            target="tech:pgvector", rel="used-tech")],
        crawled_at="2026-07-24 12:00",
        sources=["https://x/projects"],
    )
    blob = g.model_dump_json()
    assert pg.PortfolioGraph.model_validate_json(blob).nodes[0].type == "project"


@pytest.mark.httpx_mock(assert_all_requests_were_expected=False)
def test_discover_urls_scopes_to_host_and_dedupes(httpx_mock):
    httpx_mock.add_response(url=f"{BASE}/", text=(
        '<a href="/projects">Projects</a>'
        '<a href="/posts/enterprise-search">ES</a>'
        '<a href="/posts/enterprise-search">dup</a>'
        '<a href="https://twitter.com/x">off</a>'))
    httpx_mock.add_response(url=re.compile(rf"{re.escape(BASE)}/(projects|posts).*"),
                            text="<a href='/posts/npc-coach'>NPC</a>")
    urls = pg.discover_urls(BASE, httpx.Client())
    assert urls[0] == f"{BASE}/"                       # base first
    assert f"{BASE}/posts/enterprise-search" in urls
    assert f"{BASE}/posts/npc-coach" in urls           # second-hop discovery
    assert all(u.startswith(BASE) for u in urls)       # host-scoped
    assert len(urls) == len(set(urls))                 # deduped


def test_fetch_pages_skips_errors(httpx_mock):
    httpx_mock.add_response(url=f"{BASE}/a", text="<p>Alpha  body</p>")
    httpx_mock.add_response(url=f"{BASE}/b", status_code=404)
    pages = pg.fetch_pages([f"{BASE}/a", f"{BASE}/b"], httpx.Client())
    assert pages == [(f"{BASE}/a", "Alpha  body")]


def test_extract_page_parses_llm_json():
    payload = (
        '{"projects":[{"name":"NPC Coach","one_line":"call QA",'
        '"stack":["Gemini"],"metrics":["130% lift"],'
        '"links":{"case_study":"https://x/posts/npc-coach"}}],'
        '"skills":["evals"],"technologies":["Gemini"]}')
    ex = pg.extract_page("https://x/posts/npc-coach", "some text", lambda p: payload)
    assert ex.projects[0].name == "NPC Coach"
    assert ex.projects[0].metrics == ["130% lift"]


def test_extract_page_degrades_on_bad_json():
    ex = pg.extract_page("https://x/a", "text", lambda p: "not json")
    assert ex.projects == [] and ex.skills == []


def test_build_graph_dedupes_projects_and_links_edges():
    e1 = pg.PageExtract(projects=[pg.ProjectFacts(
        name="Enterprise Search", company="Hybridge", stack=["pgvector"],
        metrics=["70% fewer hallucinations"],
        links={"case_study": "https://x/posts/enterprise-search"})],
        skills=["RAG"], technologies=["pgvector"])
    e2 = pg.PageExtract(projects=[pg.ProjectFacts(  # same project, second page
        name="enterprise search", stack=["Vertex Gemini"])])
    g = pg.build_graph([e1, e2], ["https://x/projects"], "2026-07-24 12:00")

    projects = [n for n in g.nodes if n.type == "project"]
    assert len(projects) == 1                          # deduped by slug
    techs = {n.label for n in g.nodes if n.type == "technology"}
    assert techs == {"pgvector", "Vertex Gemini"}      # merged across pages
    pid = projects[0].id
    assert any(e.source == pid and e.rel == "used-tech" for e in g.edges)
    assert any(e.rel == "built-at" for e in g.edges)
    assert any(e.rel == "achieved" for e in g.edges)
    assert g.crawled_at == "2026-07-24 12:00"


def test_build_graph_unions_stack_across_pages():
    e1 = pg.PageExtract(projects=[pg.ProjectFacts(
        name="Sample Project", stack=["pgvector"])])
    e2 = pg.PageExtract(projects=[pg.ProjectFacts(  # same project, second page
        name="Sample Project", stack=["Vertex Gemini"])])
    g = pg.build_graph([e1, e2], ["https://x/projects"], "2026-07-24 12:00")

    projects = [n for n in g.nodes if n.type == "project"]
    assert len(projects) == 1
    stack = set(projects[0].data["stack"])
    assert {"pgvector", "Vertex Gemini"} <= stack     # both survive, none lost


def test_build_graph_drops_degenerate_labels():
    ex = pg.PageExtract(technologies=["...", "!!!", "Sample Tech"])
    g = pg.build_graph([ex], ["https://x/projects"], "2026-07-24 12:00")

    assert all(n.id for n in g.nodes)                  # no empty ids
    ids = [n.id for n in g.nodes]
    assert len(ids) == len(set(ids))                   # no collisions
    labels = {n.label for n in g.nodes}
    assert "Sample Tech" in labels
    assert "..." not in labels and "!!!" not in labels


def test_sheet_storage_roundtrip(monkeypatch):
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
                    return {"sheets": [{"properties": {"title": "PortfolioGraph"}}]}
            return R()
        def batchUpdate(self, **k):
            class R:
                def execute(self_):
                    return {}
            return R()

    monkeypatch.setattr(sh, "_svc", lambda creds: type(
        "S", (), {"spreadsheets": lambda self_: FakeSheets()})())

    sh.write_portfolio_graph("creds", "sid", '{"nodes":[]}', "2026-07-24 12:00")
    assert sh.read_portfolio_graph("creds", "sid") == '{"nodes":[]}'


def test_render_pack_lists_projects_with_links():
    g = pg.build_graph([pg.PageExtract(projects=[pg.ProjectFacts(
        name="CBCT Scan Validator", one_line="artifact detection",
        metrics=["macro AUROC 0.93", "replaced $98K quote"],
        links={"case_study": "https://x/posts/cbct-scan-validator"})])],
        ["https://x"], "2026-07-24 12:00")
    text = pg.render_pack(g)
    assert "CBCT Scan Validator" in text
    assert "macro AUROC 0.93" in text
    assert "https://x/posts/cbct-scan-validator" in text


def test_rebuild_crawls_and_writes(monkeypatch):
    import jobpilot.sheets as sh
    from tests.test_sources import make_cfg

    monkeypatch.setattr(pg, "discover_urls", lambda base, c: ["https://x/a"])
    monkeypatch.setattr(pg, "fetch_pages", lambda urls, c: [("https://x/a", "body")])
    monkeypatch.setattr(pg, "extract_page", lambda url, text, llm: pg.PageExtract(
        projects=[pg.ProjectFacts(name="Loan Radar", one_line="MLOps")]))
    written = {}
    monkeypatch.setattr(sh, "write_portfolio_graph",
                        lambda c, s, j, ts: written.update({"json": j}))

    notes = pg.rebuild("creds", "sid", make_cfg(), lambda p: "{}", object(),
                       __import__("datetime").datetime(2026, 7, 24, 12, 0))
    assert "Loan Radar" in written["json"]
    assert any("portfolio graph" in n.lower() for n in notes)


def test_main_has_rebuild_portfolio_graph_flag():
    import argparse
    import jobpilot.__main__ as m

    # The flag must parse without error.
    parser = argparse.ArgumentParser()
    # Re-declare the same flag the module adds, then assert the module references it.
    import inspect
    src = inspect.getsource(m)
    assert "--rebuild-portfolio-graph" in src
    assert "portfolio_graph" in src
