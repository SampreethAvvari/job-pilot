import Link from "next/link";

import { readCompanies } from "@/lib/companies";
import { readJobs } from "@/lib/jobs";
import { isRemaining, jobsForCompany, norm } from "@/lib/company-match";
import { resumeLinksFromEnv } from "@/lib/resume-links";
import { JobsTable } from "@/components/jobs-table";

export const dynamic = "force-dynamic";

export default async function CompanyPage({
  params,
}: {
  params: Promise<{ name: string }>;
}) {
  const { name } = await params;
  const company = decodeURIComponent(name);
  const [watchlist, jobs] = await Promise.all([
    readCompanies().catch(() => []),
    readJobs(),
  ]);
  const watch = watchlist.find((c) => norm(c.company) === norm(company));
  const companyJobs = watch
    ? jobsForCompany(watch, jobs)
    : jobs.filter((j) => norm(j.company) === norm(company));

  return (
    <div className="rise">
      <div className="mb-4">
        <Link href="/companies" className="text-xs hover:underline"
              style={{ color: "var(--text-dim)" }}>
          ← all companies
        </Link>
        <div className="mt-2 flex flex-wrap items-baseline gap-3">
          <h1 className="display text-2xl font-extrabold tracking-tight">
            {watch?.company ?? company}
          </h1>
          {watch && (
            <span className="text-xs" style={{ color: "var(--text-dim)" }}>
              {watch.ats || "unresolved"}
              {watch.status && <> · {watch.status}</>}
              {watch.lastChecked && <> · checked {watch.lastChecked}</>}
              {watch.careersUrl && (
                <>
                  {" · "}
                  <a className="hover:underline" href={watch.careersUrl}
                     target="_blank" rel="noopener">careers ↗</a>
                </>
              )}
            </span>
          )}
        </div>
        <p className="mt-1 text-xs" style={{ color: "var(--text-dim)" }}>
          {companyJobs.filter(isRemaining).length} left to apply ·{" "}
          {companyJobs.length} tracked in total. Matching your target roles —
          scored, filtered for seniority and sponsorship, with tailoring and
          outreach per job. Switch the status filter to see handled jobs.
        </p>
      </div>

      <JobsTable initial={companyJobs} mode="open" defaultStatus="New"
                 resumeLinks={resumeLinksFromEnv()} />
    </div>
  );
}
