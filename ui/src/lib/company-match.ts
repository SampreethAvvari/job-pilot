import type { Company, Job } from "./types";

/** Parse a "YYYY-MM-DD HH:MM" (UTC) posted stamp to epoch ms; 0 if unknown. */
export function postedTs(posted: string): number {
  if (!posted) return 0;
  const ts = Date.parse(posted.replace(" ", "T") + "Z");
  return Number.isFinite(ts) ? ts : 0;
}

/** Age computed LIVE from the real posted timestamp — never the frozen
 * "Posted age" column, which goes stale the moment a row is written. */
export function liveAge(posted: string): string {
  const ts = postedTs(posted);
  if (!ts) return "—";
  const hours = Math.max(0, (Date.now() - ts) / 3600_000);
  if (hours < 1) return `${Math.round(hours * 60)}m ago`;
  if (hours < 24) return `${Math.round(hours)}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

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

/** Console wide relevance gate: below 75 is archived server side; the UI
 *  enforces the same floor so legacy rows behave until migration runs. */
export const MIN_FIT = 75;

/** Unscored rows pass only when the owner added them by hand. */
export function passesFit(j: Job, minFit: number): boolean {
  if (j.fit === null) return j.source === "manual";
  return j.fit >= minFit;
}

/** Sort key: real posted time when known; manual rows fall back to the day
 *  the owner added them; anything else sinks. */
export function effectiveRecency(j: Job): number {
  const p = postedTs(j.posted); // postedTs returns 0 as its own "unknown" sentinel
  if (p !== 0) return p;
  if (j.source === "manual") {
    const t = Date.parse(j.dateFound);
    return Number.isNaN(t) ? 0 : t;
  }
  return 0;
}

/** Posted within the last `hours` (default 24) — drives the "new" badge.
 *  Kept here, beside the other clock-reading helpers, so components stay pure
 *  (calling Date.now() straight in a render body trips react-hooks/purity). */
export function isFreshPost(posted: string, hours = 24): boolean {
  const ts = postedTs(posted);
  return ts > 0 && Date.now() - ts <= hours * 3600_000;
}

/** Job falls inside a rolling recency window of `hours`, by effectiveRecency
 *  (real posted time, or dateFound for manual rows). Unknown-age rows fail. */
export function withinRecency(j: Job, hours: number): boolean {
  const ts = effectiveRecency(j);
  return ts !== 0 && Date.now() - ts <= hours * 3600_000;
}

/** Still waiting for the user's action AND relevant. Applied/Outreach/Response/
 * Interview/Offer/Rejected/Dismissed or low-fit jobs drop out of the count. */
export function isRemaining(j: Job): boolean {
  return (
    (j.status === "" || j.status === "New") &&
    passesFit(j, MIN_FIT)
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
