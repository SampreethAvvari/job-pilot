// Client-safe types and constants (no googleapis imports here).

// Must mirror src/jobpilot/sheets.py HEADERS exactly (columns A..S).
export const HEADERS = [
  "Date found", "Job ID", "Title", "Company", "Location", "Remote", "Posted",
  "Posted age", "URL", "Source", "Fit", "Why", "Sponsorship", "Resume variant",
  "Status", "Notes", "Applied date", "Last reply", "Reply class",
  "Tailored resume", "Cover letter", "JD keywords", "JD excerpt",
  "Contact", "Draft", "Find people", "Role", "Resume ATS",
] as const;

export const ROLES = ["FDE", "AIE", "MLE", "DE", "DS", "SWE", "Other"] as const;
// The four master resumes a job can be matched to (scorer's resume_variant).
export const RESUME_VARIANTS = ["FDE", "AIE", "MLE", "SDE"] as const;

// 0-based column index -> A1 letters (0->A, 25->Z, 26->AA).
export function colLetter(idx: number): string {
  let letters = "";
  let n = idx + 1;
  while (n) {
    const rem = (n - 1) % 26;
    letters = String.fromCharCode(65 + rem) + letters;
    n = Math.floor((n - 1) / 26);
  }
  return letters;
}

export const STATUSES = [
  "New", "Applied", "Outreach sent", "Response", "Interview", "Offer", "Rejected",
  "Dismissed",
] as const;

export type Job = {
  row: number;
  dateFound: string;
  id: string;
  title: string;
  company: string;
  location: string;
  remote: string;
  posted: string;
  postedAge: string;
  url: string;
  source: string;
  fit: number | null;
  why: string;
  sponsorship: string;
  resumeVariant: string;
  status: string;
  notes: string;
  appliedDate: string;
  lastReply: string;
  replyClass: string;
  tailoredResume: string;
  coverLetter: string;
  jdKeywords: string;
  contact: string;
  draft: string;
  findPeople: string;
  role: string;
  resumeAts: string;
};

// Outreach tab (columns A-M — keep in sync with sheets.py OUTREACH_HEADERS)
export type Outreach = {
  row: number;
  searchedAt: string;
  company: string;
  domain: string;
  variant: string;
  variantReason: string;
  subject: string;
  guessedEmails: string;
  draft: string;
  resume: string; // master resume Drive file id for the chosen variant
  coverLetter: string; // "yes" | "no"
  status: string;
  notes: string;
  peopleFound: string; // Hunter contacts: "Name (role) <email> 95%; ..."
};

// Companies watchlist tab (columns A-H — keep in sync with sheets.py COMPANIES_HEADERS)
export type Company = {
  row: number;
  company: string;
  careersUrl: string;
  ats: string;
  slug: string;
  status: string;
  lastChecked: string;
  jobsLastFetch: string;
  notes: string;
};
