import { latestReports, readReports } from "@/lib/reports";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const kind = url.searchParams.get("kind");
  const key = url.searchParams.get("key");
  try {
    if (kind && key) {
      const map = await latestReports(kind);
      return Response.json(map[key] ?? { error: "no report yet" });
    }
    return Response.json({ reports: await readReports() });
  } catch (e) {
    return Response.json({ error: String(e) }, { status: 500 });
  }
}
