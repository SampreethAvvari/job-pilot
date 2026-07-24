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
