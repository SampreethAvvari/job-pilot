import { sheetsClient, SPREADSHEET_ID } from "./google";

let cached: { pack: string; at: number } | null = null;
const TTL_MS = 5 * 60_000;

/** The grounding corpus from the Knowledge sheet tab, cached briefly. */
export async function knowledgePack(): Promise<string> {
  if (cached && Date.now() - cached.at < TTL_MS) return cached.pack;
  const res = await sheetsClient().spreadsheets.values.get({
    spreadsheetId: SPREADSHEET_ID,
    range: "Knowledge!A2:C",
  });
  const pack = (res.data.values ?? [])
    .filter((r) => r[0] && r[2])
    .map((r) => `# SOURCE: ${r[0]}\n${r[2]}`)
    .join("\n\n");
  cached = { pack, at: Date.now() };
  return pack;
}
