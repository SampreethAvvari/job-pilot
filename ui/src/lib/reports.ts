import { sheetsClient, SPREADSHEET_ID } from "./google";

export type AtsReport = {
  timestamp: string;
  kind: string; // "master" | "job"
  key: string; // variant or job id
  score: number;
  report: {
    score: number;
    breakdown: Record<string, number>;
    keyword_coverage: number;
    pages: number;
    words: number;
    attempts: number;
    issues: string[];
  } | null;
};

export async function readReports(): Promise<AtsReport[]> {
  try {
    const res = await sheetsClient().spreadsheets.values.get({
      spreadsheetId: SPREADSHEET_ID,
      range: "Reports!A2:E",
    });
    return (res.data.values ?? []).map((r) => {
      let parsed = null;
      try { parsed = JSON.parse(r[4] ?? "null"); } catch { /* keep null */ }
      return {
        timestamp: r[0] ?? "", kind: r[1] ?? "", key: r[2] ?? "",
        score: Number(r[3] ?? 0), report: parsed,
      };
    });
  } catch {
    return []; // Reports tab may not exist yet
  }
}

export async function latestReports(kind: string): Promise<Record<string, AtsReport>> {
  const all = await readReports();
  const out: Record<string, AtsReport> = {};
  for (const r of all) {
    if (r.kind === kind) out[r.key] = r; // later rows win (append order)
  }
  return out;
}
