from __future__ import annotations

import jobpilot.portfolio_graph as pg


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
