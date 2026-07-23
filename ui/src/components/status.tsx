export function statusPillClass(status: string): string {
  const map: Record<string, string> = {
    New: "pill-new",
    Applied: "pill-applied",
    "Outreach sent": "pill-outreach",
    Response: "pill-response",
    Interview: "pill-interview",
    Offer: "pill-offer",
    Rejected: "pill-rejected",
    Dismissed: "pill-dismissed",
  };
  return `pill ${map[status] ?? "pill-new"}`;
}

export function StatusPill({ status }: { status: string }) {
  return <span className={statusPillClass(status)}>{status || "New"}</span>;
}
