"""Seed the Companies watchlist tab with a curated set of tech companies.

Resolves every candidate locally (ATS detection + board verification) so the
production pipeline never has to probe a large batch, then appends only the
companies whose boards actually answer. Re-running skips names already present.

Usage:
    python scripts/seed_companies.py          # dry run: resolve + report only
    python scripts/seed_companies.py --apply  # resolve + append to the Sheet

The list is curated for: public ATS APIs we can poll (Greenhouse, Lever, Ashby,
Workday, SmartRecruiters, Workable, Recruitee), companies known to sponsor
work visas, and active early-career engineering hiring. Mega-caps with custom
anti-bot portals (Google, Meta, Apple, Amazon, Netflix, Microsoft...) are
deliberately absent — aggregator sources cover them.
"""

from __future__ import annotations

import sys

import httpx

from jobpilot.companies import CompanyRow
from jobpilot import resolver

# (Company, careers URL) — URL given where detection needs it (Workday tenants
# can't be guessed; a few Greenhouse slugs differ from the company name).
CANDIDATES: list[tuple[str, str]] = [
    # --- AI labs, ML infra, GPU clouds ---
    ("OpenAI", ""), ("Anthropic", ""), ("Mistral AI", ""), ("Cohere", ""),
    ("Hugging Face", ""), ("Perplexity", ""), ("xAI", ""), ("Together AI", ""),
    ("Fireworks AI", ""), ("Groq", ""), ("Cerebras Systems", ""),
    ("SambaNova Systems", ""), ("Runway", ""), ("Luma AI", ""), ("Harvey", ""),
    ("Glean", ""), ("Writer", ""), ("Anyscale", ""), ("Weights & Biases", ""),
    ("LangChain", ""), ("Pinecone", ""), ("Weaviate", ""), ("Baseten", ""),
    ("Modal", ""), ("CoreWeave", ""), ("Lambda", ""), ("Crusoe", ""),
    ("Scale AI", ""), ("Snorkel AI", ""), ("Labelbox", ""),
    ("ElevenLabs", ""), ("Cursor", ""), ("Sierra", ""), ("Replit", ""),
    # --- Dev tools, data, cloud infra ---
    ("Vercel", ""), ("GitLab", ""), ("Docker", ""), ("Postman", ""),
    ("Kong", ""), ("HashiCorp", ""), ("Temporal", ""), ("Retool", ""),
    ("Render", ""), ("Fly.io", ""), ("Supabase", ""), ("Neon", ""),
    ("PlanetScale", ""), ("ClickHouse", ""), ("SingleStore", ""),
    ("Confluent", ""), ("Snowflake", ""), ("Databricks", ""), ("dbt Labs", ""),
    ("Fivetran", ""), ("Airbyte", ""), ("Astronomer", ""), ("Prefect", ""),
    ("Dagster Labs", ""), ("Grafana Labs", ""), ("Sentry", ""),
    ("Honeycomb", ""), ("Chronosphere", ""), ("PagerDuty", ""),
    ("LaunchDarkly", ""), ("Harness", ""), ("Pulumi", ""), ("Redis", ""),
    ("MongoDB", ""), ("Elastic", ""), ("Datadog", ""), ("Twilio", ""),
    # --- Product & SaaS ---
    ("Notion", ""), ("Linear", ""), ("Figma", ""), ("Canva", ""),
    ("Miro", ""), ("Airtable", ""), ("Zapier", ""), ("Webflow", ""),
    ("Framer", ""), ("Calendly", ""), ("Grammarly", ""), ("Asana", ""),
    ("ClickUp", ""), ("Dropbox", ""), ("Box", ""), ("Celonis", ""),
    ("Amplitude", ""), ("Mixpanel", ""), ("Statsig", ""), ("Braze", ""),
    ("Klaviyo", ""), ("Intercom", ""), ("HubSpot", ""), ("Squarespace", ""),
    ("Etsy", ""), ("DoorDash", ""), ("Lyft", ""), ("Airbnb", ""),
    ("Pinterest", ""), ("Reddit", ""), ("Discord", ""), ("Roblox", ""),
    ("Twitch", ""), ("Duolingo", ""), ("Coursera", ""), ("Quizlet", ""),
    ("Instacart", ""), ("Attentive", ""), ("Samsara", ""), ("Flexport", ""),
    # --- Fintech ---
    ("Stripe", ""), ("Plaid", ""), ("Brex", ""), ("Ramp", ""),
    ("Mercury", ""), ("Deel", ""), ("Rippling", ""), ("Gusto", ""),
    ("Carta", ""), ("Navan", ""), ("Affirm", ""), ("Chime", ""),
    ("Robinhood", ""), ("Coinbase", ""), ("Marqeta", ""),
    ("Modern Treasury", ""), ("Alloy", ""), ("Persona", ""),
    ("Stytch", ""), ("WorkOS", ""), ("Clerk", ""), ("Adyen", ""),
    # --- Security ---
    ("Cloudflare", ""), ("Okta", ""), ("Snyk", ""), ("Wiz", ""),
    ("SentinelOne", ""), ("Tailscale", ""), ("Vanta", ""), ("Drata", ""),
    ("Abnormal Security", ""), ("Chainguard", ""), ("Semgrep", ""),
    ("1Password", ""), ("Palantir", ""),
    # --- Quant/trading (strong sponsors, new-grad friendly) ---
    ("Two Sigma", "https://boards.greenhouse.io/twosigma"),
    ("Hudson River Trading", "https://boards.greenhouse.io/wehrtyou"),
    ("Jump Trading", "https://boards.greenhouse.io/jumptrading"),
    ("DRW", "https://boards.greenhouse.io/drweng"),
    ("IMC Trading", "https://boards.greenhouse.io/imc"),
    ("Optiver", "https://boards.greenhouse.io/optiverus"),
    ("Voleon", ""),
    # --- Large enterprises on Workday (URL required for detection) ---
    ("Nvidia", "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"),
    ("Salesforce", "https://salesforce.wd12.myworkdayjobs.com/External_Career_Site"),
    ("Adobe", "https://adobe.wd5.myworkdayjobs.com/external_experienced"),
    ("Intel", "https://intel.wd1.myworkdayjobs.com/External"),
    ("AMD", "https://amd.wd1.myworkdayjobs.com/External"),
    ("Qualcomm", "https://qualcomm.wd5.myworkdayjobs.com/External"),
    ("Zoom", "https://zoom.wd5.myworkdayjobs.com/Zoom"),
    ("Workday", "https://workday.wd5.myworkdayjobs.com/Workday"),
    ("CrowdStrike", "https://crowdstrike.wd5.myworkdayjobs.com/crowdstrikecareers"),
    ("Dell Technologies", "https://dell.wd1.myworkdayjobs.com/External"),
    ("ServiceNow", "https://careers.smartrecruiters.com/ServiceNow"),
    ("Palo Alto Networks", "https://careers.smartrecruiters.com/PaloAltoNetworks"),
    # --- More applied-AI / ML startups ---
    ("Adept AI", ""), ("Contextual AI", ""), ("Cresta", ""), ("Moveworks", ""),
    ("Synthesia", ""), ("Descript", ""), ("AssemblyAI", ""), ("Deepgram", ""),
    ("Hume AI", ""), ("Stability AI", ""), ("Lightning AI", ""), ("Predibase", ""),
    ("Arize AI", ""), ("Fiddler AI", ""), ("Humanloop", ""), ("LlamaIndex", ""),
    ("Twelve Labs", ""), ("Poolside", ""), ("Augment Code", ""), ("Codeium", ""),
    ("Sourcegraph", ""), ("Zed Industries", ""), ("Imbue", ""), ("Typeface", ""),
    ("Jasper", ""), ("Decagon", ""), ("Cognition Labs", ""), ("Mercor", ""),
    ("EvenUp", ""), ("Abridge", ""), ("OpenEvidence", ""), ("Ideogram", ""),
    # --- More dev tools / data / infra ---
    ("Railway", ""), ("Northflank", ""), ("Gitpod", ""), ("Depot", ""),
    ("Turso", ""), ("Xata", ""), ("Convex", ""), ("Appwrite", ""),
    ("Hasura", ""), ("Apollo GraphQL", ""), ("Inngest", ""), ("Trigger.dev", ""),
    ("Resend", ""), ("Liveblocks", ""), ("Ably", ""), ("Novu", ""),
    ("Hightouch", ""), ("RudderStack", ""), ("Materialize", ""), ("Tinybird", ""),
    ("Timescale", ""), ("Cockroach Labs", ""), ("EdgeDB", ""), ("WarpStream", ""),
    ("Redpanda", ""), ("Hex Technologies", ""), ("Sigma Computing", ""),
    ("Metabase", ""), ("Preset", ""), ("Estuary", ""), ("Tecton", ""),
    # --- More SaaS / product / HR / ops ---
    ("Coda", ""), ("Lattice", ""), ("Culture Amp", ""), ("15Five", ""),
    ("HiBob", ""), ("Oyster HR", ""), ("Metaview", ""), ("Pave", ""),
    ("Assembled", ""), ("Sprig", ""), ("Dovetail", ""), ("Pendo", ""),
    ("Productboard", ""), ("Shortcut", ""), ("Superhuman", ""), ("Loom", ""),
    ("Verkada", ""), ("Ironclad", ""),
    # --- More fintech / payments / risk ---
    ("Wise", ""), ("Lithic", ""), ("Highnote", ""), ("Moov", ""),
    ("Finix", ""), ("Airwallex", ""), ("Sardine", ""), ("Unit21", ""),
    ("Middesk", ""), ("Truework", ""), ("Argyle", ""), ("Method Financial", ""),
    ("Sila", ""), ("Treasury Prime", ""), ("Mercoa", ""), ("Checkout.com", ""),
    ("Klarna", ""),
    # --- Healthtech ---
    ("Cedar", ""), ("Oscar Health", ""), ("Hims & Hers", ""),
    ("Cityblock Health", ""), ("Carbon Health", ""), ("Maven Clinic", ""),
    ("Spring Health", ""), ("Lyra Health", ""), ("Headway", ""), ("Tempus", ""),
    ("Flatiron Health", ""), ("Komodo Health", ""), ("Cohere Health", ""),
    ("Suki AI", ""), ("Garner Health", ""), ("Sword Health", ""),
    ("Hinge Health", ""), ("Devoted Health", ""), ("Clipboard Health", ""),
    ("Aledade", ""), ("Included Health", ""), ("Commure", ""),
    # --- Commerce / logistics / marketplaces ---
    ("Faire", ""), ("Whatnot", ""), ("StockX", ""), ("Poshmark", ""),
    ("ThredUp", ""), ("Gopuff", ""), ("Toast", ""), ("Olo", ""),
    ("Shippo", ""), ("ShipBob", ""), ("Stord", ""), ("Project44", ""),
    ("FourKites", ""),
    # --- More security ---
    ("Material Security", ""), ("Sublime Security", ""), ("Endor Labs", ""),
    ("Aikido Security", ""), ("Nightfall AI", ""), ("Cyera", ""),
    ("GitGuardian", ""), ("Sysdig", ""), ("Aqua Security", ""),
    ("Orca Security", ""), ("JupiterOne", ""),
]

BOARD_URLS = {
    "greenhouse": "https://boards.greenhouse.io/{slug}",
    "lever": "https://jobs.lever.co/{slug}",
    "ashby": "https://jobs.ashbyhq.com/{slug}",
    "smartrecruiters": "https://careers.smartrecruiters.com/{slug}",
    "workable": "https://apply.workable.com/{slug}",
    "recruitee": "https://{slug}.recruitee.com",
}


def board_url(row: CompanyRow) -> str:
    if row.ats == "workday":
        tenant, wd, site = row.slug.split("/")
        return f"https://{tenant}.{wd}.myworkdayjobs.com/{site}"
    return BOARD_URLS.get(row.ats, "").format(slug=row.slug)


def verify_workday(client: httpx.Client, row: CompanyRow) -> bool:
    tenant, wd, site = row.slug.split("/")
    try:
        resp = client.post(
            f"https://{tenant}.{wd}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs",
            json={"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""},
        )
        return resp.status_code == 200 and "jobPostings" in resp.json()
    except (httpx.HTTPError, ValueError):
        return False


def main() -> None:
    apply = "--apply" in sys.argv
    client = httpx.Client(timeout=12, follow_redirects=True,
                          headers={"User-Agent": "Mozilla/5.0 (compatible; JobPilot)"})

    resolved: list[CompanyRow] = []
    for name, url in CANDIDATES:
        row = CompanyRow(row=0, company=name, careers_url=url)
        resolver.resolve(row, client)
        if row.ats == "workday" and row.status == "active" and not verify_workday(client, row):
            row.ats, row.slug, row.status = "", "", "unsupported"
            row.notes = "workday board did not verify"
        flag = "OK " if row.status == "active" else "-- "
        print(f"{flag}{name:<24} {row.ats:<16} {row.slug}")
        resolved.append(row)

    active = [r for r in resolved if r.status == "active"]
    print(f"\n{len(active)} of {len(CANDIDATES)} candidates resolved to a pollable board")
    by_ats: dict[str, int] = {}
    for r in active:
        by_ats[r.ats] = by_ats.get(r.ats, 0) + 1
    print("  " + ", ".join(f"{k}: {v}" for k, v in sorted(by_ats.items())))

    if not apply:
        print("\ndry run — pass --apply to append the active companies to the Sheet")
        return

    import os
    from pathlib import Path

    from jobpilot.config import Config
    from jobpilot.gauth import credentials
    from jobpilot import sheets

    profile = "private/profile.yaml" if Path("private/profile.yaml").exists() else "profile.yaml"
    cfg = Config.load(profile)
    creds = credentials()
    sid = os.environ.get("JOBPILOT_SPREADSHEET_ID") or cfg.sheet.spreadsheet_id
    if not sid:
        raise SystemExit("no spreadsheet id — set JOBPILOT_SPREADSHEET_ID or sheet.spreadsheet_id")
    existing = {d["Company"].strip().lower()
                for d in sheets.read_companies(creds, sid) if d["Company"].strip()}
    new_rows = [r for r in active if r.company.lower() not in existing]
    values = [[r.company, board_url(r), r.ats, r.slug, "active", "", "", ""]
              for r in new_rows]
    if values:
        svc = sheets._svc(creds)
        svc.spreadsheets().values().append(
            spreadsheetId=sid, range="Companies!A1", valueInputOption="RAW",
            insertDataOption="INSERT_ROWS", body={"values": values},
        ).execute()
    print(f"appended {len(values)} new companies ({len(active) - len(values)} already present)")


if __name__ == "__main__":
    main()
