import { readJobs } from "@/lib/jobs";
import { resumeLinksFromEnv } from "@/lib/resume-links";
import { JobsProvider } from "@/components/jobs-store";
import JobsView from "@/components/jobs-view";

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
          Applied <span style={{ color: "var(--emerald)" }}>({count})</span>
        </h1>
      </div>
      <JobsProvider initial={jobs}>
        <JobsView mode="applied" resumeLinks={resumeLinksFromEnv()} />
      </JobsProvider>
    </div>
  );
}
