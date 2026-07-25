import httpx

from jobpilot.github_repos import RepoFacts, fetch_contributed_repos


def _node(name, login, typename, is_private, languages=None, topics=None, is_fork=False):
    return {
        "nameWithOwner": f"{login}/{name}",
        "name": name,
        "owner": {"login": login, "__typename": typename},
        "isPrivate": is_private,
        "isFork": is_fork,
        "description": f"{name} description",
        "stargazerCount": 3,
        "url": f"https://github.com/{login}/{name}",
        "primaryLanguage": {"name": "Python"},
        "languages": {"nodes": [{"name": ln} for ln in (languages or [])]},
        "repositoryTopics": {"nodes": [{"topic": {"name": t}} for t in (topics or [])]},
    }


def test_fetch_contributed_repos_merges_dedups_and_drops_forks(httpx_mock):
    widget = _node("widget-lib", "acme-org", "Organization", True,
                   languages=["Python", "Go"], topics=["infra"])
    httpx_mock.add_response(
        url="https://api.github.com/graphql",
        json={
            "data": {
                "viewer": {
                    # org repo appears in BOTH connections (must dedup to one)
                    "contributed": {"nodes": [widget, _node("my-tool", "sampleuser", "User", False)]},
                    "owned": {"nodes": [
                        widget,  # duplicate of the contributed one
                        _node("owned-app", "sampleuser", "User", True),
                        _node("someone-fork", "sampleuser", "User", False, is_fork=True),  # dropped
                    ]},
                }
            }
        },
    )

    repos = fetch_contributed_repos("faketoken", httpx.Client())

    # widget (deduped) + my-tool + owned-app = 3; the fork is dropped
    assert len(repos) == 3
    names = {r.name for r in repos}
    assert names == {"widget-lib", "my-tool", "owned-app"}
    assert "someone-fork" not in names
    org_repo = next(r for r in repos if r.owner == "acme-org")
    assert org_repo.name == "widget-lib"
    assert org_repo.is_org is True
    assert org_repo.is_private is True
    assert org_repo.languages == ["Python", "Go"]
    assert org_repo.topics == ["infra"]
    assert org_repo.primary_language == "Python"
    assert org_repo.stars == 3
    assert org_repo.url == "https://github.com/acme-org/widget-lib"

    own_repo = next(r for r in repos if r.owner == "sampleuser")
    assert own_repo.name == "my-tool"
    assert own_repo.is_org is False
    assert own_repo.is_private is False
    assert own_repo.languages == []
    assert own_repo.topics == []

    for repo in repos:
        assert isinstance(repo, RepoFacts)


def test_fetch_contributed_repos_degrades_to_empty_on_http_error(httpx_mock):
    httpx_mock.add_response(
        url="https://api.github.com/graphql",
        status_code=401,
        json={"message": "Bad credentials"},
    )

    assert fetch_contributed_repos("faketoken", httpx.Client()) == []


def test_fetch_contributed_repos_degrades_to_empty_on_malformed_json(httpx_mock):
    httpx_mock.add_response(
        url="https://api.github.com/graphql",
        content=b"not json",
    )

    assert fetch_contributed_repos("faketoken", httpx.Client()) == []
