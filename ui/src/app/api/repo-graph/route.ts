import { latestRun, triggerRepoGraph } from "@/lib/run";

export async function POST() {
  try {
    const current = await latestRun();
    if (current.state === "RUNNING") {
      return Response.json({ ok: true, alreadyRunning: true });
    }
    await triggerRepoGraph();
    return Response.json({ ok: true });
  } catch (e) {
    return Response.json({ error: String(e) }, { status: 500 });
  }
}

export async function GET() {
  try {
    return Response.json(await latestRun());
  } catch (e) {
    return Response.json({ error: String(e) }, { status: 500 });
  }
}
