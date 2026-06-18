"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { findPeopleLinks } from "@/lib/people";
import { RESUME_VARIANTS, type Outreach } from "@/lib/types";

type RunState = "RUNNING" | "SUCCEEDED" | "FAILED" | "NONE";

function statusColor(status: string): string {
  if (status === "Drafted") return "var(--green)";
  if (status.toLowerCase().startsWith("fail")) return "var(--red)";
  return "var(--amber)";
}

export function OutreachConsole({ initial }: { initial: Outreach[] }) {
  const [rows, setRows] = useState<Outreach[]>(initial);
  const [company, setCompany] = useState("");
  const [variant, setVariant] = useState(""); // "" = auto-pick
  const [busy, setBusy] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState("");
  const baseline = useRef(0);
  const startedAt = useRef(0);
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
        if (d.rows) setRows(d.rows);
        const grew = (d.rows?.length ?? 0) > baseline.current;
        const timedOut = Date.now() - startedAt.current > 8 * 60_000;
        if (grew || d.state === "FAILED" || timedOut) {
          if (!grew && (d.state === "FAILED" || timedOut)) {
            setError(
              "The run finished without a new draft. Check the Cloud Run job logs " +
                "(it can fail when APOLLO/Gemini or pdflatex are unavailable).",
            );
          }
          stop();
        }
      } catch {
        /* keep polling */
      }
    }, 6000);
  }, []);

  async function draft(e: React.FormEvent) {
    e.preventDefault();
    const name = company.trim();
    if (!name || busy) return;
    setBusy(true);
    setError("");
    baseline.current = rows.length;
    startedAt.current = Date.now();
    setElapsed(0);
    try {
      const res = await fetch("/api/company-outreach", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ company: name, variant }),
      });
      if (!res.ok) throw new Error("trigger failed");
      poll();
    } catch {
      setError("Could not start the draft run. Try again.");
      stop();
    }
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
          {RESUME_VARIANTS.map((v) => (
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
              Drafting… {elapsed}m (Cloud Run ~2-5m)
            </>
          ) : (
            "✉ Draft outreach"
          )}
        </button>
      </form>
      {error && <div className="text-xs" style={{ color: "var(--red)" }}>{error}</div>}

      <div className="panel overflow-x-auto">
        <table className="console-table">
          <thead>
            <tr>
              <th>Company</th><th>Resume</th><th>Draft</th>
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
                <td colSpan={7} className="py-10 text-center"
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
