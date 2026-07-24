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
