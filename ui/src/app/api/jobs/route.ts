import { readJobs } from "@/lib/jobs";

export async function GET() {
  try {
    return Response.json({ jobs: await readJobs() });
  } catch (e) {
    return Response.json({ error: String(e) }, { status: 500 });
  }
}
