import { readJobs } from "@/lib/jobs";
import { resumeLinksFromEnv } from "@/lib/resume-links";
import { JobsProvider } from "@/components/jobs-store";
import JobsView from "@/components/jobs-view";

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
      <JobsProvider initial={jobs}>
        <JobsView mode="open" resumeLinks={resumeLinks} />
      </JobsProvider>
    </div>
  );
}
