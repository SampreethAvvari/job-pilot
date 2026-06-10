import { updateRow } from "@/lib/jobs";

export async function POST(request: Request) {
  try {
    const { row, updates } = (await request.json()) as {
      row: number;
      updates: Record<string, string>;
    };
    if (!row || row < 2 || !updates || Object.keys(updates).length === 0) {
      return Response.json({ error: "row and updates required" }, { status: 400 });
    }
    await updateRow(row, updates);
    return Response.json({ ok: true });
  } catch (e) {
    return Response.json({ error: String(e) }, { status: 500 });
  }
}
