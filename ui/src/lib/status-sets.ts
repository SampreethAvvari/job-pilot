// Client-safe status groupings shared by nav, tables, and pages.

export const APPLIED_SET = new Set([
  "Applied", "Outreach sent", "Response", "Interview", "Offer",
]);

export function isApplied(status: string): boolean {
  return APPLIED_SET.has(status);
}

// A step beyond "applied and waiting" — the company has actually replied.
export const RESPONDED_SET = new Set(["Response", "Interview", "Offer"]);
