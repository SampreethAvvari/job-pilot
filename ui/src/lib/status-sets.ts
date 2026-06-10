// Client-safe status groupings shared by nav, tables, and pages.

export const APPLIED_SET = new Set([
  "Applied", "Outreach sent", "Response", "Interview", "Offer",
]);

export function isApplied(status: string): boolean {
  return APPLIED_SET.has(status);
}
