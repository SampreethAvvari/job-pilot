import { triggerRebuild } from "@/lib/run";

export async function POST(request: Request) {
  try {
    const { variant } = (await request.json()) as { variant: string };
    if (!variant || !/^[A-Z]{2,8}$/.test(variant)) {
      return Response.json({ error: "valid variant required" }, { status: 400 });
    }
    await triggerRebuild(variant);
    return Response.json({ ok: true });
  } catch (e) {
    return Response.json({ error: String(e) }, { status: 500 });
  }
}
