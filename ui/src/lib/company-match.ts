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

/** Tracked-job counts keyed by normalized company name (stable across
 * sheet-row renumbering, unlike row keys). */
export function trackedCounts(companies: Company[], jobs: Job[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const c of companies) {
    counts[norm(c.company)] = jobsForCompany(c, jobs).length;
  }
  return counts;
}
