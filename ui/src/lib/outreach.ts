import { sheetsClient, SPREADSHEET_ID } from "./google";
import type { Outreach } from "./types";

export type { Outreach } from "./types";

// Reads the Outreach tab (columns A-L — keep in sync with sheets.py OUTREACH_HEADERS).
export async function readOutreach(): Promise<Outreach[]> {
  const res = await sheetsClient().spreadsheets.values.get({
    spreadsheetId: SPREADSHEET_ID,
    range: "Outreach!A2:M",
  });
  return (res.data.values ?? [])
    .map((v, i) => {
      const g = (j: number) => (v[j] as string) ?? "";
      return {
        row: i + 2,
        searchedAt: g(0), company: g(1), domain: g(2), variant: g(3),
        variantReason: g(4), subject: g(5), guessedEmails: g(6), draft: g(7),
        resume: g(8), coverLetter: g(9), status: g(10), notes: g(11),
        peopleFound: g(12),
      };
    })
    .filter((o) => o.company)
    .reverse(); // newest first
}
