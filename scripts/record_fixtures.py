"""Record one real API response per keyless source into tests/fixtures/.

Also validates the profile.yaml watchlist: reports which Greenhouse/Lever/Ashby
slugs return 404 so they can be pruned. Run from repo root:

    python scripts/record_fixtures.py
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx

ROOT = Path(__file__).parent.parent
FIXTURES = ROOT / "tests" / "fixtures"


def save(name: str, data) -> None:
    """Save fixture, structurally truncated to keep files small but valid JSON."""
    if isinstance(data, list):
        data = data[:30]
    elif isinstance(data, dict) and isinstance(data.get("jobs"), list):
        jobs = sorted(  # keep engineer roles so query-matching tests have hits
            data["jobs"], key=lambda j: "engineer" not in str(j.get("title", "")).lower()
        )
        data = {**data, "jobs": jobs[:30]}
    FIXTURES.mkdir(parents=True, exist_ok=True)
    (FIXTURES / f"{name}.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
    print(f"saved {name}.json")


def main() -> None:
    import yaml

    cfg = yaml.safe_load((ROOT / "profile.yaml").read_text(encoding="utf-8"))
    sources = cfg["sources"]
    client = httpx.Client(timeout=30, follow_redirects=True)

    # --- validate watchlists, record first live board of each type ---
    for src, base in [
        ("greenhouse", "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"),
        ("lever", "https://api.lever.co/v0/postings/{slug}?mode=json"),
        ("ashby", "https://api.ashbyhq.com/posting-api/job-board/{slug}"),
    ]:
        recorded = False
        for slug in sources[src]["companies"]:
            r = client.get(base.format(slug=slug))
            ok = r.status_code == 200
            print(f"{src}:{slug} -> {r.status_code}")
            if ok and not recorded:
                save(src, r.json())
                recorded = True

    # --- remoteok ---
    r = client.get("https://remoteok.com/api", headers={"User-Agent": "JobPilot/1.0"})
    print(f"remoteok -> {r.status_code}")
    if r.status_code == 200:
        save("remoteok", r.json()[:40])

    # --- hn who's hiring ---
    s = client.get(
        "https://hn.algolia.com/api/v1/search_by_date",
        params={"query": "Ask HN: Who is hiring?", "tags": "story,author_whoishiring"},
    )
    save("hn_story", s.json())
    story_id = next(
        h["objectID"] for h in s.json()["hits"] if "who is hiring" in h["title"].lower()
    )
    c = client.get(
        "https://hn.algolia.com/api/v1/search_by_date",
        params={"tags": f"comment,story_{story_id}", "hitsPerPage": 50},
    )
    print(f"hn_hiring story={story_id} -> {c.status_code}")
    save("hn_comments", c.json())


if __name__ == "__main__":
    main()
