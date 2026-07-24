"""Portfolio knowledge graph: crawl the portfolio, extract per-project facts with
Gemini, assemble a nodes+edges graph, store it, and render it into the Knowledge pack.

Grounds the Assistant chat and the auto-apply answer engine in real project facts and
links. Spec: docs/superpowers/specs/2026-07-24-auto-apply-design.md
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

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
