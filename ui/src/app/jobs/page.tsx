import { readJobs } from "@/lib/jobs";
import { resumeLinksFromEnv } from "@/lib/resume-links";
import { JobsTable } from "@/components/jobs-table";

export const dynamic = "force-dynamic";

export default async function JobsPage() {
  const jobs = await readJobs();
  const resumeLinks = resumeLinksFromEnv();
  return (
    <div>
      <div className="mb-4">
        <div className="eyebrow">registry</div>
        <h1 className="display mt-1 text-2xl font-extrabold tracking-tight">All jobs</h1>
      </div>
      <JobsTable initial={jobs} mode="open" resumeLinks={resumeLinks} />
    </div>
  );
}
