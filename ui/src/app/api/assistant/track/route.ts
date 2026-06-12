import { createHash } from "node:crypto";

import { appendJob, readJobs, updateRow } from "@/lib/jobs";
import { triggerTailor } from "@/lib/run";

/** Mirror of python dedup.key(): sha1("norm(company)|norm(title)")[:16]. */
function norm(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}
function jobKey(company: string, title: string): string {
  return createHash("sha1")
    .update(`${norm(company)}|${norm(title)}`)
    .digest("hex")
    .slice(0, 16);
}

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as {
      jobId?: string;
      company?: string;
      title?: string;
      jd?: string;
      url?: string;
    };

    // Existing tracked job: straight to the tailor pipeline.
    if (body.jobId) {
      await triggerTailor(body.jobId);
      return Response.json({ jobId: body.jobId });
    }

    const company = (body.company ?? "").trim();
    const title = (body.title ?? "").trim();
    const jd = (body.jd ?? "").trim();
    if (!company || !title || jd.length < 100) {
      return Response.json(
        { error: "company, title and a real job description are required" },
        { status: 400 },
      );
    }

    const id = jobKey(company, title);
    const existing = (await readJobs()).find((j) => j.id === id);
    if (existing) {
      // refresh the JD so tailoring uses what the user just pasted
      await updateRow(existing.row, { "JD excerpt": jd.slice(0, 5000) });
      await triggerTailor(id);
      return Response.json({ jobId: id, existed: true });
    }

    await appendJob({
      id,
      title,
      company,
      url: (body.url ?? "").trim(),
      jd: jd.slice(0, 5000),
    });
    await triggerTailor(id);
    return Response.json({ jobId: id });
  } catch (e) {
    return Response.json({ error: String(e) }, { status: 500 });
  }
}
