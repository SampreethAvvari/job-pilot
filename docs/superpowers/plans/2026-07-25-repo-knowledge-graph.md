# Repo Knowledge Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Build a separate knowledge graph of every git repo the user contributed to (their own repos plus private/org repos), sourced from the GitHub GraphQL contributions API, stored in a `RepoGraph` Sheet tab, rendered into the Knowledge pack (so auto-apply answers can cite real repos and roles), with a visual map and a console rebuild trigger. Mirrors the deployed Portfolio Knowledge Graph.

**Architecture:** New `src/jobpilot/repo_graph.py` reuses the graph data model from `portfolio_graph.py` (GraphNode/GraphEdge/PortfolioGraph-style container). Instead of crawling a website, it calls the GitHub GraphQL API with a PAT (from Secret Manager env `JOBPILOT_GITHUB_TOKEN`) to fetch the user's `contributionsCollection` (repos contributed to, incl. private/org) + repo metadata (languages, topics, description, stars). It builds nodes (repo, org, language, framework/topic) and edges (contributed-to, owned-by-org, uses-language), stores the graph in a `RepoGraph` tab, renders it into a NEW Knowledge-pack section (separate from `portfolio`), and exposes a rebuild on the console. Reuses the Sheet-store, render-to-pack, HTML-map, and CLI/UI-trigger patterns already shipped.

**Tech Stack:** Python 3.12, pydantic v2, httpx (GitHub GraphQL), google-api-python-client (Sheets/Drive), Next.js UI.

Prereq (owner, not code): a GitHub classic PAT with scopes `repo` + `read:org`, stored as Secret Manager secret mounted to env `JOBPILOT_GITHUB_TOKEN`. All tasks build + test with a MOCKED GitHub API (pytest-httpx); the token is only needed for real runs.

## Global Constraints

- Python 3.12; `from __future__ import annotations`; ruff E4/E7/E9/F.
- Reuse `portfolio_graph`'s `GraphNode`/`GraphEdge` and the `PortfolioGraph` container (or a thin alias) rather than redefining graph primitives. Reuse `sanitize`/render patterns.
- Never raise out of the rebuild path (degrade to notes), exactly like `portfolio_graph.rebuild`.
- GitHub token read from env `JOBPILOT_GITHUB_TOKEN`; if absent, rebuild returns a "no token" note and does NOT overwrite the stored graph.
- Empty/failed fetch must NOT overwrite a good stored graph (same guard shipped in portfolio_graph: skip write when 0 repos).
- HTML map must be self-contained AND XSS-safe (escape embedded JSON like the portfolio map fix: `<`/`>`/`&`).
- Sheet-is-the-store, 45000 cell cap (drop whole nodes if over, don't slice JSON).
- No personal data / real tokens in tracked tests; mock the GitHub API. No token ever committed.
- This graph renders into a SEPARATE knowledge-pack section keyed `repos` (portfolio graph keeps `portfolio`); both feed the same pack the answer engine + Assistant read.
- Commit as SampreethAvvari <spa9659@nyu.edu>, no Claude co-author trailer.

---

### Task 1: GitHub contributions client (mocked)

**Files:** Create `src/jobpilot/github_repos.py`; Test `tests/test_github_repos.py`

**Interfaces:** Produces `fetch_contributed_repos(token: str, client) -> list[RepoFacts]` where `RepoFacts` is a pydantic model (name, owner, is_org, is_private, description, primary_language, languages: list[str], topics: list[str], stars, url, contribution_commits). Uses the GitHub GraphQL endpoint `https://api.github.com/graphql` with `Authorization: bearer <token>`. Query `viewer.repositoriesContributedTo` (+ `viewer.repositories` for own) with `contributionsCollection` where available; page via cursors. Degrades to `[]` on error (never raises).

- [ ] Step 1: failing test — mock a GraphQL JSON response (pytest-httpx) with 2 repos (one org/private, one own/public) and assert `fetch_contributed_repos` parses both into `RepoFacts` with languages/topics/owner/is_org. Include a test that an HTTP 401/error returns `[]`.
- [ ] Step 2: run, confirm fail.
- [ ] Step 3: implement `RepoFacts` + `fetch_contributed_repos` (GraphQL POST, parse `data.viewer...nodes`, map to RepoFacts; try/except -> []). Keep the query in a module constant.
- [ ] Step 4: run, confirm pass.
- [ ] Step 5: commit `feat: GitHub contributions client for repo graph`.

### Task 2: Build the repo graph

**Files:** Modify `src/jobpilot/repo_graph.py` (new module that imports graph primitives from portfolio_graph); Test `tests/test_repo_graph.py`

**Interfaces:** Produces `build_repo_graph(repos: list[RepoFacts], now_str) -> <graph container>`. Nodes: `repo:<owner>-<name>` (data: description, stars, url, languages, commits, private), `org:<owner>` (for org-owned), `language:<lang>`, `topic:<topic>`. Edges: repo->language `uses-language`, repo->org `owned-by-org`, repo->topic `tagged`. Dedup repos by owner/name slug; merge languages/topics. Drop degenerate labels (reuse the portfolio_graph `_slug` degenerate-guard lesson). Reuse `GraphNode`/`GraphEdge`.

- [ ] TDD: two RepoFacts (one org, one own) -> assert repo nodes deduped, org node + owned-by-org edge for the org repo only, language nodes merged, no empty-id nodes. Commit `feat: assemble repo graph from contributions`.

### Task 3: RepoGraph Sheet storage

**Files:** Modify `src/jobpilot/sheets.py`; Test `tests/test_repo_graph.py`

**Interfaces:** `ensure_repo_graph_tab`, `write_repo_graph(creds, sid, graph_json, now_str)`, `read_repo_graph(creds, sid) -> str`. Tab `RepoGraph`, headers `["Key","Updated","JSON"]`, row key `graph`, 45000 cap (drop whole nodes if over, not slice). Mirror `ensure_portfolio_graph_tab` exactly (fake-`_svc` roundtrip test).

- [ ] TDD roundtrip + oversize-drops-nodes-not-slice test. Commit `feat: RepoGraph sheet tab storage`.

### Task 4: Orchestrator + pack rendering (separate `repos` section)

**Files:** Modify `src/jobpilot/repo_graph.py`, `src/jobpilot/knowledge.py`; Test `tests/test_repo_graph.py`

**Interfaces:** `render_repo_pack(graph) -> str` (per-repo text: name, role/commits, languages, topics, url). `rebuild(creds, sid, cfg, client, now) -> list[str]`: read token from env `JOBPILOT_GITHUB_TOKEN`; if absent -> `["repo graph: no JOBPILOT_GITHUB_TOKEN, skipped"]` and NO write; else fetch -> build -> if 0 repos, keep previous (no write) -> else write graph + note "repo graph: N repos, M orgs". Add a NEW `repos` builder to `knowledge.refresh`'s builders dict (alongside `portfolio`) rendering from `read_repo_graph`; add `"repos"` to `AUTO_SECTIONS`. Never raises.

- [ ] TDD: render_repo_pack lists repos with url; rebuild with mocked fetch writes and notes; no-token path skips write; knowledge pack gains a `repos` section. Commit `feat: repo graph orchestrator + repos knowledge section`.

### Task 5: CLI + daily refresh + XSS-safe HTML map

**Files:** Modify `src/jobpilot/__main__.py`, `src/jobpilot/pipeline.py`, `src/jobpilot/repo_graph.py`; Test `tests/test_repo_graph.py`

**Interfaces:** `--rebuild-repo-graph` CLI flag (mirror `--rebuild-portfolio-graph`); call `repo_graph.rebuild` in the full pipeline run next to the portfolio rebuild. `render_repo_html(graph) -> str` self-contained + XSS-escaped (reuse the portfolio map's escape: embed only id/type/label + edges, `.replace('<','\\u003c')...`), best-effort Drive upload `_repo_graph.html` in rebuild.

- [ ] TDD: flag present + behavioral pipeline test (rebuild called in full run, skipped in fast); `render_repo_html` escapes a `</script>` label (count==1) and has no external assets. Commit `feat: --rebuild-repo-graph flag, daily refresh, XSS-safe map`.

### Task 6: Console trigger + Knowledge page section

**Files:** Modify `ui/src/lib/run.ts` (add `triggerRepoGraph`), Create `ui/src/app/api/repo-graph/route.ts` (mirror portfolio-graph route), Modify `ui/src/components/knowledge-panel.tsx` (add a second "Rebuild repo knowledge" button + its own last-run line, or a second panel). No dashes in copy.

- [ ] Build + verify `cd ui && npx tsc --noEmit && npm run lint && npm run build`. Commit `feat: repo-graph rebuild trigger + console button`.

### Task 7: Full suite, lint, UI build, deploy

- [ ] `.venv/Scripts/python.exe -m pytest -q` green; ruff clean on new files; UI build green.
- [ ] Final whole-branch review (fable), fix must-fixes.
- [ ] Merge to master + push (auto-deploys). Owner then adds the PAT secret + env wiring for real data.

## Notes

- **Owner prereq:** create `JOBPILOT_GITHUB_TOKEN` secret (classic PAT, scopes `repo` + `read:org`), mount to the Cloud Run job env. Until then, `--rebuild-repo-graph` no-ops with a note and the console button reports "no token".
- Reuse portfolio_graph primitives and the shipped lessons: never-overwrite-on-empty, drop-whole-nodes size cap, XSS-escape the HTML map, degenerate-label guard.
- Keep `repos` and `portfolio` as distinct pack sections so the answer engine can cite both without conflation.
