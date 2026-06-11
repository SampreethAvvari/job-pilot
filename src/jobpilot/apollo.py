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


MAX_REVEALS = 3  # people/match spends a credit each — cap the burn per company


def find_contacts(company: str, client: httpx.Client, max_contacts: int = 2) -> list[Contact]:
    """Contacts that have a usable email — drafts without a recipient are banned.

    `mixed_people/search` was deprecated by Apollo (422) — `api_search` is the
    replacement, but it hides name/email until `people/match` reveals them.
    """
    key = os.environ.get("APOLLO_API_KEY")
    if not key:
        return []
    headers = {"X-Api-Key": key, "Content-Type": "application/json"}
    resp = client.post(
        f"{API}/mixed_people/api_search",
        headers=headers,
        json={
            "q_organization_name": company,
            "person_titles": TITLES,
            "page": 1,
            "per_page": 5,
        },
    )
    if resp.status_code in (401, 402, 403, 422):
        return []  # plan does not allow people search
    resp.raise_for_status()
    out: list[Contact] = []
    reveals = 0
    for p in resp.json().get("people", []):
        if len(out) >= max_contacts or reveals >= MAX_REVEALS:
            break
        email = _clean(p.get("email"))
        name = p.get("name") or ""
        linkedin = p.get("linkedin_url") or ""
        if not email or not name:
            reveals += 1
            person = _match(p.get("id"), headers, client)
            email = email or _clean(person.get("email"))
            name = name or person.get("name") or ""
            linkedin = linkedin or person.get("linkedin_url") or ""
        if not email:
            continue  # no recipient -> useless for outreach
        out.append(Contact(
            name=name,
            title=p.get("title", ""),
            email=email,
            linkedin_url=linkedin,
        ))
    return out


def _clean(email: str | None) -> str:
    email = email or ""
    return "" if "email_not_unlocked" in email else email


def _match(person_id: str | None, headers: dict, client: httpx.Client) -> dict:
    """Spend one credit to reveal a person's name/email; {} when not possible."""
    if not person_id:
        return {}
    try:
        resp = client.post(
            f"{API}/people/match", headers=headers,
            json={"id": person_id, "reveal_personal_emails": False},
        )
        if resp.status_code != 200:
            return {}
        return resp.json().get("person") or {}
    except httpx.HTTPError:
        return {}


def linkedin_people_search_url(company: str) -> str:
    from urllib.parse import quote

    return ("https://www.linkedin.com/search/results/people/?keywords="
            + quote(f'"{company}" recruiter'))
