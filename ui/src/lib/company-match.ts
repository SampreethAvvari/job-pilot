import type { Company, Job } from "./types";

/** Job rows store company names as boards report them ("nvidia" tenant,
 * "Acme Corp" display name); the watchlist holds display names ("Nvidia").
 * Normalize both and also accept the board slug's first segment. */
export function norm(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, "");
}

export function companyAliases(c: Company): Set<string> {
  const aliases = new Set([norm(c.company)]);
  if (c.slug) aliases.add(norm(c.slug.split("/")[0]));
  return aliases;
}

export function jobsForCompany(c: Company, jobs: Job[]): Job[] {
  const aliases = companyAliases(c);
  return jobs.filter((j) => aliases.has(norm(j.company)));
}

/** The console-wide relevance gate: under-70 fit is hidden everywhere.
 * Unscored jobs (manual adds) pass — unknown is not "under 70". */
export const MIN_FIT = 70;

/** Still waiting for the user's action AND relevant. Applied/Outreach/Response/
 * Interview/Offer/Rejected/Dismissed or low-fit jobs drop out of the count. */
export function isRemaining(j: Job): boolean {
  return (
    (j.status === "" || j.status === "New") &&
    (j.fit === null || j.fit >= MIN_FIT)
  );
}

export type CompanyJobMeta = {
  remaining: number; // jobs still waiting for action
  newest: string;    // freshest remaining job's posted stamp ("YYYY-MM-DD HH:MM", "" unknown)
};

/** Per-company remaining count + freshest posting, keyed by normalized company
 * name (stable across sheet-row renumbering, unlike row keys). */
export function companyJobMeta(
  companies: Company[],
  jobs: Job[],
): Record<string, CompanyJobMeta> {
  const meta: Record<string, CompanyJobMeta> = {};
  for (const c of companies) {
    const remaining = jobsForCompany(c, jobs).filter(isRemaining);
    let newest = "";
    for (const j of remaining) {
      if (j.posted && j.posted > newest) newest = j.posted;
    }
    meta[norm(c.company)] = { remaining: remaining.length, newest };
  }
  return meta;
}
