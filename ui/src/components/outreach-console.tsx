"use client";

// Card read layer for cold outreach. The polling/batch trigger logic below
// (stop/poll/begin/draft) is ported byte-for-byte from the pre-redesign
// table version — draft-one and batch both POST /api/company-outreach, then
// poll GET every 6s watching for a RUNNING state to clear (or a 12-minute
// timeout) while rows fill in live. That control flow must not drift on a
// visual pass; only the render below it changed.

import { useCallback, useEffect, useRef, useState } from "react";

import Badge from "@/components/ui/badge";
import Button from "@/components/ui/button";
import EmptyState from "@/components/ui/empty-state";
import { findPeopleLinks } from "@/lib/people";
import type { Outreach } from "@/lib/types";

type RunState = "RUNNING" | "SUCCEEDED" | "FAILED" | "NONE";

// The four master resumes an outreach draft can be pinned to (unrelated to
// the jobs table's per-role scoring; kept local now that types.ts no longer
// exports a shared RESUME_VARIANTS).
const OUTREACH_RESUME_VARIANTS = ["FDE", "AIE", "MLE", "SDE"] as const;

/** Tone + blink for the status pill, ported from the pre-redesign table's
 * statusColor (same branch order/conditions): "Drafted" is done, anything
 * starting with "fail" failed, everything else (e.g. "No email", or a row
 * still being written by the batch job) is in-flight and blinks. */
function outreachTone(status: string): { tone: "emerald" | "rose" | "amber"; blink: boolean } {
  if (status === "Drafted") return { tone: "emerald", blink: false };
  if (status.toLowerCase().startsWith("fail")) return { tone: "rose", blink: false };
  return { tone: "amber", blink: true };
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
    <div className="rise flex flex-col gap-4">
      <form onSubmit={draft} className="card flex flex-wrap items-center gap-2 p-4">
        <input
          className="input"
          style={{ minWidth: "16rem" }}
          placeholder="Company name (e.g. Anthropic)"
          value={company}
          maxLength={80}
          onChange={(e) => setCompany(e.target.value)}
          aria-label="company name"
        />
        <select
          className="input"
          value={variant}
          onChange={(e) => setVariant(e.target.value)}
          aria-label="resume variant"
        >
          <option value="">resume: auto-pick</option>
          {OUTREACH_RESUME_VARIANTS.map((v) => (
            <option key={v} value={v}>
              resume: {v}
            </option>
          ))}
        </select>
        <Button type="submit" busy={busy} disabled={!company.trim()}>
          {busy ? `Working… ${elapsed}m (Cloud Run)` : "✉ Draft outreach"}
        </Button>

        <span className="mx-1 text-[12px]" style={{ color: "var(--ink-35)" }}>
          or
        </span>

        <input
          className="input"
          style={{ width: "4.5rem" }}
          type="number"
          min={1}
          max={50}
          value={batchN}
          onChange={(e) => setBatchN(Math.max(1, Math.min(50, Number(e.target.value) || 1)))}
          aria-label="batch size"
        />
        <Button
          type="button"
          variant="ghost"
          disabled={busy}
          title="Draft the freshest real-hiring companies from the Jobs tab (1 Hunter credit each)"
          onClick={() => begin({ batch: batchN })}
        >
          ✦ Batch-draft fresh companies
        </Button>
      </form>
      {error && (
        <div className="text-[13px]" style={{ color: "var(--rose)" }} role="alert">
          {error}
        </div>
      )}

      {rows.length === 0 ? (
        <EmptyState title="No outreach yet" hint="Draft one company above or run a batch." />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {rows.map((o) => (
            <OutreachCard key={o.row} o={o} />
          ))}
        </div>
      )}
    </div>
  );
}

function OutreachCard({ o }: { o: Outreach }) {
  const { tone, blink } = outreachTone(o.status);
  const emails = o.emailsFound ? o.emailsFound.split(";").map((p) => p.trim()).filter(Boolean) : [];
  const inboxes = o.guessedEmails ? o.guessedEmails.split(",").map((p) => p.trim()).filter(Boolean) : [];
  const people = findPeopleLinks(o.company);

  return (
    <article className="card card-hover rise flex flex-col gap-3 p-5">
      <header className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p
            className="truncate font-semibold"
            style={{ fontFamily: "var(--font-archivo)", fontSize: 16, color: "var(--ink)" }}
            title={o.company}
          >
            {o.company}
          </p>
          {o.domain && (
            <p className="mt-0.5 truncate text-[12px]" style={{ color: "var(--ink-55)" }}>
              {o.domain}
            </p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <Badge tone="neutral">{o.variant || "·"}</Badge>
          <span className={blink ? "blink" : undefined}>
            <Badge tone={tone}>{o.status || "·"}</Badge>
          </span>
        </div>
      </header>
      {o.variantReason && (
        <p className="truncate text-[11px]" style={{ color: "var(--ink-35)" }} title={o.variantReason}>
          {o.variantReason}
        </p>
      )}

      <div
        className="mt-auto flex flex-wrap items-center gap-1.5 border-t pt-3"
        style={{ borderColor: "var(--line)" }}
      >
        {o.draft ? (
          <a href={o.draft} target="_blank" rel="noopener" className="btn-ghost btn-sm">
            Draft ↗
          </a>
        ) : (
          <Badge tone="neutral">Draft ·</Badge>
        )}

        <Badge tone={o.coverLetter === "yes" ? "emerald" : "neutral"}>
          {o.coverLetter === "yes" ? "Cover ✓" : "Cover ·"}
        </Badge>

        <Badge tone={emails.length > 0 ? "blue" : "neutral"}>
          {emails.length > 0
            ? `Emails found (${emails.length})`
            : "Emails found ·"}
        </Badge>

        <details className="inline-block">
          <summary className="btn-ghost btn-sm inline-flex cursor-pointer list-none select-none">
            Find the person
          </summary>
          <div className="mt-1.5 flex flex-wrap gap-x-2 gap-y-1 pl-1">
            {people.map((l) => (
              <a
                key={l.label}
                href={l.url}
                target="_blank"
                rel="noopener"
                className="text-[11px] hover:underline"
                style={{ color: "var(--ink-55)" }}
              >
                {l.label} ↗
              </a>
            ))}
          </div>
        </details>

        <Badge tone={inboxes.length > 0 ? "violet" : "neutral"}>
          {inboxes.length > 0 ? `Quick inboxes (${inboxes.length})` : "Quick inboxes ·"}
        </Badge>
      </div>

      {(emails.length > 0 || inboxes.length > 0) && (
        <div className="text-[11px]" style={{ color: "var(--ink-35)" }}>
          {emails.length > 0 && (
            <p className="truncate" title={o.emailsFound}>
              found: {emails.slice(0, 3).join(", ")}
            </p>
          )}
          {inboxes.length > 0 && (
            <p className="truncate" title={o.guessedEmails}>
              guessed: {inboxes.slice(0, 3).join(", ")}
            </p>
          )}
        </div>
      )}
    </article>
  );
}
