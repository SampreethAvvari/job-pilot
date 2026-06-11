import { sheetsClient, SPREADSHEET_ID } from "./google";
import type { Company } from "./types";

export type { Company } from "./types";

export async function readCompanies(): Promise<Company[]> {
  const res = await sheetsClient().spreadsheets.values.get({
    spreadsheetId: SPREADSHEET_ID,
    range: "Companies!A2:H",
  });
  return (res.data.values ?? [])
    .map((v, i) => {
      const g = (j: number) => (v[j] as string) ?? "";
      return {
        row: i + 2,
        company: g(0), careersUrl: g(1), ats: g(2), slug: g(3),
        status: g(4), lastChecked: g(5), jobsLastFetch: g(6), notes: g(7),
      };
    })
    .filter((c) => c.company);
}

export async function addCompany(company: string, careersUrl: string) {
  await sheetsClient().spreadsheets.values.append({
    spreadsheetId: SPREADSHEET_ID,
    range: "Companies!A1",
    valueInputOption: "RAW",
    insertDataOption: "INSERT_ROWS",
    requestBody: { values: [[company, careersUrl]] },
  });
}

export async function removeCompany(row: number) {
  const svc = sheetsClient();
  const meta = await svc.spreadsheets.get({ spreadsheetId: SPREADSHEET_ID });
  const sheet = meta.data.sheets?.find((s) => s.properties?.title === "Companies");
  const sheetId = sheet?.properties?.sheetId;
  if (sheetId == null) throw new Error("Companies tab not found");
  await svc.spreadsheets.batchUpdate({
    spreadsheetId: SPREADSHEET_ID,
    requestBody: {
      requests: [{
        deleteDimension: {
          range: { sheetId, dimension: "ROWS", startIndex: row - 1, endIndex: row },
        },
      }],
    },
  });
}
