import { readJdExcerpt, readJobs } from "@/lib/jobs";
import { fetchJd, jdIsThin } from "@/lib/jd";

// Resolve the best available job description for a job: the stored excerpt if
// it is substantial, otherwise the live posting page.
export async function GET(request: Request) {
  try {
    const jobId = new URL(request.url).searchParams.get("jobId") ?? "";
    const job = (await readJobs()).find((j) => j.id === jobId);
    if (!job) return Response.json({ error: "job not found" }, { status: 404 });

    let jd = await readJdExcerpt(job.row);
    let source: "stored" | "fetched" | "none" = "stored";
    if (jdIsThin(jd) && job.url) {
      const fetched = await fetchJd(job.url);
      if (!jdIsThin(fetched)) {
        jd = fetched;
        source = "fetched";
      } else {
        source = "none";
      }
    } else if (jdIsThin(jd)) {
      source = "none";
    }
    return Response.json({
      company: job.company, title: job.title, url: job.url, jd, source,
    });
  } catch (e) {
    return Response.json({ error: String(e) }, { status: 500 });
  }
}
