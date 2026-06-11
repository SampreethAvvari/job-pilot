"use client";

import Link from "next/link";
import { useState } from "react";

import type { Company } from "@/lib/types";

function statusColor(status: string): string {
  if (status === "active") return "var(--green)";
  if (status.startsWith("error")) return "var(--red)";
  if (status === "unsupported") return "var(--text-faint)";
  return "var(--amber)"; // pending / blank: resolver picks it up next run
}

export function CompaniesTable({ initial }: { initial: Company[] }) {
  const [companies, setCompanies] = useState(initial);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function refetch() {
    const d = await (await fetch("/api/companies")).json();
    if (d.companies) setCompanies(d.companies as Company[]);
  }

  async function add(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || busy) return;
    setBusy(true);
    setError("");
    try {
      const res = await fetch("/api/companies", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ company: name.trim(), careersUrl: url.trim() }),
      });
      if (!res.ok) throw new Error("add failed");
      setName("");
      setUrl("");
      await refetch();
    } catch {
      setError("Could not add the company — try again.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(c: Company) {
    if (!window.confirm(`Stop watching ${c.company}?`)) return;
    setBusy(true);
    setError("");
    try {
      const res = await fetch("/api/companies", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ remove: true, row: c.row }),
      });
      if (!res.ok) throw new Error("remove failed");
      await refetch(); // rows renumber after a delete — never splice locally
    } catch {
      setError("Could not remove the company — try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <form onSubmit={add} className="panel flex flex-wrap items-center gap-2 p-3">
        <input
          className="panel px-2 py-1.5 text-xs"
          style={{ minWidth: "14rem" }}
          placeholder="Company name (e.g. Snowflake)"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <input
          className="panel grow px-2 py-1.5 text-xs"
          style={{ minWidth: "20rem" }}
          placeholder="Careers URL — optional, but required for Workday boards"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
        <button className="btn-amber" type="submit" disabled={busy || !name.trim()}>
          {busy ? "…" : "+ Watch company"}
        </button>
        <span className="text-[11px]" style={{ color: "var(--text-dim)" }}>
          The next run (≤30 min) detects the ATS and starts polling its job board.
        </span>
      </form>
      {error && <div className="text-xs" style={{ color: "var(--red)" }}>{error}</div>}

      <div className="panel overflow-x-auto">
        <table className="console-table">
          <thead>
            <tr>
              <th>Company</th><th>ATS</th><th>Status</th><th>Jobs (last fetch)</th>
              <th>Last checked</th><th>Notes</th><th></th>
            </tr>
          </thead>
          <tbody>
            {companies.map((c) => (
              <tr key={c.row}>
                <td>
                  <Link className="hover:underline"
                        href={`/companies/${encodeURIComponent(c.company)}`}>
                    {c.company}
                  </Link>
                  {c.careersUrl && (
                    <a className="ml-1 text-[10px] hover:underline" href={c.careersUrl}
                       target="_blank" rel="noopener"
                       style={{ color: "var(--text-faint)" }}>↗</a>
                  )}
                </td>
                <td style={{ color: "var(--text-dim)" }}>{c.ats || "—"}</td>
                <td style={{ color: statusColor(c.status) }}>{c.status || "pending"}</td>
                <td>{c.jobsLastFetch || "—"}</td>
                <td className="whitespace-nowrap" style={{ color: "var(--text-dim)" }}>
                  {c.lastChecked || "—"}
                </td>
                <td className="max-w-72 truncate" style={{ color: "var(--text-faint)" }}
                    title={c.notes}>{c.notes}</td>
                <td>
                  <button className="text-xs hover:underline" disabled={busy}
                          style={{ color: "var(--red)" }} onClick={() => remove(c)}>
                    remove
                  </button>
                </td>
              </tr>
            ))}
            {companies.length === 0 && (
              <tr><td colSpan={7} className="py-10 text-center"
                      style={{ color: "var(--text-faint)" }}>
                No companies watched yet. Add one above — the pipeline finds its
                career board and checks it every 30 minutes.
              </td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
