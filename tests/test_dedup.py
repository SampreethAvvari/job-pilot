from jobpilot.dedup import filter_new, job_id
from jobpilot.models import Posting


def make(title="ML Engineer", company="Acme", location="NYC", source="greenhouse", url="u"):
    return Posting(title=title, company=company, location=location, source=source, url=url)


def test_id_stable_across_formatting():
    assert job_id(make(company="Acme, Inc.")) == job_id(make(company="acme inc"))


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
