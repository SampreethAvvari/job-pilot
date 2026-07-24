import { sheetsClient, SPREADSHEET_ID } from "./google";
import type { Application, ApplicationQuestion } from "./types";

export { APPLICATION_STATUSES, type Application, type ApplicationQuestion } from "./types";

function parseQuestions(raw: string): ApplicationQuestion[] {
  if (!raw) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.map((q) => {
      const r = (q ?? {}) as Record<string, unknown>;
      return {
        label: typeof r.label === "string" ? r.label : "",
        answer: typeof r.answer === "string" ? r.answer : "",
        required: Boolean(r.required),
        charLimit: typeof r.char_limit === "number" ? r.char_limit : null,
        kind: typeof r.kind === "string" ? r.kind : "text",
        screenshot: typeof r.screenshot === "string" ? r.screenshot : "",
      };
    });
  } catch {
    // Malformed JSON in the cell degrades to no questions rather than a 500.
    return [];
  }
}

function parseNotes(raw: string): string[] {
  if (!raw) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.map((n) => String(n)) : [];
  } catch {
    return [];
  }
}

export async function readApplications(): Promise<Application[]> {
  const res = await sheetsClient().spreadsheets.values.get({
    spreadsheetId: SPREADSHEET_ID,
    range: "Applications!A2:K",
  });
  return (res.data.values ?? [])
    .map((v, i) => {
      const g = (j: number) => (v[j] as string) ?? "";
      return {
        row: i + 2,
        jobId: g(0),
        company: g(1),
        title: g(2),
        ats: g(3),
        status: g(4),
        location: g(5),
        coverLetter: g(6),
        evidence: g(7),
        questions: parseQuestions(g(8)),
        updated: g(9),
        notes: parseNotes(g(10)),
      };
    })
    .filter((a) => a.jobId);
}
