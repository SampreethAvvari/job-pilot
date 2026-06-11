import { readCompanies } from "@/lib/companies";
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

  return (
    <div className="rise">
      <div className="mb-5">
        <div className="eyebrow">watchlist</div>
        <h1 className="display mt-1 text-2xl font-extrabold tracking-tight">Companies</h1>
        <p className="mt-1 text-xs" style={{ color: "var(--text-dim)" }}>
          Career boards polled directly every 30 minutes. Add a company by name —
          the pipeline auto-detects its ATS (Greenhouse, Lever, Ashby, Workday,
          SmartRecruiters, Workable, Recruitee). Paste the careers URL for Workday
          companies; boards we can&apos;t reach are marked unsupported and stay
          covered by the aggregator sources.
        </p>
      </div>

      <CompaniesTable initial={companies} />
    </div>
  );
}
