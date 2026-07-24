# Auto-apply Answer Engine + Applications Queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Build the non-browser core of auto-apply: load the locked application profile, generate a per-job cover letter (PDF) and screening answers in the user's voice under the truthfulness + no-dash rules, model an `Applications` state machine in a Sheet tab, store evidence, and expose an Applications queue in the console. No form submission yet (that is Phase 3+, the ATS adapters) — this phase produces reviewable "application plans" and the answer engine they depend on.

**Architecture:** New `src/jobpilot/apply/` package: `profile.py` (locked-field loader + NY/Bay-Area selection), `answers.py` (cover letter + screening answers via Gemini, reusing `company_outreach.sanitize_text` and the LaTeX/Drive path), `plan.py` (ApplicationPlan model + status enum). New `Applications` Sheet tab (sheets.py). New console `/applications` view. Personal data stays in the private profile / Secret Manager; tests use synthetic data.

**Tech Stack:** Python 3.12, pydantic v2, google-genai (Vertex Gemini), google-api-python-client (Sheets/Drive), pdflatex (cover letter), Next.js UI.

This is Phase 2 of the auto-apply feature (spec: `docs/superpowers/specs/2026-07-24-auto-apply-design.md`). Phase 1 (portfolio knowledge graph) is merged. Phases 3-6 (ATS adapters, Workday, local fallback, full-auto) follow.

## Global Constraints

- Python 3.12; `from __future__ import annotations` at top of every new module.
- ruff select E4/E7/E9/F; clean imports.
- LLM only via `make_gemini_llm(cfg, schema=...)` (schema for structured answers) or `make_tailor_llm(cfg)` (free text). No new client code.
- **Truthfulness gate (all modes):** work authorization, sponsorship, numbers (years, GPA, dates, salary), and EEO answers come ONLY from the profile, never invented. A required question with no profile/knowledge basis is NOT guessed — it is flagged `needs_input`.
- **No dashes / no AI-tell** in every generated string: run `company_outreach.sanitize_text` as a post-filter; the prompt also forbids em/en dashes and AI-tell vocabulary. Voice: confident-not-perfect, honest, spoken, succinct (from the profile `voice` block).
- **Locked fields always win:** answers for name/phone/address/education/experience come verbatim from the profile, never from the LLM.
- Location: NY profile by default; Bay Area profile (address + resume) when the job location matches a Bay Area trigger token.
- Cover letter is ALWAYS rendered to PDF and stored in evidence.
- Length-aware: when a field limit is known, generate to fit; never hard-truncate mid-sentence (summarize gracefully; flag if a hard cut is unavoidable).
- Sheet-is-the-store; 45000-char cell cap; follow `ensure_*_tab` patterns.
- No personal data / real employer names in tracked tests — synthetic placeholders only.
- Commit as SampreethAvvari <spa9659@nyu.edu>, no Claude co-author trailer.

---

### Task 1: Application profile model + loader

**Files:**
- Create: `src/jobpilot/apply/__init__.py` (empty package marker)
- Create: `src/jobpilot/apply/profile.py`
- Modify: `src/jobpilot/config.py` (add optional `application` field to `Config`)
- Test: `tests/test_apply_profile.py`

**Interfaces:**
- Produces: pydantic models `Identity`, `LocationProfile`, `Eeo`, `Compensation`, `EducationItem`, `ExperienceItem`, `Voice`, `ApplicationProfile`; and `ApplicationProfile.for_location(job_location: str) -> ResolvedProfile` returning the chosen address + resume path + all locked fields. `Config.application: ApplicationProfile | None = None`.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd job-pilot && .venv/Scripts/python.exe -m pytest tests/test_apply_profile.py -q`
Expected: FAIL `ModuleNotFoundError: No module named 'jobpilot.apply'`

- [ ] **Step 3: Write minimal implementation**

Create `src/jobpilot/apply/__init__.py`:
```python
"""Auto-apply: locked profile, answer engine, application plans (Phase 2+)."""
```

Create `src/jobpilot/apply/profile.py`:
```python
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
```

Modify `src/jobpilot/config.py` — add the import and the optional field on `Config` (near the other optional sections):
```python
from jobpilot.apply.profile import ApplicationProfile
```
and inside `class Config(_Strict)`:
```python
    application: ApplicationProfile | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd job-pilot && .venv/Scripts/python.exe -m pytest tests/test_apply_profile.py tests/test_config.py -q`
Expected: PASS (new tests + existing config tests still green — the `application` field is optional so existing profiles validate unchanged).

- [ ] **Step 5: Commit**

```bash
git add src/jobpilot/apply/__init__.py src/jobpilot/apply/profile.py src/jobpilot/config.py tests/test_apply_profile.py
git commit -m "feat: locked application profile model, loader, NY/Bay-Area selection"
```

---

### Task 2: Salary + how-heard resolution helpers

**Files:**
- Modify: `src/jobpilot/apply/profile.py`
- Test: `tests/test_apply_profile.py`

**Interfaces:**
- Produces: `Compensation.salary_answer(jd_text: str, wants_number: bool) -> str`. If `wants_number` and the JD contains a salary range, echo a number inside that range; if `wants_number` and no JD range, use `fallback_range_usd` formatted (e.g. "$130,000 - $140,000" but WITHOUT a dash — use "$130,000 to $140,000"); if free-text allowed (`wants_number=False`), return `salary_prefer_text`.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_apply_profile.py
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
```

- [ ] **Step 2: Run to verify fail**

Run: `cd job-pilot && .venv/Scripts/python.exe -m pytest tests/test_apply_profile.py -q`
Expected: FAIL `AttributeError: 'Compensation' object has no attribute 'salary_answer'`

- [ ] **Step 3: Write minimal implementation**

Add to `Compensation` in `src/jobpilot/apply/profile.py`:
```python
    def salary_answer(self, jd_text: str, wants_number: bool) -> str:
        import re

        if not wants_number:
            return self.salary_prefer_text
        if self.use_jd_range_if_present:
            nums = re.findall(r"\$?\s*(\d{2,3}(?:,\d{3})|\d{5,6})", jd_text or "")
            vals = [int(n.replace(",", "")) for n in nums]
            vals = [v for v in vals if 40000 <= v <= 500000]
            if vals:
                lo = min(vals)
                return f"${lo:,}"
        lo, hi = self.fallback_range_usd[0], self.fallback_range_usd[1]
        return f"${lo:,} to ${hi:,}"
```

- [ ] **Step 4: Run to verify pass**

Run: `cd job-pilot && .venv/Scripts/python.exe -m pytest tests/test_apply_profile.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/jobpilot/apply/profile.py tests/test_apply_profile.py
git commit -m "feat: salary answer resolution (JD range, fallback, no dash)"
```

---

### Task 3: ApplicationPlan model + status machine

**Files:**
- Create: `src/jobpilot/apply/plan.py`
- Test: `tests/test_apply_plan.py`

**Interfaces:**
- Produces: `Question` (label, answer, required, char_limit, kind, screenshot), `ApplicationStatus` (Literal), `ApplicationPlan` (job_id, company, title, ats, location_key, cover_letter_pdf_url, questions, status, evidence_folder, notes), and `ApplicationPlan.next_status_after_fill() -> str` (returns `needs_input` if any required question is unanswered, else `needs_review`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_apply_plan.py
from __future__ import annotations

from jobpilot.apply import plan as pl


def _q(label, answer, required=True):
    return pl.Question(label=label, answer=answer, required=required)


def test_plan_needs_review_when_all_required_answered():
    p = pl.ApplicationPlan(job_id="j1", company="Acme", title="AIE", ats="greenhouse",
                           questions=[_q("Why us?", "Because I ship.")])
    assert p.next_status_after_fill() == "needs_review"


def test_plan_needs_input_when_required_unanswered():
    p = pl.ApplicationPlan(job_id="j1", company="Acme", title="AIE", ats="greenhouse",
                           questions=[_q("Security clearance?", ""), _q("Why us?", "x")])
    assert p.next_status_after_fill() == "needs_input"


def test_optional_blank_does_not_block():
    p = pl.ApplicationPlan(job_id="j1", company="Acme", title="AIE", ats="lever",
                           questions=[_q("Optional note", "", required=False)])
    assert p.next_status_after_fill() == "needs_review"


def test_plan_json_roundtrips():
    p = pl.ApplicationPlan(job_id="j1", company="Acme", title="AIE", ats="ashby",
                           questions=[_q("Q", "A")])
    assert pl.ApplicationPlan.model_validate_json(p.model_dump_json()).job_id == "j1"
```

- [ ] **Step 2: Run to verify fail**

Run: `cd job-pilot && .venv/Scripts/python.exe -m pytest tests/test_apply_plan.py -q`
Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

Create `src/jobpilot/apply/plan.py`:
```python
"""ApplicationPlan: the reviewable artifact of a fill. Serialized to plan.json in
Drive and mirrored to the Applications Sheet tab. Spec: 2026-07-24-auto-apply-design.md
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ApplicationStatus = Literal[
    "queued", "filling", "needs_review", "needs_input", "approved", "submitting",
    "submitted", "failed", "captcha_blocked", "manual_required", "check_email",
]


class Question(BaseModel):
    label: str
    answer: str = ""
    required: bool = True
    char_limit: int | None = None
    kind: str = "text"  # text | textarea | select | file | eeo | boolean
    screenshot: str = ""  # Drive/URL of the per-question screenshot


class ApplicationPlan(BaseModel):
    job_id: str
    company: str
    title: str
    ats: str
    location_key: str = "ny"
    cover_letter_pdf_url: str = ""
    questions: list[Question] = Field(default_factory=list)
    status: ApplicationStatus = "queued"
    evidence_folder: str = ""
    notes: list[str] = Field(default_factory=list)

    def next_status_after_fill(self) -> ApplicationStatus:
        if any(q.required and not q.answer.strip() for q in self.questions):
            return "needs_input"
        return "needs_review"
```

- [ ] **Step 4: Run to verify pass**

Run: `cd job-pilot && .venv/Scripts/python.exe -m pytest tests/test_apply_plan.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/jobpilot/apply/plan.py tests/test_apply_plan.py
git commit -m "feat: ApplicationPlan model and fill-status machine"
```

---

### Task 4: Screening answer engine

**Files:**
- Create: `src/jobpilot/prompts/apply_answer_v1.txt`
- Create: `src/jobpilot/apply/answers.py`
- Test: `tests/test_apply_answers.py`

**Interfaces:**
- Consumes: `make_tailor_llm(cfg)` (free-text LLM); `company_outreach.sanitize_text`; `ResolvedProfile`; portfolio knowledge pack (optional grounding string).
- Produces: `answer_question(q: Question, jd: str, profile: ResolvedProfile, knowledge: str, llm) -> str`. Deterministic locked answers (auth, sponsorship, EEO, salary, education/experience recap, how-heard) are resolved WITHOUT the LLM; only open-ended screeners call the LLM. All LLM output passes `sanitize_text`. Length-aware: if `q.char_limit`, the prompt is told the limit and the result is checked (if over, one retry asking to shorten, else a graceful sentence-boundary trim, and a note is appended).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_apply_answers.py
from __future__ import annotations

from jobpilot.apply import answers as an
from jobpilot.apply import plan as pl
from jobpilot.apply import profile as ap
from tests.test_apply_profile import _sample


def _resolved():
    return _sample().for_location("New York, NY")


def test_sponsorship_answered_from_profile_not_llm():
    q = pl.Question(label="Will you now or in the future require sponsorship?",
                    kind="boolean")
    out = an.answer_question(q, "jd", _resolved(), "", llm=lambda p: "SHOULD NOT BE USED")
    assert out.lower().startswith("yes")  # requires_sponsorship True


def test_work_auth_answered_from_profile():
    q = pl.Question(label="Are you authorized to work in the US?", kind="boolean")
    out = an.answer_question(q, "jd", _resolved(), "", llm=lambda p: "no")
    assert out.lower().startswith("yes")


def test_open_ended_uses_llm_and_sanitizes_dashes():
    q = pl.Question(label="Why do you want to work here?", kind="textarea")
    out = an.answer_question(q, "We build AI infra", _resolved(),
                             "Jane shipped RAG systems",
                             llm=lambda p: "I love infra — especially RAG.")
    assert "—" not in out and "-" not in out.replace("F-1", "")  # sanitized
    assert out  # non-empty


def test_char_limit_trims_gracefully_without_midsentence_cut():
    q = pl.Question(label="One line pitch", kind="textarea", char_limit=40)
    long = "I ship production ML. I love hard problems. I move fast."
    out = an.answer_question(q, "jd", _resolved(), "", llm=lambda p: long)
    assert len(out) <= 40
    assert out.endswith(".") or out.endswith("ML.") or not out.endswith(" ")
```

- [ ] **Step 2: Run to verify fail**

Run: `cd job-pilot && .venv/Scripts/python.exe -m pytest tests/test_apply_answers.py -q`
Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

Create `src/jobpilot/prompts/apply_answer_v1.txt`:
```
You are answering ONE job-application screening question as the candidate, in first
person. Be honest and specific. Sell someone who ships and figures things out, not
someone who claims to know everything. Concessions are fine ("I have not used X in
production, but ...").

STRICT STYLE:
- Natural spoken language, not stiff writing. Succinct.
- No em dashes or en dashes. No AI-tell words (delve, realm, seamless, robust,
  leverage, tapestry, "not just X but Y").
- Do not invent facts, numbers, employers, or links. Use only what is grounded below.
{limit_line}

CANDIDATE BACKGROUND (ground truth):
{knowledge}

JOB DESCRIPTION:
{jd}

QUESTION:
{question}

Answer:
```

Create `src/jobpilot/apply/answers.py`:
```python
"""Answer engine: locked deterministic answers + LLM open-ended screeners, all
run through the no-dash sanitizer. Cover letter lives in cover.py (Task 5)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from jobpilot.apply.plan import Question
from jobpilot.apply.profile import ResolvedProfile
from jobpilot.company_outreach import sanitize_text

PROMPT = Path(__file__).parent.parent / "prompts" / "apply_answer_v1.txt"

_YES = "Yes"
_NO = "No"


def _is(label: str, *needles: str) -> bool:
    lo = label.lower()
    return any(n in lo for n in needles)


def _locked_answer(q: Question, profile: ResolvedProfile, jd: str) -> str | None:
    """Return a verbatim locked answer, or None if this is an open-ended screener."""
    lbl = q.label
    idn = profile.identity
    if _is(lbl, "sponsor"):
        return _YES if idn.requires_sponsorship else _NO
    if _is(lbl, "authorized to work", "legally authorized", "work authorization"):
        return idn.work_authorization if _is(lbl, "status") else (
            _YES if idn.authorized_to_work_us else _NO)
    if _is(lbl, "18 years", "over 18", "at least 18"):
        return _YES if idn.over_18 else _NO
    if _is(lbl, "gender"):
        return profile.eeo.gender
    if _is(lbl, "race", "ethnicity"):
        return profile.eeo.race_ethnicity
    if _is(lbl, "veteran"):
        return profile.eeo.veteran_status
    if _is(lbl, "disab"):
        return profile.eeo.disability_status
    if _is(lbl, "hispanic", "latino"):
        return _YES if profile.eeo.hispanic_latino else _NO
    if _is(lbl, "salary", "compensation expectation", "expected pay", "desired salary"):
        wants_number = q.kind in ("text", "number") or _is(lbl, "number", "amount")
        return profile.compensation.salary_answer(jd, wants_number)
    if _is(lbl, "how did you hear", "how you heard", "referral source"):
        return profile.compensation.how_did_you_hear
    if _is(lbl, "relocat"):
        return _YES if profile.compensation.willing_to_relocate else _NO
    if _is(lbl, "start date", "earliest start", "available to start"):
        return profile.compensation.earliest_start
    if _is(lbl, "notice period"):
        return profile.compensation.notice_period
    return None


def _graceful_trim(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit]
    for sep in (". ", "! ", "? "):
        i = cut.rfind(sep)
        if i >= limit // 2:
            return cut[: i + 1].strip()
    i = cut.rfind(" ")
    return (cut[:i] if i > 0 else cut).strip()


def answer_question(q: Question, jd: str, profile: ResolvedProfile, knowledge: str,
                    llm: Callable[[str], str]) -> str:
    locked = _locked_answer(q, profile, jd)
    if locked is not None:
        return locked
    limit_line = (f"- Keep the answer under {q.char_limit} characters, complete and "
                  "self-contained." if q.char_limit else "")
    prompt = PROMPT.read_text(encoding="utf-8").format(
        limit_line=limit_line, knowledge=knowledge or "(no extra background)",
        jd=(jd or "")[:4000], question=q.label)
    try:
        raw = llm(prompt)
    except Exception:  # noqa: BLE001 — no answer beats a wrong/injected one
        return ""
    out = sanitize_text(raw).strip()
    if q.char_limit and len(out) > q.char_limit:
        try:
            shorter = sanitize_text(llm(prompt + f"\n\nToo long. Rewrite in under "
                                        f"{q.char_limit} characters.")).strip()
            if len(shorter) <= q.char_limit:
                return shorter
        except Exception:  # noqa: BLE001
            pass
        return _graceful_trim(out, q.char_limit)
    return out
```

Note: confirm `company_outreach.sanitize_text` collapses `" - "` and em/en dashes (it does — `_DASHES` map + the `" - "` clause rule). The test `test_open_ended_uses_llm_and_sanitizes_dashes` asserts no bare dash survives; if `sanitize_text` leaves a standalone hyphen that is not clause punctuation, adjust the assertion to check only em/en dashes and `" - "`, matching what the shared sanitizer guarantees — do NOT weaken the sanitizer's real contract.

- [ ] **Step 4: Run to verify pass**

Run: `cd job-pilot && .venv/Scripts/python.exe -m pytest tests/test_apply_answers.py -q`
Expected: PASS. If the dash assertion is stricter than `sanitize_text`'s guarantee, align the test to the sanitizer's real behavior (em/en dashes and `" - "` clause dashes removed), keeping a real assertion.

- [ ] **Step 5: Commit**

```bash
git add src/jobpilot/prompts/apply_answer_v1.txt src/jobpilot/apply/answers.py tests/test_apply_answers.py
git commit -m "feat: screening answer engine (locked + LLM, sanitized, length-aware)"
```

---

### Task 5: Cover letter generation (PDF)

**Files:**
- Create: `src/jobpilot/prompts/apply_cover_v1.txt`
- Create: `src/jobpilot/apply/cover.py`
- Test: `tests/test_apply_cover.py`

**Interfaces:**
- Consumes: `make_tailor_llm(cfg)`; `company_outreach.sanitize_text` + its `_latex_escape` + LaTeX cover-letter rendering path (reuse — do NOT duplicate LaTeX); `ResolvedProfile`; knowledge string.
- Produces: `cover_letter_text(company, title, jd, profile, knowledge, llm) -> str` (sanitized, voice-driven, no dashes) and `render_cover_pdf(text, profile) -> bytes` (reuse `company_outreach`'s LaTeX build). Split text-gen (unit-testable) from PDF render (needs pdflatex).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_apply_cover.py
from __future__ import annotations

from jobpilot.apply import cover
from tests.test_apply_profile import _sample


def test_cover_text_is_sanitized_and_grounded():
    text = cover.cover_letter_text(
        "Acme", "AI Engineer", "We build RAG infra", _sample().for_location("NY"),
        "Jane shipped a RAG platform with citations",
        llm=lambda p: "I would love to help — I shipped RAG at Acme Robotics.")
    assert "—" not in text
    assert text.strip()


def test_cover_text_degrades_to_empty_on_llm_error():
    def boom(p):
        raise RuntimeError("no llm")
    text = cover.cover_letter_text("Acme", "AIE", "jd", _sample().for_location("NY"),
                                   "", llm=boom)
    assert text == ""
```

- [ ] **Step 2: Run to verify fail**

Run: `cd job-pilot && .venv/Scripts/python.exe -m pytest tests/test_apply_cover.py -q`
Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

First READ `src/jobpilot/company_outreach.py` to find the exact LaTeX cover-letter render helper (the code that turns sanitized paragraphs into a PDF via `_latex_escape` + `latexpdf`). Reuse that function for `render_cover_pdf`; do not reimplement LaTeX.

Create `src/jobpilot/prompts/apply_cover_v1.txt` (voice contract + no-invention rule + "3 short paragraphs, spoken, no dashes, no AI-tell", grounded in the knowledge + JD).

Create `src/jobpilot/apply/cover.py` with `cover_letter_text` (calls llm, `sanitize_text`, returns "" on error) and `render_cover_pdf` (delegates to the reused company_outreach LaTeX builder). Keep the two separate so text is unit-testable without pdflatex.

- [ ] **Step 4: Run to verify pass**

Run: `cd job-pilot && .venv/Scripts/python.exe -m pytest tests/test_apply_cover.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/jobpilot/prompts/apply_cover_v1.txt src/jobpilot/apply/cover.py tests/test_apply_cover.py
git commit -m "feat: cover letter text generation (voice, sanitized) + PDF render reuse"
```

---

### Task 6: Applications Sheet tab

**Files:**
- Modify: `src/jobpilot/sheets.py`
- Test: `tests/test_apply_sheet.py`

**Interfaces:**
- Produces: `ensure_applications_tab(creds, sid)`, `upsert_application(creds, sid, plan_dict)`, `read_applications(creds, sid) -> list[dict]`. Tab `Applications`, headers `["Job ID","Company","Title","ATS","Status","Location","Cover letter","Evidence","Questions","Updated","Notes"]` (Questions + plan detail stored as JSON in a cell, capped 45000). Upsert keys on Job ID (update the existing row or append). Follow the existing `ensure_*_tab` + values-API pattern.

- [ ] **Step 1-5:** TDD mirroring Task 5 of Phase 1 (the PortfolioGraph tab): a monkeypatched `_svc` fake proving an upsert-then-read roundtrip and that a second upsert on the same Job ID updates rather than appends. Commit `feat: Applications sheet tab (upsert by job id)`.

(Full test + code follow the identical fake-`_svc` structure used in `tests/test_portfolio_graph.py::test_sheet_storage_roundtrip`; the reviewer of that task confirmed the pattern. Model `read_applications` on `read_rows` and `upsert_application` on a read-existing-then-update-or-append flow like `companies.merge_into_sources`.)

---

### Task 7: Console Applications view (read-only queue)

**Files:**
- Create: `ui/src/app/api/applications/route.ts` (GET reads the Applications tab via the Sheets lib)
- Create: `ui/src/app/applications/page.tsx` + `ui/src/components/applications-view.tsx`
- Modify: `ui/src/components/nav.tsx`, `ui/src/components/mobile-nav.tsx` (add "Applications" entry)

**Interfaces:**
- Consumes: the Applications tab (via the same Google auth lib the other API routes use — inspect `ui/src/lib/` for the sheets read helper the jobs route uses).
- Produces: an `/applications` page rendering each application as a card (company, title, status badge, cover-letter link, per-question answers with screenshots when present, evidence link). Read-only in this phase (Approve/submit + Auto-apply button come with the ATS adapters in Phase 3). Use the shared Card/Badge/Button primitives; no dashes in copy; status badge tone by status.

- [ ] **Steps:** Build the GET route (mirror `api/jobs/route.ts`), the view (mirror `companies-view.tsx` card style), register nav in both files (mirror the Phase 1 `/knowledge` entry). Verify `cd ui && npx tsc --noEmit && npm run lint && npm run build`. Commit `feat: read-only Applications queue view + nav`.

---

### Task 8: Fill orchestrator (no browser) — assemble a plan from a job

**Files:**
- Create: `src/jobpilot/apply/engine.py`
- Test: `tests/test_apply_engine.py`

**Interfaces:**
- Consumes: `profile.ApplicationProfile.for_location`, `answers.answer_question`, `cover.cover_letter_text`, the portfolio knowledge pack (via `sheets.read_knowledge`/`read_portfolio_graph`), `plan.ApplicationPlan`.
- Produces: `build_plan(job_row: dict, questions: list[Question], cfg, knowledge, llm, now) -> ApplicationPlan`. Given a job (company/title/location/JD) and a list of known form questions (the ATS adapters in Phase 3 will supply these; here they are passed in / tested with synthetic sets), it resolves the location profile, answers every question (locked + LLM), generates the cover letter text, applies the truthfulness gate (unanswerable required question → `needs_input`), and returns a populated `ApplicationPlan` with `status = next_status_after_fill()`. Pure logic, no browser, no Sheet writes (the caller persists).

- [ ] **Steps:** TDD — feed a synthetic job + a question set including a locked question (sponsorship), an open-ended one (why us), and an unanswerable required one (a bespoke question with `answer=""` the LLM returns empty for), assert the plan answers the lockable ones from profile, fills the open one, and lands `needs_input` because of the unanswerable required question. Assert no dashes in any answer. Commit `feat: browserless fill orchestrator building an ApplicationPlan`.

---

### Task 9: Full suite, lint, UI build, docs

**Files:** none (verification) + `docs/superpowers/specs/2026-07-24-auto-apply-design.md` (tick Phase 2 done in rollout).

- [ ] Run `cd job-pilot && .venv/Scripts/python.exe -m pytest -q` (all green).
- [ ] `.venv/Scripts/python.exe -m ruff check src/jobpilot/apply/ src/jobpilot/config.py src/jobpilot/sheets.py` (clean).
- [ ] `cd ui && npx tsc --noEmit && npm run lint && npm run build` (clean; `/applications` present).
- [ ] Commit any fixes.

---

## Notes for the implementer

- **No submission in this phase.** The engine builds a reviewable plan from a supplied question set. The ATS adapters (Phase 3) discover the real questions/limits from live forms and call `build_plan`, then a submit phase replays approved answers. Keep `engine.build_plan` browser-free.
- **Truthfulness gate is not optional.** Locked answers must come from the profile; the LLM path is only for open-ended screeners and always passes `sanitize_text`. A required question the engine cannot answer → `needs_input`, never a guess.
- **Owner prerequisite (not code):** the real `application:` block (staged in `private/application_profile_draft.yaml`) must be merged into the private profile and pushed to Secret Manager (`JOBPILOT_PROFILE`) before production runs use real data. Tests use synthetic data only.
- **Reuse, don't duplicate:** `sanitize_text` for dashes, the `company_outreach` LaTeX path for the cover PDF, the `ensure_*_tab` sheet pattern, the shared UI primitives.
