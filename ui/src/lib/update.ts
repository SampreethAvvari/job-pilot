// The one true /api/jobs/update caller — ported verbatim from the old
// jobs-table.tsx (lines 15-22) so every mutation path (store, replies-view)
// shares identical failure behavior.

export async function pushUpdate(row: number, updates: Record<string, string>): Promise<void> {
  const res = await fetch("/api/jobs/update", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ row, updates }),
  });
  if (!res.ok) throw new Error("update failed");
}
