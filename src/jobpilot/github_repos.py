"""GitHub contributions client for the repo knowledge graph.

Fetches every repo the authenticated user contributed to (own, private, and
org repos alike) via the GitHub GraphQL API. Best-effort only: any failure
(bad token, rate limit, malformed response) degrades to an empty list rather
than raising, so a graph rebuild never breaks on GitHub trouble.
"""

from __future__ import annotations

import httpx
from pydantic import BaseModel, Field

GITHUB_GRAPHQL = "https://api.github.com/graphql"

# Everything the user is part of: repos contributed to, repos owned, and repos
# in orgs they belong to (e.g. Hybridge). Merged + deduped in fetch. Single page
# of 100 per connection comfortably covers one person's repos; GraphQL cursors
# could page past that if ever needed.
CONTRIB_QUERY = """
fragment repoFields on Repository {
  nameWithOwner
  name
  owner { login __typename }
  isPrivate
  isFork
  description
  stargazerCount
  url
  primaryLanguage { name }
  languages(first: 10) { nodes { name } }
  repositoryTopics(first: 10) { nodes { topic { name } } }
}
query {
  viewer {
    contributed: repositoriesContributedTo(first: 100, contributionTypes: [COMMIT, PULL_REQUEST, REPOSITORY], includeUserRepositories: true) {
      nodes { ...repoFields }
    }
    owned: repositories(first: 100, ownerAffiliations: [OWNER, COLLABORATOR, ORGANIZATION_MEMBER], orderBy: { field: PUSHED_AT, direction: DESC }) {
      nodes { ...repoFields }
    }
  }
}
"""


class RepoFacts(BaseModel):
    name: str
    owner: str
    is_org: bool = False
    is_private: bool = False
    description: str = ""
    primary_language: str = ""
    languages: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    stars: int = 0
    url: str = ""
    contribution_commits: int = 0


def _to_repo_facts(node: dict) -> RepoFacts:
    owner = node.get("owner") or {}
    primary_language = node.get("primaryLanguage") or {}
    languages = [n["name"] for n in (node.get("languages") or {}).get("nodes", [])]
    topics = [
        t["topic"]["name"] for t in (node.get("repositoryTopics") or {}).get("nodes", [])
    ]
    return RepoFacts(
        name=node["name"],
        owner=owner.get("login", ""),
        is_org=owner.get("__typename") == "Organization",
        is_private=bool(node.get("isPrivate")),
        description=node.get("description") or "",
        primary_language=primary_language.get("name") or "",
        languages=languages,
        topics=topics,
        stars=node.get("stargazerCount") or 0,
        url=node.get("url") or "",
    )


def fetch_contributed_repos(token: str, client: httpx.Client) -> list[RepoFacts]:
    """All repos the user contributed to (own + private + org). Never raises —
    any error (auth, rate limit, malformed response) degrades to []."""
    headers = {"Authorization": f"bearer {token}", "Content-Type": "application/json"}
    try:
        resp = client.post(GITHUB_GRAPHQL, headers=headers, json={"query": CONTRIB_QUERY})
        resp.raise_for_status()
        viewer = resp.json()["data"]["viewer"]
        merged = ((viewer.get("contributed") or {}).get("nodes", [])
                  + (viewer.get("owned") or {}).get("nodes", []))
        seen: set[str] = set()
        out: list[RepoFacts] = []
        for node in merged:
            key = node.get("nameWithOwner")
            if not key or key in seen or node.get("isFork"):
                continue  # dedup across the two connections; drop forks (not "his" work)
            seen.add(key)
            out.append(_to_repo_facts(node))
        return out
    except Exception:  # noqa: BLE001 — best-effort fetch, always degrade to []
        return []
