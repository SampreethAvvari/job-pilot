"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import type { Company } from "@/lib/types";
import type { CompanyJobMeta } from "@/lib/company-match";

function norm(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, "");
}

function statusColor(status: string): string {
  if (status === "active") return "var(--green)";
  if (status.startsWith("error")) return "var(--red)";
  if (status === "unsupported") return "var(--text-faint)";
  return "var(--amber)"; // pending / blank: resolver picks it up next run
}

function postedTs(posted: string): number {
  if (!posted) return 0;
  const ts = Date.parse(posted.replace(" ", "T") + "Z");
  return Number.isFinite(ts) ? ts : 0;
}

function age(posted: string): string {
  const ts = postedTs(posted);
  if (!ts) return "—";
  const hours = Math.max(0, (Date.now() - ts) / 3600_000);
  if (hours < 1) return `${Math.round(hours * 60)}m ago`;
  if (hours < 24) return `${Math.round(hours)}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

const EMPTY: CompanyJobMeta = { remaining: 0, newest: "" };

export function CompaniesTable({
  initial,
  meta = {},
}: {
  initial: Company[];
  meta?: Record<string, CompanyJobMeta>;
}) {
  const [companies, setCompanies] = useState(initial);
  const [sortBy, setSortBy] = useState<"newest" | "jobs" | "name">("newest");
  const [fresh, setFresh] = useState(0); // hours; 0 = any
  const [showQuiet, setShowQuiet] = useState(false);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const { visible, quiet } = useMemo(() => {
    const rows = companies.map((c) => ({ c, m: meta[norm(c.company)] ?? EMPTY }));
    const inWindow = (m: CompanyJobMeta) =>
      fresh === 0 || (postedTs(m.newest) && Date.now() - postedTs(m.newest) <= fresh * 3600_000);
    const visible = rows.filter(({ m }) => m.remaining > 0 && inWindow(m));
    const quiet = rows.filter((r) => !visible.includes(r));
    visible.sort((a, b) => {
      if (sortBy === "jobs") return b.m.remaining - a.m.remaining;
      if (sortBy === "name") return a.c.company.localeCompare(b.c.company);
      return b.m.newest.localeCompare(a.m.newest) || b.m.remaining - a.m.remaining;
    });
    quiet.sort((a, b) => a.c.company.localeCompare(b.c.company));
    return { visible, quiet };
  }, [companies, meta, sortBy, fresh]);

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
      setShowQuiet(true); // the new row starts quiet — let the user see it landed
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

  function renderRow({ c, m }: { c: Company; m: CompanyJobMeta }) {
    return (
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
        <td title={`matched at last fetch: ${c.jobsLastFetch || "0"}`}>
          <Link className="hover:underline"
                href={`/companies/${encodeURIComponent(c.company)}`}>
            {m.remaining}
          </Link>
        </td>
        <td className="whitespace-nowrap"
            title={m.newest || "no dated open jobs"}
            style={{
              color: postedTs(m.newest) && Date.now() - postedTs(m.newest) <= 24 * 3600_000
                ? "var(--green)" : "var(--text-dim)",
            }}>
          {age(m.newest)}
        </td>
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
    );
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
      </form>
      {error && <div className="text-xs" style={{ color: "var(--red)" }}>{error}</div>}

      <div className="flex flex-wrap items-center gap-2 text-xs">
        <select className="panel cell-select px-2 py-1.5 text-xs" value={sortBy}
                onChange={(e) => setSortBy(e.target.value as typeof sortBy)}>
          <option value="newest">sort: newest job</option>
          <option value="jobs">sort: most jobs</option>
          <option value="name">sort: name</option>
        </select>
        <select className="panel cell-select px-2 py-1.5 text-xs" value={fresh}
                onChange={(e) => setFresh(Number(e.target.value))}>
          <option value={0}>newest job: any age</option>
          <option value={24}>newest job ≤ 24h</option>
          <option value={72}>newest job ≤ 3d</option>
          <option value={168}>newest job ≤ 7d</option>
        </select>
        <span style={{ color: "var(--text-dim)" }}>
          {visible.length} compan{visible.length === 1 ? "y" : "ies"} with open jobs for you
        </span>
      </div>

      <div className="panel overflow-x-auto">
        <table className="console-table">
          <thead>
            <tr>
              <th>Company</th><th>ATS</th><th>Status</th><th>Jobs</th>
              <th>Newest job</th><th>Last checked</th><th>Notes</th><th></th>
            </tr>
          </thead>
          <tbody>
            {visible.map(renderRow)}
            {visible.length === 0 && (
              <tr><td colSpan={8} className="py-10 text-center"
                      style={{ color: "var(--text-faint)" }}>
                Nothing matches the current filters — every watched company is
                still being checked twice an hour.
              </td></tr>
            )}
          </tbody>
        </table>
      </div>

      {quiet.length > 0 && (
        <div className="flex flex-col gap-2">
          <button className="btn-ghost self-start px-2 py-1 text-xs"
                  onClick={() => setShowQuiet((s) => !s)}>
            {showQuiet ? "▾ hide" : "▸ show"} {quiet.length} quiet
            compan{quiet.length === 1 ? "y" : "ies"} (no relevant jobs right now — still watched)
          </button>
          {showQuiet && (
            <div className="panel overflow-x-auto">
              <table className="console-table">
                <tbody>{quiet.map(renderRow)}</tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
