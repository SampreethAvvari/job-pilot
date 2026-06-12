import { readCompanies } from "@/lib/companies";
import { readJobs } from "@/lib/jobs";
import { norm, trackedCounts } from "@/lib/company-match";
import type { Company } from "@/lib/types";
import { CompaniesTable } from "@/components/companies-table";

export const dynamic = "force-dynamic";

export default async function CompaniesPage() {
  let companies: Company[] = [];
  try {
    companies = await readCompanies();
  } catch {
    // Companies tab is created by the pipeline's first run; empty until then
  }
  const jobs = await readJobs();
  const tracked = trackedCounts(companies, jobs);
  companies.sort(
    (a, b) =>
      (tracked[norm(b.company)] ?? 0) - (tracked[norm(a.company)] ?? 0) ||
      a.company.localeCompare(b.company),
  );

  return (
    <div className="rise">
      <div className="mb-5">
        <div className="eyebrow">watchlist</div>
        <h1 className="display mt-1 text-2xl font-extrabold tracking-tight">Companies</h1>
        <p className="mt-1 text-xs" style={{ color: "var(--text-dim)" }}>
          Career boards polled directly every 30 minutes. Add a company by name —
          the pipeline auto-detects its ATS (Greenhouse, Lever, Ashby, Workday,
          SmartRecruiters, Workable, Recruitee). Paste the careers URL for Workday
          companies. <b>Jobs</b> counts the roles tracked for you — matching your
          target titles, early-career, sponsorship-viable — exactly what opens
          when you click the company.
        </p>
      </div>

      <CompaniesTable initial={companies} tracked={tracked} />
    </div>
  );
}
