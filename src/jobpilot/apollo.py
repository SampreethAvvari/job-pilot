"""Apollo.io contact lookup — best-effort on the free plan.

Free plans have very limited API access; every call degrades gracefully:
no key -> skipped, 401/403/402 (plan limits) -> skipped with note.
"""

from __future__ import annotations

import os

import httpx

API = "https://api.apollo.io/api/v1"
TITLES = [
    "technical recruiter", "recruiter", "talent acquisition",
    "university recruiter", "engineering manager",
]


class Contact(dict):
    """{name, title, email (may be ''), linkedin_url}"""


def find_contacts(company: str, client: httpx.Client, max_contacts: int = 2) -> list[Contact]:
    key = os.environ.get("APOLLO_API_KEY")
    if not key:
        return []
    headers = {"X-Api-Key": key, "Content-Type": "application/json"}
    resp = client.post(
        f"{API}/mixed_people/search",
        headers=headers,
        json={
            "q_organization_name": company,
            "person_titles": TITLES,
            "page": 1,
            "per_page": max_contacts,
        },
    )
    if resp.status_code in (401, 402, 403, 422):
        return []  # plan does not allow people search
    resp.raise_for_status()
    out: list[Contact] = []
    for p in resp.json().get("people", [])[:max_contacts]:
        email = p.get("email") or ""
        if "email_not_unlocked" in email:
            email = _reveal_email(p.get("id"), headers, client)
        out.append(Contact(
            name=p.get("name", ""),
            title=p.get("title", ""),
            email=email,
            linkedin_url=p.get("linkedin_url", ""),
        ))
    return out


def _reveal_email(person_id: str | None, headers: dict, client: httpx.Client) -> str:
    """Spend one credit to unlock an email; empty string when not possible."""
    if not person_id:
        return ""
    try:
        resp = client.post(f"{API}/people/match", headers=headers, json={"id": person_id})
        if resp.status_code != 200:
            return ""
        email = (resp.json().get("person") or {}).get("email") or ""
        return "" if "email_not_unlocked" in email else email
    except httpx.HTTPError:
        return ""


def linkedin_people_search_url(company: str) -> str:
    from urllib.parse import quote

    return ("https://www.linkedin.com/search/results/people/?keywords="
            + quote(f'"{company}" recruiter'))
