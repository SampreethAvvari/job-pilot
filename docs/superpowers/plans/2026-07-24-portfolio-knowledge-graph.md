# Portfolio Knowledge Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Crawl the user's portfolio, extract a project knowledge graph with an LLM, store it, and flatten it into the existing Knowledge pack so the Assistant (and the upcoming auto-apply answer engine) ground answers in real project facts and links.

**Architecture:** A new `portfolio_graph.py` module discovers and fetches every portfolio page over HTTP (reusing the polite httpx + strip_html helpers), sends each page to Gemini under a JSON-schema contract to extract per-project facts, assembles those into a nodes+edges graph stored as JSON in a new `PortfolioGraph` Sheet tab, and rewrites `knowledge.portfolio_section` to render that graph into rich pack text. A CLI flag `--rebuild-portfolio-graph` and a console button trigger a background rebuild; the daily full run refreshes it automatically.

**Tech Stack:** Python 3.12, pydantic v2, httpx (+ pytest-httpx for tests), google-genai (Vertex Gemini), google-api-python-client (Sheets/Drive), Next.js App Router + google-auth-library (UI trigger).

This is Plan 1 of the auto-apply feature (spec: `docs/superpowers/specs/2026-07-24-auto-apply-design.md`). It ships working software on its own: a richer, graph-grounded Knowledge pack plus a rebuild button. Plans 2-6 (application profile + answer engine + Applications UI, easy ATS adapters, Workday, local fallback, full-auto unlock) follow separately.

## Global Constraints

- Python target 3.12; `from __future__ import annotations` at the top of every new module (matches the codebase).
- Lint: ruff pinned to `select=["E4","E7","E9","F"]`; keep imports clean, no unused.
- Never raise out of a refresh/rebuild path — one dead page or LLM failure must degrade to a note, never crash the run (matches `knowledge.refresh`).
- Personal data stays out of the public repo: the graph is built at runtime from the live portfolio, never committed. No fixtures containing the user's real content in tracked tests — use the Jane Doe style placeholder content already used in `tests/`.
- LLM access only via `jobpilot.scorer.make_gemini_llm(cfg, schema=...)`. No new client code.
- Gemini extraction may not invent facts/metrics/links not present on the page (prompt rule + schema).
- Sheet is the store: follow the `ensure_*_tab` / values API patterns in `sheets.py`. A single Sheet cell caps at 50000 chars — keep the graph JSON under 45000 (same guard as `write_knowledge`).
- Commit after every task with a `feat:`/`test:`/`refactor:` message. Author commits as SampreethAvvari <spa9659@nyu.edu> (repo convention, no Claude co-author trailer).

---

### Task 1: Graph data models

**Files:**
- Create: `src/jobpilot/portfolio_graph.py`
- Test: `tests/test_portfolio_graph.py`

**Interfaces:**
- Produces: `ProjectFacts`, `PageExtract`, `GraphNode`, `GraphEdge`, `PortfolioGraph` (pydantic models). `PageExtract` is the per-page LLM output schema. `PortfolioGraph` is the stored artifact.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_portfolio_graph.py
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
            "company": "Hybridge",
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd job-pilot && python -m pytest tests/test_portfolio_graph.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'jobpilot.portfolio_graph'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/jobpilot/portfolio_graph.py
"""Portfolio knowledge graph: crawl the portfolio, extract per-project facts with
Gemini, assemble a nodes+edges graph, store it, and render it into the Knowledge pack.

Grounds the Assistant chat and the auto-apply answer engine in real project facts and
links. Spec: docs/superpowers/specs/2026-07-24-auto-apply-design.md
"""

from __future__ import annotations

from typing import Literal

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
    data: dict = Field(default_factory=dict)


class GraphEdge(BaseModel):
    source: str
    target: str
    rel: EdgeRel


class PortfolioGraph(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    crawled_at: str = ""
    sources: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd job-pilot && python -m pytest tests/test_portfolio_graph.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/jobpilot/portfolio_graph.py tests/test_portfolio_graph.py
git commit -m "feat: portfolio graph data models"
```

---

### Task 2: Page discovery and fetch

**Files:**
- Modify: `src/jobpilot/portfolio_graph.py`
- Test: `tests/test_portfolio_graph.py`

**Interfaces:**
- Consumes: `jobpilot.sources.common.strip_html`; `httpx.Client`.
- Produces: `discover_urls(base: str, client) -> list[str]` (seed pages + same-host links, deduped, base first); `fetch_pages(urls, client) -> list[tuple[str, str]]` (list of `(url, stripped_text)`, skipping pages that error).

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_portfolio_graph.py
import re

import httpx


BASE = "https://portfolio.example"


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd job-pilot && python -m pytest tests/test_portfolio_graph.py -q`
Expected: FAIL with `AttributeError: module 'jobpilot.portfolio_graph' has no attribute 'discover_urls'`

- [ ] **Step 3: Write minimal implementation**

```python
# add imports at top of src/jobpilot/portfolio_graph.py
import re
from urllib.parse import urljoin, urlparse

import httpx

from jobpilot.sources.common import strip_html

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
        u = u.split("#")[0].rstrip("/")
        if u and u not in seen and _same_host(u, base):
            seen.append(u)
            order.append(u)

    add(base)  # normalized: base + "/" collapses to base after rstrip inside add()
    for seed in seeds:
        try:
            resp = client.get(seed)
            resp.raise_for_status()
        except httpx.HTTPError:
            continue
        add(seed)
        for href in _HREF_RE.findall(resp.text):
            add(urljoin(seed + "/", href))
    # Base must sort first; keep discovery order otherwise.
    order.sort(key=lambda u: (u != base,))
    return order[:MAX_PAGES]


def fetch_pages(urls: list[str], client: httpx.Client) -> list[tuple[str, str]]:
    """(url, stripped text) for each page that loads; dead pages skipped."""
    out: list[tuple[str, str]] = []
    for url in urls:
        try:
            resp = client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError:
            continue
        text = strip_html(resp.text)[:PAGE_CHARS]
        if text:
            out.append((url, text))
    return out
```

Note: `discover_urls` normalizes `base + "/"` to `base` via `rstrip("/")` inside `add`, so the seed and the "/" entry collapse to one; the sort key `u != base + "/"` still works because after rstrip the base entry equals `base` — change the sort key to `u != base` to match. Use `order.sort(key=lambda u: (u != base,))`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd job-pilot && python -m pytest tests/test_portfolio_graph.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/jobpilot/portfolio_graph.py tests/test_portfolio_graph.py
git commit -m "feat: portfolio page discovery and fetch"
```

---

### Task 3: LLM extraction per page

**Files:**
- Create: `src/jobpilot/prompts/portfolio_extract_v1.txt`
- Modify: `src/jobpilot/portfolio_graph.py`
- Test: `tests/test_portfolio_graph.py`

**Interfaces:**
- Consumes: `jobpilot.scorer.make_gemini_llm` (an `LlmFn = Callable[[str], str]`).
- Produces: `extract_page(url: str, text: str, llm) -> PageExtract` (one retry, degrades to empty `PageExtract` on failure).

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_portfolio_graph.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd job-pilot && python -m pytest tests/test_portfolio_graph.py -q`
Expected: FAIL with `AttributeError: ... has no attribute 'extract_page'`

- [ ] **Step 3: Write minimal implementation**

Create `src/jobpilot/prompts/portfolio_extract_v1.txt`:

```
You are extracting a candidate's project portfolio into structured facts for a
knowledge graph. Read the page below and return JSON matching the schema.

STRICT RULES:
- Only use facts stated on the page. Never invent metrics, dates, companies, or links.
- Copy links (case study, demo, repo) exactly as they appear; do not guess URLs.
- If the page is not about a project (e.g. a nav or contact page), return empty lists.
- Keep each string concise and factual.

PAGE URL: {url}

PAGE CONTENT:
{content}
```

Add to `src/jobpilot/portfolio_graph.py`:

```python
from pathlib import Path

from jobpilot.scorer import LlmFn

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
```

The caller builds the LLM with the right schema: `make_gemini_llm(cfg, schema=PageExtract)` (Task 6 orchestrator wires this).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd job-pilot && python -m pytest tests/test_portfolio_graph.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/jobpilot/portfolio_graph.py src/jobpilot/prompts/portfolio_extract_v1.txt tests/test_portfolio_graph.py
git commit -m "feat: per-page portfolio extraction with schema contract"
```

---

### Task 4: Assemble the graph

**Files:**
- Modify: `src/jobpilot/portfolio_graph.py`
- Test: `tests/test_portfolio_graph.py`

**Interfaces:**
- Consumes: `PageExtract`, graph models from Task 1.
- Produces: `build_graph(extracts: list[PageExtract], sources: list[str], now_str: str) -> PortfolioGraph`. Projects dedupe by slugified name; edges created for stack (`used-tech`), company (`built-at`), metrics (`achieved`), links (`links-to`), skills (`solved-problem` from project to skill). Node id scheme: `project:<slug>`, `tech:<slug>`, `skill:<slug>`, `company:<slug>`, `outcome:<slug>`.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_portfolio_graph.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd job-pilot && python -m pytest tests/test_portfolio_graph.py -q`
Expected: FAIL with `AttributeError: ... has no attribute 'build_graph'`

- [ ] **Step 3: Write minimal implementation**

```python
# add to src/jobpilot/portfolio_graph.py
def _slug(text: str) -> str:
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
            nodes[nid].data.update({k: v for k, v in data.items() if v})
        return nid

    def edge(src: str, dst: str, rel: EdgeRel) -> None:
        if not any(e.source == src and e.target == dst and e.rel == rel for e in edges):
            edges.append(GraphEdge(source=src, target=dst, rel=rel))

    for ex in extracts:
        for p in ex.projects:
            pid = node("project", p.name, {
                "one_line": p.one_line, "problem": p.problem, "approach": p.approach,
                "role": p.role, "dates": p.dates, "links": p.links,
                "metrics": p.metrics, "stack": p.stack})
            for tech in p.stack:
                edge(pid, node("technology", tech), "used-tech")
            if p.company:
                edge(pid, node("company", p.company), "built-at")
            for m in p.metrics:
                edge(pid, node("outcome", m), "achieved")
            for url in p.links.values():
                edge(pid, node("outcome", url, {"url": url}), "links-to")
        for sk in ex.skills:
            node("skill", sk)
        for tech in ex.technologies:
            node("technology", tech)

    return PortfolioGraph(nodes=list(nodes.values()), edges=edges,
                          crawled_at=now_str, sources=sources)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd job-pilot && python -m pytest tests/test_portfolio_graph.py -q`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add src/jobpilot/portfolio_graph.py tests/test_portfolio_graph.py
git commit -m "feat: assemble portfolio graph from page extracts"
```

---

### Task 5: Sheet storage for the graph

**Files:**
- Modify: `src/jobpilot/sheets.py`
- Test: `tests/test_portfolio_graph.py`

**Interfaces:**
- Consumes: existing `_svc`, `ensure_*_tab` patterns in `sheets.py`.
- Produces: `ensure_portfolio_graph_tab(creds, sid)`, `write_portfolio_graph(creds, sid, graph_json: str, now_str: str)`, `read_portfolio_graph(creds, sid) -> str` (JSON string, or `""` if unset). Tab `PortfolioGraph`, headers `["Key", "Updated", "JSON"]`, single row key `graph`.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_portfolio_graph.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd job-pilot && python -m pytest tests/test_portfolio_graph.py::test_sheet_storage_roundtrip -q`
Expected: FAIL with `AttributeError: module 'jobpilot.sheets' has no attribute 'write_portfolio_graph'`

- [ ] **Step 3: Write minimal implementation**

Add to `src/jobpilot/sheets.py` (near the other `ensure_*_tab` helpers):

```python
PORTFOLIO_GRAPH_HEADERS = ["Key", "Updated", "JSON"]


def ensure_portfolio_graph_tab(creds, spreadsheet_id: str) -> None:
    svc = _svc(creds)
    meta = svc.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    titles = [s["properties"]["title"] for s in meta["sheets"]]
    if "PortfolioGraph" in titles:
        return
    svc.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": [{"addSheet": {"properties": {"title": "PortfolioGraph"}}}]},
    ).execute()
    svc.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id, range="PortfolioGraph!A1", valueInputOption="RAW",
        body={"values": [PORTFOLIO_GRAPH_HEADERS]},
    ).execute()


def write_portfolio_graph(creds, spreadsheet_id: str, graph_json: str,
                          now_str: str) -> None:
    ensure_portfolio_graph_tab(creds, spreadsheet_id)
    svc = _svc(creds)
    svc.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id, range="PortfolioGraph!A2", valueInputOption="RAW",
        body={"values": [["graph", now_str, graph_json[:45000]]]},
    ).execute()


def read_portfolio_graph(creds, spreadsheet_id: str) -> str:
    ensure_portfolio_graph_tab(creds, spreadsheet_id)
    resp = (_svc(creds).spreadsheets().values()
            .get(spreadsheetId=spreadsheet_id, range="PortfolioGraph!A2:C2").execute())
    rows = resp.get("values", [])
    return rows[0][2] if rows and len(rows[0]) >= 3 else ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd job-pilot && python -m pytest tests/test_portfolio_graph.py::test_sheet_storage_roundtrip -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/jobpilot/sheets.py tests/test_portfolio_graph.py
git commit -m "feat: PortfolioGraph sheet tab storage"
```

---

### Task 6: Orchestrator — crawl to graph to pack

**Files:**
- Modify: `src/jobpilot/portfolio_graph.py`
- Modify: `src/jobpilot/knowledge.py` (rewrite `portfolio_section`)
- Test: `tests/test_portfolio_graph.py`

**Interfaces:**
- Consumes: `discover_urls`, `fetch_pages`, `extract_page`, `build_graph`; `make_gemini_llm(cfg, schema=PageExtract)`; `sheets.write_portfolio_graph`; `cfg.profile.portfolio`.
- Produces: `rebuild(creds, sid, cfg, llm, client, now) -> list[str]` (notes; never raises) and `render_pack(graph: PortfolioGraph) -> str`. `knowledge.portfolio_section` is rewritten to read the stored graph and call `render_pack`, falling back to the old homepage strip when the graph is empty.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_portfolio_graph.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd job-pilot && python -m pytest tests/test_portfolio_graph.py -q`
Expected: FAIL with `AttributeError: ... has no attribute 'render_pack'`

- [ ] **Step 3: Write minimal implementation**

Add to `src/jobpilot/portfolio_graph.py`:

```python
from datetime import datetime

from jobpilot import sheets
from jobpilot.config import Config


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
    except Exception as exc:  # noqa: BLE001 — degrade to a note
        notes.append(f"portfolio graph: FAILED ({type(exc).__name__}: {exc})")
    return notes
```

Rewrite `portfolio_section` in `src/jobpilot/knowledge.py`:

```python
def portfolio_section(cfg: Config, client: httpx.Client, creds=None,
                      spreadsheet_id: str = "") -> str:
    """Render the stored portfolio graph into pack text; fall back to homepage strip."""
    if creds and spreadsheet_id:
        from jobpilot import portfolio_graph as pgmod

        raw = sheets.read_portfolio_graph(creds, spreadsheet_id)
        if raw:
            try:
                return pgmod.render_pack(pgmod.PortfolioGraph.model_validate_json(raw))
            except Exception:  # noqa: BLE001 — fall through to homepage strip
                pass
    url = cfg.profile.portfolio
    if not url:
        return ""
    try:
        resp = client.get(url)
        resp.raise_for_status()
        return strip_html(resp.text)[:PORTFOLIO_CHARS]
    except httpx.HTTPError:
        return ""
```

Update `knowledge.refresh` to pass `creds`/`spreadsheet_id` into the portfolio builder:

```python
        "portfolio": lambda: portfolio_section(cfg, client, creds, spreadsheet_id),
```

(The `refresh` signature already receives `creds` and `spreadsheet_id`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd job-pilot && python -m pytest tests/test_portfolio_graph.py tests/test_knowledge.py -q`
Expected: PASS. If `test_refresh_degrades_per_section_and_writes` breaks on the new `portfolio_section` signature, confirm the monkeypatch there still overrides `kn.portfolio_section` wholesale (it does) so the extra args are harmless.

- [ ] **Step 5: Commit**

```bash
git add src/jobpilot/portfolio_graph.py src/jobpilot/knowledge.py tests/test_portfolio_graph.py
git commit -m "feat: portfolio graph orchestrator and pack rendering"
```

---

### Task 7: CLI flag and full-run refresh

**Files:**
- Modify: `src/jobpilot/__main__.py`
- Modify: `src/jobpilot/pipeline.py`
- Test: `tests/test_portfolio_graph.py`

**Interfaces:**
- Consumes: `portfolio_graph.rebuild`, `make_gemini_llm(cfg, schema=PageExtract)`, `gauth.credentials`.
- Produces: `--rebuild-portfolio-graph` CLI flag (mirrors `--refresh-knowledge`); a call to `portfolio_graph.rebuild` inside the full pipeline run (not fast mode), before the knowledge refresh so the pack renders the fresh graph.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_portfolio_graph.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd job-pilot && python -m pytest tests/test_portfolio_graph.py::test_main_has_rebuild_portfolio_graph_flag -q`
Expected: FAIL (`--rebuild-portfolio-graph` not in source)

- [ ] **Step 3: Write minimal implementation**

In `src/jobpilot/__main__.py`, add the argument alongside the others:

```python
    parser.add_argument("--rebuild-portfolio-graph", action="store_true",
                        help="crawl the portfolio and rebuild the knowledge graph")
```

And a handler block (place it near the `--refresh-knowledge` block):

```python
    if args.rebuild_portfolio_graph:
        import os
        from datetime import datetime, timezone

        import httpx

        from jobpilot import portfolio_graph
        from jobpilot.gauth import credentials
        from jobpilot.scorer import make_gemini_llm

        creds = credentials()
        sid = os.environ.get("JOBPILOT_SPREADSHEET_ID") or cfg.sheet.spreadsheet_id
        llm = make_gemini_llm(cfg, schema=portfolio_graph.PageExtract)
        client = httpx.Client(timeout=20, follow_redirects=True,
                              headers=portfolio_graph.UA)
        for note in portfolio_graph.rebuild(creds, sid, cfg, llm, client,
                                            datetime.now(timezone.utc)):
            print(note)
        return
```

In `src/jobpilot/pipeline.py`, inside the full run (guard `if not fast:`, where `--refresh-knowledge` equivalent work happens — find where `knowledge.refresh` is called in the full run and add the graph rebuild immediately before it):

```python
    if not fast:
        from jobpilot import portfolio_graph
        from jobpilot.scorer import make_gemini_llm as _mk
        pg_llm = _mk(cfg, schema=portfolio_graph.PageExtract)
        pg_client = httpx.Client(timeout=20, follow_redirects=True,
                                 headers=portfolio_graph.UA)
        notes += portfolio_graph.rebuild(creds, sid, cfg, pg_llm, pg_client, now)
```

Read `pipeline.py` first to match the exact variable names in scope (`creds`, `sid`, `now`, `notes`, and how `knowledge.refresh` is currently invoked in the full run) and slot the call in with those names. If `knowledge.refresh` is not currently called in `run()`, add the graph rebuild in the same place the daily full run does its non-fast finalization.

- [ ] **Step 4: Run tests**

Run: `cd job-pilot && python -m pytest tests/test_portfolio_graph.py tests/test_pipeline.py -q`
Expected: PASS. Also run `python -c "import jobpilot.__main__"` to confirm the module imports cleanly.

- [ ] **Step 5: Commit**

```bash
git add src/jobpilot/__main__.py src/jobpilot/pipeline.py tests/test_portfolio_graph.py
git commit -m "feat: --rebuild-portfolio-graph flag and full-run refresh"
```

---

### Task 8: UI trigger (route + run helper)

**Files:**
- Modify: `job-pilot/ui/src/lib/run.ts`
- Create: `job-pilot/ui/src/app/api/portfolio-graph/route.ts`

**Interfaces:**
- Consumes: `runWithArgs` and `latestRun` in `lib/run.ts`.
- Produces: `triggerPortfolioGraph(): Promise<void>` (runs `["--rebuild-portfolio-graph"]`); a `POST /api/portfolio-graph` route that triggers it and a `GET` that returns `latestRun()` state.

- [ ] **Step 1: Add the run helper**

In `job-pilot/ui/src/lib/run.ts`, add:

```typescript
export async function triggerPortfolioGraph(): Promise<void> {
  await runWithArgs(["--rebuild-portfolio-graph"]);
}
```

- [ ] **Step 2: Create the route**

Create `job-pilot/ui/src/app/api/portfolio-graph/route.ts`:

```typescript
import { latestRun, triggerPortfolioGraph } from "@/lib/run";

export async function POST() {
  try {
    const current = await latestRun();
    if (current.state === "RUNNING") {
      return Response.json({ ok: true, alreadyRunning: true });
    }
    await triggerPortfolioGraph();
    return Response.json({ ok: true });
  } catch (e) {
    return Response.json({ error: String(e) }, { status: 500 });
  }
}

export async function GET() {
  try {
    return Response.json(await latestRun());
  } catch (e) {
    return Response.json({ error: String(e) }, { status: 500 });
  }
}
```

- [ ] **Step 3: Typecheck the UI**

Run: `cd job-pilot/ui && npm run lint && npx tsc --noEmit`
Expected: no errors. (If `npm run lint` script differs, run `npx next lint`.)

- [ ] **Step 4: Commit**

```bash
git add ui/src/lib/run.ts ui/src/app/api/portfolio-graph/route.ts
git commit -m "feat: portfolio-graph rebuild trigger route"
```

---

### Task 9: UI Knowledge page with rebuild button

**Files:**
- Create: `job-pilot/ui/src/app/knowledge/page.tsx`
- Modify: nav (add a "Knowledge" entry where the other tabs/links are registered — inspect `ui/src/components` for the nav component and mobile bottom nav noted in the system memory)

**Interfaces:**
- Consumes: `POST /api/portfolio-graph` (trigger), `GET /api/portfolio-graph` (state).
- Produces: a page with a "Rebuild portfolio knowledge" button that POSTs, disables while `state === "RUNNING"`, and shows last-run state; polls `GET` every 15s while running.

- [ ] **Step 1: Create the page**

Create `job-pilot/ui/src/app/knowledge/page.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";

type RunState = "RUNNING" | "SUCCEEDED" | "FAILED" | "NONE";

export default function KnowledgePage() {
  const [state, setState] = useState<RunState>("NONE");
  const [started, setStarted] = useState("");

  async function refresh() {
    const res = await fetch("/api/portfolio-graph");
    const data = (await res.json()) as { state: RunState; started: string };
    setState(data.state);
    setStarted(data.started);
  }

  useEffect(() => {
    refresh();
  }, []);

  useEffect(() => {
    if (state !== "RUNNING") return;
    const id = setInterval(refresh, 15000);
    return () => clearInterval(id);
  }, [state]);

  async function rebuild() {
    setState("RUNNING");
    await fetch("/api/portfolio-graph", { method: "POST" });
    refresh();
  }

  return (
    <main className="mx-auto max-w-2xl p-6">
      <h1 className="text-xl font-semibold">Portfolio knowledge</h1>
      <p className="mt-2 text-sm opacity-70">
        Crawls your portfolio, rebuilds the project knowledge graph, and refreshes the
        answer grounding. Runs automatically in the daily pipeline; use this to rebuild
        now after publishing new work.
      </p>
      <button
        onClick={rebuild}
        disabled={state === "RUNNING"}
        className="mt-4 rounded-lg px-4 py-2 text-sm font-medium shadow disabled:opacity-50"
      >
        {state === "RUNNING" ? "Rebuilding…" : "Rebuild portfolio knowledge"}
      </button>
      <p className="mt-3 text-xs opacity-60">
        Last run: {state}
        {started ? ` · ${new Date(started).toLocaleString()}` : ""}
      </p>
    </main>
  );
}
```

Match the button/card styling to the existing light card system (shared primitives in `ui/src/components/ui/`) rather than raw Tailwind classes if those primitives exist — inspect a sibling page (e.g. the Assistant page) and reuse its `Button`/`Card` components for visual consistency.

- [ ] **Step 2: Register nav entry**

Inspect the nav component(s) (desktop + mobile bottom nav) and add a "Knowledge" link to `/knowledge`, following the exact pattern of the existing entries (Jobs, Companies, Replies, Assistant).

- [ ] **Step 3: Typecheck and build**

Run: `cd job-pilot/ui && npx tsc --noEmit && npm run build`
Expected: build succeeds, `/knowledge` route compiled.

- [ ] **Step 4: Commit**

```bash
git add ui/src/app/knowledge/page.tsx ui/src/components
git commit -m "feat: Knowledge page with rebuild-portfolio button"
```

---

### Task 10: Visual graph map to Drive (optional viewer)

**Files:**
- Modify: `src/jobpilot/portfolio_graph.py`
- Test: `tests/test_portfolio_graph.py`

**Interfaces:**
- Consumes: `PortfolioGraph`; `tailor._drive`/folder helpers for Drive upload (reuse the existing `_ensure_folder`/upload pattern in `tailor.py`).
- Produces: `render_html(graph) -> str` (self-contained HTML, nodes+edges embedded as JSON, no external CDN) and an upload step in `rebuild` that writes `_portfolio_graph.html` to the `JobPilot Applications` Drive folder. HTML uses inline SVG/force layout with the embedded data — no network calls (CSP-safe, matches the artifact self-contained rule).

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_portfolio_graph.py
def test_render_html_is_self_contained():
    g = pg.build_graph([pg.PageExtract(projects=[pg.ProjectFacts(name="JobPilot")])],
                       ["https://x"], "2026-07-24 12:00")
    html = pg.render_html(g)
    assert "<html" in html.lower()
    assert "JobPilot" in html
    assert "http://" not in html and "https://cdn" not in html  # no external assets
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd job-pilot && python -m pytest tests/test_portfolio_graph.py::test_render_html_is_self_contained -q`
Expected: FAIL (`render_html` missing)

- [ ] **Step 3: Write minimal implementation**

```python
# add to src/jobpilot/portfolio_graph.py
import json


def render_html(graph: PortfolioGraph) -> str:
    """Self-contained HTML map: embedded data, inline canvas layout, no external assets."""
    data = json.dumps({"nodes": [n.model_dump() for n in graph.nodes],
                       "edges": [e.model_dump() for e in graph.edges]})
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
```

In `rebuild`, after writing the graph to the Sheet, upload the HTML (best-effort, never fails the run):

```python
        try:
            from jobpilot import tailor
            folder = tailor._ensure_folder(creds, "JobPilot Applications")
            tailor.upload_bytes(creds, folder, "_portfolio_graph.html",
                                render_html(graph).encode("utf-8"), "text/html")
        except Exception as exc:  # noqa: BLE001
            notes.append(f"portfolio graph html: skipped ({type(exc).__name__})")
```

If `tailor` has no generic `upload_bytes`, add one mirroring `upload_pdf`:

```python
# in src/jobpilot/tailor.py
def upload_bytes(creds, folder_id: str, filename: str, blob: bytes,
                 mimetype: str) -> str:
    f = _drive(creds).files().create(
        body={"name": filename, "parents": [folder_id]},
        media_body=MediaInMemoryUpload(blob, mimetype=mimetype),
        fields="id, webViewLink").execute()
    return f.get("webViewLink", "")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd job-pilot && python -m pytest tests/test_portfolio_graph.py -q`
Expected: PASS (all portfolio-graph tests green)

- [ ] **Step 5: Commit**

```bash
git add src/jobpilot/portfolio_graph.py src/jobpilot/tailor.py tests/test_portfolio_graph.py
git commit -m "feat: self-contained portfolio graph HTML map to Drive"
```

---

### Task 11: Full suite, lint, and deploy check

**Files:** none (verification task)

- [ ] **Step 1: Run the whole Python suite**

Run: `cd job-pilot && python -m pytest -q`
Expected: all green (existing + new). Fix any regression before proceeding.

- [ ] **Step 2: Lint**

Run: `cd job-pilot && ruff check src/jobpilot/portfolio_graph.py src/jobpilot/knowledge.py src/jobpilot/sheets.py src/jobpilot/__main__.py`
Expected: no findings. Clean up the redundant `nid` lines flagged in Task 4 and any unused imports.

- [ ] **Step 3: Smoke-test the CLI locally (dry, no submit)**

Run (needs local creds/token as the existing tools do): `cd job-pilot && python -m jobpilot --rebuild-portfolio-graph`
Expected: prints `portfolio graph: N pages, M projects`; the `PortfolioGraph` tab in the Dashboard Sheet gets a `graph` row; the Assistant answers now reference real projects. If auth is unavailable locally, defer this to the deployed job (push auto-deploys; then trigger via the Knowledge button and check the Sheet tab).

- [ ] **Step 4: UI build**

Run: `cd job-pilot/ui && npx tsc --noEmit && npm run build`
Expected: clean build with `/knowledge` and `/api/portfolio-graph` present.

- [ ] **Step 5: Commit any fixes**

```bash
git add -A
git commit -m "test: portfolio graph full-suite and lint pass"
```

---

## Notes for the implementer

- **IAM:** the UI service account already triggers `jobpilot` runs with arg overrides (tailor/outreach), so `--rebuild-portfolio-graph` needs no new permission — it reuses the same `jobpilot` job, not a new one. (The separate `jobpilot-apply` job comes in a later plan.)
- **Cost:** one Gemini call per crawled page (~14-40 pages) on `cfg.scoring.model` (Flash). Pennies per rebuild; daily refresh is fine.
- **Why graph-then-pack:** the answer engine (Plan 2) reads the Knowledge pack, so rendering the graph into the pack means zero changes there. The graph JSON + HTML map are for retrieval/subgraph selection and human viewing.
- **Do not** commit the user's real portfolio content into any test fixture; tests use synthetic `example.com` content only.
