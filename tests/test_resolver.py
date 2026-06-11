import httpx

from jobpilot import resolver
from jobpilot.companies import CompanyRow


def test_match_url_patterns():
    cases = {
        "https://boards.greenhouse.io/stripe": ("greenhouse", "stripe"),
        "https://job-boards.greenhouse.io/figma/jobs/123": ("greenhouse", "figma"),
        "https://boards.greenhouse.io/embed/job_board?for=gusto": ("greenhouse", "gusto"),
        "https://jobs.lever.co/palantir": ("lever", "palantir"),
        "https://jobs.eu.lever.co/n26": ("lever", "n26"),
        "https://jobs.ashbyhq.com/openai": ("ashby", "openai"),
        "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite":
            ("workday", "nvidia/wd5/NVIDIAExternalCareerSite"),
        "https://salesforce.wd12.myworkdayjobs.com/en-US/External_Career_Site":
            ("workday", "salesforce/wd12/External_Career_Site"),
        "https://careers.smartrecruiters.com/Visa": ("smartrecruiters", "Visa"),
        "https://apply.workable.com/acme-inc/": ("workable", "acme-inc"),
        "https://acme.recruitee.com/": ("recruitee", "acme"),
    }
    for url, expected in cases.items():
        assert resolver.match_url(url) == expected, url
    assert resolver.match_url("https://www.example.com/careers") is None


def test_slug_candidates():
    assert resolver.slug_candidates("Scale AI") == ["scaleai", "scale-ai", "scale"]
    assert resolver.slug_candidates("Stripe") == ["stripe"]


def test_resolve_from_careers_url_no_http():
    row = CompanyRow(row=2, company="Stripe",
                     careers_url="https://boards.greenhouse.io/stripe")
    resolver.resolve(row, httpx.Client())  # URL match needs no requests
    assert (row.ats, row.slug, row.status, row.dirty) == \
        ("greenhouse", "stripe", "active", True)


def test_resolve_by_probe(httpx_mock):
    httpx_mock.add_response(
        url="https://boards-api.greenhouse.io/v1/boards/stripe/jobs",
        json={"jobs": []},
    )
    row = CompanyRow(row=2, company="Stripe")
    resolver.resolve(row, httpx.Client())
    assert (row.ats, row.slug, row.status) == ("greenhouse", "stripe", "active")


def test_resolve_unsupported(httpx_mock):
    httpx_mock.add_response(status_code=404, is_reusable=True)  # every probe 404s
    row = CompanyRow(row=2, company="Zzz Qqq")
    resolver.resolve(row, httpx.Client())
    assert row.status == "unsupported"
    assert row.dirty


def test_resolve_pending_skips_resolved_rows():
    rows = [CompanyRow(row=2, company="Done", ats="lever", slug="done",
                       status="active")]
    notes = resolver.resolve_pending(rows)
    assert notes == []
