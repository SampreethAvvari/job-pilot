import { sheetsClient, SPREADSHEET_ID } from "./google";
import { colLetter, HEADERS, type Job } from "./types";

export { HEADERS, STATUSES, type Job } from "./types";

const LAST_COL = colLetter(HEADERS.length - 1);

function toJob(row: number, v: string[]): Job {
  const g = (i: number) => v[i] ?? "";
  const fit = parseInt(g(10), 10);
  return {
    row,
    dateFound: g(0), id: g(1), title: g(2), company: g(3), location: g(4),
    remote: g(5), posted: g(6), postedAge: g(7), url: g(8), source: g(9),
    fit: Number.isFinite(fit) ? fit : null,
    why: g(11), sponsorship: g(12), resumeVariant: g(13), status: g(14),
    notes: g(15), appliedDate: g(16), lastReply: g(17), replyClass: g(18),
    tailoredResume: g(19), coverLetter: g(20), jdKeywords: g(21),
    contact: g(23), draft: g(24), findPeople: g(25), // 22 = JD excerpt, omitted
    role: g(26),
    resumeAts: g(27),
  };
}

export async function readJobs(): Promise<Job[]> {
  const res = await sheetsClient().spreadsheets.values.get({
    spreadsheetId: SPREADSHEET_ID,
    range: `Jobs!A2:${LAST_COL}`,
  });
  return (res.data.values ?? []).map((v, i) => {
    const job = toJob(i + 2, v as string[]);
    return job;
  });
}

export async function updateRow(row: number, updates: Record<string, string>) {
  const data = Object.entries(updates).map(([header, value]) => {
    const idx = (HEADERS as readonly string[]).indexOf(header);
    if (idx < 0) throw new Error(`unknown header: ${header}`);
    return { range: `Jobs!${colLetter(idx)}${row}`, values: [[value]] };
  });
  await sheetsClient().spreadsheets.values.batchUpdate({
    spreadsheetId: SPREADSHEET_ID,
    requestBody: { valueInputOption: "USER_ENTERED", data },
  });
}
