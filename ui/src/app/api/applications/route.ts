import { readApplications } from "@/lib/applications";

export async function GET() {
  try {
    return Response.json({ applications: await readApplications() });
  } catch (e) {
    return Response.json({ error: String(e) }, { status: 500 });
  }
}
