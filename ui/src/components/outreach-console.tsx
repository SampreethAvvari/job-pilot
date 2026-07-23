"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { findPeopleLinks } from "@/lib/people";
import type { Outreach } from "@/lib/types";

type RunState = "RUNNING" | "SUCCEEDED" | "FAILED" | "NONE";

// The four master resumes an outreach draft can be pinned to (unrelated to
// the jobs table's per-role scoring; kept local now that types.ts no longer
// exports a shared RESUME_VARIANTS).
const OUTREACH_RESUME_VARIANTS = ["FDE", "AIE", "MLE", "SDE"] as const;

function statusColor(status: string): string {
  if (status === "Drafted") return "var(--green)";
  if (status.toLowerCase().startsWith("fail")) return "var(--red)";
  return "var(--amber)";
}

export function OutreachConsole({ initial }: { initial: Outreach[] }) {
  const [rows, setRows] = useState<Outreach[]>(initial);
  const [company, setCompany] = useState("");
  const [variant, setVariant] = useState(""); // "" = auto-pick
  const [batchN, setBatchN] = useState(30);
  const [busy, setBusy] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState("");
  const baseline = useRef(0);
  const startedAt = useRef(0);
  const sawRunning = useRef(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const stop = () => {
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
    setBusy(false);
  };
  useEffect(() => stop, []);

  const poll = useCallback(() => {
    if (timer.current) clearInterval(timer.current);
    timer.current = setInterval(async () => {
      setElapsed(Math.floor((Date.now() - startedAt.current) / 60000));
      try {
        const d = (await (await fetch("/api/company-outreach")).json()) as {
          rows?: Outreach[];
          state?: RunState;
        };
        if (d.rows) setRows(d.rows); // table fills live as drafts land
        if (d.state === "RUNNING") sawRunning.current = true;
        const finished = sawRunning.current && d.state !== "RUNNING";
        const timedOut = Date.now() - startedAt.current > 12 * 60_000;
        if (finished || timedOut) {
          if (d.state === "FAILED" || (d.rows?.length ?? 0) <= baseline.current) {
            setError(
              "The run finished without new drafts. Check the Cloud Run job logs " +
                "(fails if Gemini/pdflatex/Hunter are unavailable).",
            );
          }
          stop();
        }
      } catch {
        /* keep polling */
      }
    }, 6000);
  }, []);

  async function begin(body: Record<string, unknown>) {
    if (busy) return;
    setBusy(true);
    setError("");
    baseline.current = rows.length;
    startedAt.current = Date.now();
    sawRunning.current = false;
    setElapsed(0);
    try {
      const res = await fetch("/api/company-outreach", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error("trigger failed");
      poll();
    } catch {
      setError("Could not start the run. Try again.");
      stop();
    }
  }

  async function draft(e: React.FormEvent) {
    e.preventDefault();
    const name = company.trim();
    if (name) await begin({ company: name, variant });
  }

  return (
    <div className="flex flex-col gap-4">
      <form onSubmit={draft} className="panel flex flex-wrap items-center gap-2 p-3">
        <input
          className="panel px-2 py-1.5 text-xs"
          style={{ minWidth: "16rem" }}
          placeholder="Company name (e.g. Anthropic)"
          value={company}
          maxLength={80}
          onChange={(e) => setCompany(e.target.value)}
        />
        <select
          className="panel cell-select px-2 py-1.5 text-xs"
          value={variant}
          onChange={(e) => setVariant(e.target.value)}
        >
          <option value="">resume: auto-pick</option>
          {OUTREACH_RESUME_VARIANTS.map((v) => (
            <option key={v} value={v}>
              resume: {v}
            </option>
          ))}
        </select>
        <button className="btn-amber px-4 py-1.5 text-xs" type="submit"
                disabled={busy || !company.trim()}>
          {busy ? (
            <>
              <span className="blink mr-1">●</span>
              Working… {elapsed}m (Cloud Run)
            </>
          ) : (
            "✉ Draft outreach"
          )}
        </button>

        <span className="mx-1 text-[11px]" style={{ color: "var(--text-faint)" }}>or</span>

        <input
          className="panel px-2 py-1.5 text-xs"
          style={{ width: "4.5rem" }}
          type="number"
          min={1}
          max={50}
          value={batchN}
          onChange={(e) => setBatchN(Math.max(1, Math.min(50, Number(e.target.value) || 1)))}
        />
        <button className="btn-ghost px-3 py-1.5 text-xs" type="button" disabled={busy}
                title="Draft the freshest real-hiring companies from the Jobs tab (1 Hunter credit each)"
                onClick={() => begin({ batch: batchN })}>
          ✦ Batch-draft fresh companies
        </button>
      </form>
      {error && <div className="text-xs" style={{ color: "var(--red)" }}>{error}</div>}

      <div className="panel overflow-x-auto">
        <table className="console-table">
          <thead>
            <tr>
              <th>Company</th><th>Resume</th><th>Draft</th><th>Emails found</th>
              <th>Find the person</th><th>Quick inboxes</th><th>Cover</th><th>Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((o) => (
              <tr key={o.row}>
                <td>
                  <span className="font-semibold">{o.company}</span>
                  {o.domain && (
                    <div className="text-[10px]" style={{ color: "var(--text-faint)" }}>
                      {o.domain}
                    </div>
                  )}
                </td>
                <td title={o.variantReason} style={{ color: "var(--text-dim)" }}>
                  {o.variant || "—"}
                </td>
                <td>
                  {o.draft ? (
                    <a className="hover:underline" href={o.draft} target="_blank"
                       rel="noopener" style={{ color: "var(--green)" }}>
                      open draft ↗
                    </a>
                  ) : "—"}
                </td>
                <td className="max-w-64 text-[10px]" title={o.emailsFound}
                    style={{ color: o.emailsFound ? "var(--text-dim)" : "var(--text-faint)" }}>
                  {o.emailsFound
                    ? o.emailsFound.split(";").slice(0, 3).map((p, i) => (
                        <div key={i} className="truncate">{p.trim()}</div>
                      ))
                    : "—"}
                </td>
                <td className="max-w-72">
                  <div className="flex flex-wrap gap-x-2 gap-y-0.5">
                    {findPeopleLinks(o.company).map((l) => (
                      <a key={l.label} className="text-[10px] hover:underline"
                         href={l.url} target="_blank" rel="noopener"
                         style={{ color: "var(--text-dim)" }}>
                        {l.label} ↗
                      </a>
                    ))}
                  </div>
                </td>
                <td className="max-w-56 truncate text-[10px]"
                    title={o.guessedEmails} style={{ color: "var(--text-faint)" }}>
                  {o.guessedEmails || "—"}
                </td>
                <td style={{ color: o.coverLetter === "yes" ? "var(--green)" : "var(--text-faint)" }}>
                  {o.coverLetter === "yes" ? "✓" : "—"}
                </td>
                <td style={{ color: statusColor(o.status) }}>{o.status || "—"}</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={8} className="py-10 text-center"
                    style={{ color: "var(--text-faint)" }}>
                  No drafts yet. Search a company above to create your first one.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
