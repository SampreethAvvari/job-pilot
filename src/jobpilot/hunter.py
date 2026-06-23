"""Hunter.io email discovery — reliable, free-tier friendly.

One Domain Search call per company (1 credit) returns the company's email
pattern plus named people with confidence-scored work emails. No key -> skipped;
any error -> skipped. NOTHING is ever sent; this only finds addresses.
"""

from __future__ import annotations

import os

import httpx

API = "https://api.hunter.io/v2"

# Roles worth emailing, scored high -> low. Matched against Hunter's
# department/position/seniority fields (lowercased substring match).
ROLE_WEIGHTS = [
    ("recruit", 100), ("talent", 95), ("people", 70), ("human resources", 70),
    ("hr", 65), ("hiring", 90),
    ("founder", 88), ("co-founder", 88), ("ceo", 85), ("cto", 85),
    ("chief", 80), ("head of engineering", 82), ("vp engineering", 80),
    ("engineering manager", 78), ("engineering", 55), ("technical", 55),
]


class Contact(dict):
    """{name, email, position, department, seniority, confidence}"""


def _role_score(position: str, department: str, seniority: str) -> int:
    hay = " ".join((position, department, seniority)).lower()
    best = 0
    for needle, weight in ROLE_WEIGHTS:
        if needle in hay:
            best = max(best, weight)
    return best


def find_contacts(company: str, domain: str, client: httpx.Client,
                  limit: int = 10) -> tuple[str, list[Contact]]:
    """Return (email_pattern, contacts) for a company. ('', []) when unavailable.

    Prefers `domain`; falls back to the company name so Hunter resolves it.
    Contacts are people with a usable work email, ranked by target-role fit then
    Hunter confidence. Costs one Domain Search credit per call.
    """
    key = os.environ.get("HUNTER_API_KEY")
    if not key:
        return "", []
    params = {"api_key": key, "limit": limit, "type": "personal"}
    if domain:
        params["domain"] = domain
    else:
        params["company"] = company
    try:
        resp = client.get(f"{API}/domain-search", params=params, timeout=30)
        if resp.status_code != 200:
            return "", []  # 401/429/usage-limit -> degrade quietly
        data = resp.json().get("data") or {}
    except (httpx.HTTPError, ValueError):
        return "", []

    pattern = data.get("pattern") or ""
    out: list[Contact] = []
    for e in data.get("emails", []):
        email = (e.get("value") or "").strip()
        if not email:
            continue
        first = e.get("first_name") or ""
        last = e.get("last_name") or ""
        name = (f"{first} {last}").strip()
        position = e.get("position") or ""
        department = e.get("department") or ""
        seniority = e.get("seniority") or ""
        out.append(Contact(
            name=name,
            email=email,
            position=position,
            department=department,
            seniority=seniority,
            confidence=int(e.get("confidence") or 0),
            score=_role_score(position, department, seniority),
        ))
    # Best target role first, then Hunter confidence; people with a name win ties.
    out.sort(key=lambda c: (c["score"], c["confidence"], bool(c["name"])),
             reverse=True)
    return pattern, out
