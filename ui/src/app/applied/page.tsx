import { readJobs } from "@/lib/jobs";
import { resumeLinksFromEnv } from "@/lib/resume-links";
import { JobsTable } from "@/components/jobs-table";

export const dynamic = "force-dynamic";

export default async function AppliedPage() {
  const jobs = await readJobs();
  const count = jobs.filter((j) =>
    ["Applied", "Outreach sent", "Response", "Interview", "Offer"].includes(j.status),
  ).length;
  return (
    <div>
      <div className="mb-4">
        <div className="eyebrow">in flight</div>
        <h1 className="display mt-1 text-2xl font-extrabold tracking-tight">
          Applied <span style={{ color: "var(--green)" }}>({count})</span>
        </h1>
      </div>
      <JobsTable initial={jobs} mode="applied" resumeLinks={resumeLinksFromEnv()} />
    </div>
  );
}
