import httpx

from jobpilot.github_repos import RepoFacts, fetch_contributed_repos


def _node(name, login, typename, is_private, languages=None, topics=None):
    return {
        "nameWithOwner": f"{login}/{name}",
        "name": name,
        "owner": {"login": login, "__typename": typename},
        "isPrivate": is_private,
        "description": f"{name} description",
        "stargazerCount": 3,
        "url": f"https://github.com/{login}/{name}",
        "primaryLanguage": {"name": "Python"},
        "languages": {"nodes": [{"name": ln} for ln in (languages or [])]},
        "repositoryTopics": {"nodes": [{"topic": {"name": t}} for t in (topics or [])]},
    }


def test_fetch_contributed_repos_parses_org_and_own_repos(httpx_mock):
    httpx_mock.add_response(
        url="https://api.github.com/graphql",
        json={
            "data": {
                "viewer": {
                    "repositoriesContributedTo": {
                        "nodes": [
                            _node(
                                "widget-lib", "acme-org", "Organization", True,
                                languages=["Python", "Go"], topics=["infra"],
                            ),
                            _node(
                                "my-tool", "sampleuser", "User", False,
                            ),
                        ]
                    }
                }
            }
        },
    )

    repos = fetch_contributed_repos("faketoken", httpx.Client())

    assert len(repos) == 2
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
