from jobpilot.dedup import filter_new, job_id, key
from jobpilot.models import Posting


def make(title="ML Engineer", company="Acme", location="NYC", source="greenhouse", url="u"):
    return Posting(title=title, company=company, location=location, source=source, url=url)


def test_id_stable_across_formatting():
    assert job_id(make(company="Acme, Inc.")) == job_id(make(company="acme inc"))


def test_id_ignores_location():
    # boards list one role per metro — same company+title is the same job
    assert job_id(make(location="Austin, Travis County")) == job_id(make(location="US"))


def test_multi_city_posting_collapses_to_one_row():
    cities = ["Tumwater, Thurston County", "Bonnie, Utah County", "US", "Remote"]
    out = filter_new([make(location=c, source="adzuna") for c in cities], set())
    assert len(out) == 1


def test_key_matches_job_id():
    p = make()
    assert key(p.company, p.title) == job_id(p)


def test_known_ids_filtered():
    p = make()
    assert filter_new([p], {job_id(p)}) == []


def test_cross_source_duplicate_keeps_higher_fidelity():
    gh = make(source="greenhouse")
    hn = make(source="hn_hiring")
    li = make(source="linkedin")
    out = filter_new([hn, gh, li], set())
    assert len(out) == 1
    assert out[0].source == "linkedin"


def test_distinct_jobs_kept():
    out = filter_new([make(), make(title="Data Engineer")], set())
    assert len(out) == 2
    assert all(p.id for p in out)
