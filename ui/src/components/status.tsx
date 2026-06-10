export function statusPillClass(status: string): string {
  const map: Record<string, string> = {
    New: "pill-new",
    Applied: "pill-applied",
    "Outreach sent": "pill-outreach",
    Response: "pill-response",
    Interview: "pill-interview",
    Offer: "pill-offer",
    Rejected: "pill-rejected",
    Dismissed: "pill-new",
  };
  return `pill ${map[status] ?? "pill-new"}`;
}

export function StatusPill({ status }: { status: string }) {
  return <span className={statusPillClass(status)}>{status || "New"}</span>;
}

export function FitMeter({ fit }: { fit: number | null }) {
  if (fit === null) return <span style={{ color: "var(--text-faint)" }}>—</span>;
  const color =
    fit >= 80 ? "var(--green)" : fit >= 60 ? "var(--amber)" : "var(--text-faint)";
  return (
    <span className="fit-meter" style={{ color }}>
      {fit}
      <span className="fit-bar">
        <div style={{ width: `${fit}%`, background: color }} />
      </span>
    </span>
  );
}
