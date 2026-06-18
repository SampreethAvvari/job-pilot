import { readOutreach } from "@/lib/outreach";
import { latestRun, triggerCompanyOutreach } from "@/lib/run";

const VARIANTS = ["AIE", "FDE", "MLE", "SDE"];

// GET: current outreach rows + the shared run state (so the tab can poll).
export async function GET() {
  try {
    const [rows, run] = await Promise.all([
      readOutreach().catch(() => []),
      latestRun().catch(() => ({ state: "NONE" as const, started: "" })),
    ]);
    return Response.json({ rows, state: run.state });
  } catch (e) {
    return Response.json({ error: String(e) }, { status: 500 });
  }
}

// POST { company, variant? }: trigger a company outreach draft run.
export async function POST(request: Request) {
  try {
    const { company, variant } = (await request.json()) as {
      company?: string;
      variant?: string;
    };
    const name = (company ?? "").trim();
    if (!name || name.length > 80) {
      return Response.json({ error: "valid company name required" }, { status: 400 });
    }
    const v = (variant ?? "").toUpperCase();
    if (v && !VARIANTS.includes(v)) {
      return Response.json({ error: "invalid variant" }, { status: 400 });
    }
    await triggerCompanyOutreach(name, v);
    return Response.json({ ok: true });
  } catch (e) {
    return Response.json({ error: String(e) }, { status: 500 });
  }
}
