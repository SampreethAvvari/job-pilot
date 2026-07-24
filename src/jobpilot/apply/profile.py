"""Locked application profile: verbatim fields used on applications, plus
NY/Bay-Area selection. AI never edits anything here. Loaded from the private
profile (Secret Manager in prod). Spec: docs/superpowers/specs/2026-07-24-auto-apply-design.md
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Identity(_Model):
    legal_name: str
    display_name: str = ""
    email: str
    phone: str = ""
    linkedin: str = ""
    github: str = ""
    portfolio: str = ""
    work_authorization: str = ""
    requires_sponsorship: bool = True
    authorized_to_work_us: bool = True
    over_18: bool = True


class LocationProfile(_Model):
    street: str
    city: str
    state: str
    zip: str
    resume_path: str


class Locations(_Model):
    default: str = "ny"
    bay_area_triggers: list[str] = []
    profiles: dict[str, LocationProfile]


class Eeo(_Model):
    gender: str = "Prefer not to say"
    race_ethnicity: str = "Prefer not to say"
    hispanic_latino: bool = False
    veteran_status: str = "Not a protected veteran"
    disability_status: str = "No"


class Compensation(_Model):
    salary_prefer_text: str = "Open to discussion"
    use_jd_range_if_present: bool = True
    fallback_range_usd: list[int] = [130000, 140000]
    earliest_start: str = "Immediately"
    notice_period: str = "2 weeks"
    willing_to_relocate: bool = True
    work_mode: str = "Open"
    how_did_you_hear: str = "Company website"


class EducationItem(_Model):
    school: str
    degree: str
    major: str = ""
    start_date: str = ""
    end_date: str = ""
    gpa: str = ""
    location: str = ""


class ExperienceItem(_Model):
    company: str
    title: str
    location: str = ""
    start_date: str = ""
    end_date: str = ""
    current: bool = False
    description: str = ""


class Voice(_Model):
    persona: str = ""
    rules: list[str] = []


class ResolvedProfile(_Model):
    """Flattened locked fields for one job, with the chosen location + resume."""
    identity: Identity
    location_key: str
    street: str
    city: str
    state: str
    zip: str
    resume_path: str
    eeo: Eeo
    compensation: Compensation
    education: list[EducationItem]
    experience: list[ExperienceItem]


class ApplicationProfile(_Model):
    identity: Identity
    locations: Locations
    eeo: Eeo = Eeo()
    compensation: Compensation = Compensation()
    education: list[EducationItem] = []
    experience: list[ExperienceItem] = []
    voice: Voice = Voice()

    def _pick_location(self, job_location: str) -> str:
        loc = (job_location or "").lower()
        if any(t.lower() in loc for t in self.locations.bay_area_triggers):
            return "bay_area"
        return self.locations.default

    def for_location(self, job_location: str) -> ResolvedProfile:
        key = self._pick_location(job_location)
        prof = self.locations.profiles.get(key) or self.locations.profiles[
            self.locations.default]
        return ResolvedProfile(
            identity=self.identity, location_key=key, street=prof.street,
            city=prof.city, state=prof.state, zip=prof.zip,
            resume_path=prof.resume_path, eeo=self.eeo,
            compensation=self.compensation, education=self.education,
            experience=self.experience)
