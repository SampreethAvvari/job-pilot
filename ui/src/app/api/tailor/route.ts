import { triggerTailor } from "@/lib/run";

export async function POST(request: Request) {
  try {
    const { jobId } = (await request.json()) as { jobId: string };
    if (!jobId || !/^[a-f0-9]{16}$/.test(jobId)) {
      return Response.json({ error: "valid jobId required" }, { status: 400 });
    }
    await triggerTailor(jobId);
    return Response.json({ ok: true });
  } catch (e) {
    return Response.json({ error: String(e) }, { status: 500 });
  }
}
