# tests/test_apply_profile.py
from __future__ import annotations

from jobpilot.apply import profile as ap


def _sample() -> ap.ApplicationProfile:
    return ap.ApplicationProfile.model_validate({
        "identity": {"legal_name": "Jane Q Candidate", "display_name": "Jane",
                     "email": "jane@example.edu", "phone": "5550001111",
                     "linkedin": "https://linkedin.test/in/jane",
                     "github": "https://github.test/jane",
                     "portfolio": "https://jane.example",
                     "work_authorization": "F-1 STEM OPT",
                     "requires_sponsorship": True, "authorized_to_work_us": True,
                     "over_18": True},
        "locations": {
            "default": "ny",
            "bay_area_triggers": ["san francisco", "sunnyvale", "san jose"],
            "profiles": {
                "ny": {"street": "1 Test St", "city": "Brooklyn", "state": "New York",
                       "zip": "11201", "resume_path": "out/ny.pdf"},
                "bay_area": {"street": "2 Demo Ct", "city": "Sunnyvale",
                             "state": "California", "zip": "94086",
                             "resume_path": "out/sfo.pdf"}}},
        "eeo": {"gender": "Prefer not to say", "race_ethnicity": "Prefer not to say",
                "hispanic_latino": False, "veteran_status": "Not a protected veteran",
                "disability_status": "No"},
        "compensation": {"salary_prefer_text": "Open to discussion",
                         "use_jd_range_if_present": True,
                         "fallback_range_usd": [130000, 140000],
                         "earliest_start": "Immediately", "notice_period": "2 weeks",
                         "willing_to_relocate": True, "work_mode": "Open",
                         "how_did_you_hear": "Company website"},
        "education": [{"school": "Test University", "degree": "MS", "major": "CE",
                       "start_date": "2023-08", "end_date": "2025-05", "gpa": "3.8/4",
                       "location": "Testville"}],
        "experience": [{"company": "Acme Robotics", "title": "AI Engineer",
                        "location": "Testville", "start_date": "2025-09",
                        "end_date": "Present", "current": True,
                        "description": "Shipped things."}],
        "voice": {"persona": "confident not perfect", "rules": ["no dashes"]},
    })


def test_default_location_is_ny():
    r = _sample().for_location("New York, NY")
    assert r.city == "Brooklyn" and r.resume_path == "out/ny.pdf"


def test_bay_area_job_switches_profile():
    r = _sample().for_location("Sunnyvale, CA")
    assert r.city == "Sunnyvale" and r.resume_path == "out/sfo.pdf"


def test_bay_area_match_is_case_insensitive_and_substring():
    r = _sample().for_location("Remote (San Francisco Bay Area)")
    assert r.city == "Sunnyvale"


def test_non_bay_us_city_stays_ny():
    r = _sample().for_location("Austin, TX")
    assert r.city == "Brooklyn"


def test_salary_free_text_prefers_negotiation_line():
    c = _sample().compensation
    assert c.salary_answer("comp is competitive", wants_number=False) == "Open to discussion"


def test_salary_number_uses_jd_range_when_present():
    c = _sample().compensation
    ans = c.salary_answer("Salary range: $150,000 - $170,000 per year", wants_number=True)
    assert "150,000" in ans or "170,000" in ans  # a number inside the JD range


def test_salary_number_falls_back_without_jd_range_and_has_no_dash():
    c = _sample().compensation
    ans = c.salary_answer("no numbers here", wants_number=True)
    assert "130,000" in ans and "140,000" in ans
    assert "-" not in ans and "—" not in ans  # no dash, uses "to"
