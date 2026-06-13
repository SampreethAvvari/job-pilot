"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { companySize, SIZE_BUCKETS } from "@/lib/company-size";
import { isApplied } from "@/lib/status-sets";
import type { Job } from "@/lib/types";
import { RESUME_VARIANTS, ROLES, STATUSES } from "@/lib/types";
import { AtsBadge } from "@/components/ats-report";
import { FitMeter } from "@/components/status";

async function pushUpdate(row: number, updates: Record<string, string>) {
  const res = await fetch("/api/jobs/update", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ row, updates }),
  });
  if (!res.ok) throw new Error("update failed");
}

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function JobsTable({
  initial,
  mode,
  resumeLinks = {},
  defaultStatus,
  defaultSort,
}: {
  initial: Job[];
  mode: "open" | "applied";
  resumeLinks?: Record<string, string>;
  defaultStatus?: string;
  defaultSort?: "found" | "posted" | "fit";
}) {
  const [jobs, setJobs] = useState(initial);
  const [status, setStatus] = useState(defaultStatus ?? (mode === "open" ? "New" : "all"));
  const [source, setSource] = useState("all");
  const [role, setRole] = useState("all");
  const [resume, setResume] = useState("all"); // best-match master resume (FDE/AIE/MLE/SDE)
  const [size, setSize] = useState("all");
  // under-70 fit is noise by default; unscored (manual) jobs are not "under 70"
  const [minFit, setMinFit] = useState(mode === "open" ? 70 : 0);
  const [postedWithin, setPostedWithin] = useState(0); // hours; 0 = any
  const [sortBy, setSortBy] = useState<"found" | "posted" | "fit">(defaultSort ?? "found");
  const [q, setQ] = useState("");
  const [error, setError] = useState("");
  const [pendingApply, setPendingApply] = useState<Job | null>(null);
  const pendingRef = useRef<Job | null>(null);
  const [confirmJob, setConfirmJob] = useState<Job | null>(null);
  const [tailoring, setTailoring] = useState<Set<number>>(new Set());
  const [drafting, setDrafting] = useState<Set<number>>(new Set());

  function runJobAction(
    job: Job,
    endpoint: string,
    done: (j: Job) => boolean,
    setBusy: React.Dispatch<React.SetStateAction<Set<number>>>,
  ) {
    setBusy((s) => new Set(s).add(job.row));
    fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jobId: job.id }),
    }).catch(() => {});
    const started = Date.now();
    const t = setInterval(async () => {
      if (Date.now() - started > 4 * 60_000) {
        clearInterval(t);
        setBusy((s) => { const n = new Set(s); n.delete(job.row); return n; });
        return;
      }
      try {
        const d = await (await fetch("/api/jobs")).json();
        const fresh = (d.jobs as Job[] | undefined)?.find((x) => x.row === job.row);
        if (fresh && done(fresh)) {
          clearInterval(t);
          setJobs((js) => js.map((x) => (x.row === job.row ? { ...x, ...fresh } : x)));
          setBusy((s) => { const n = new Set(s); n.delete(job.row); return n; });
        }
      } catch { /* keep polling */ }
    }, 15_000);
  }

  const analyze = (job: Job) =>
    runJobAction(
      job, "/api/tailor",
      // wait for the value to CHANGE — a retried row already holds a FAILED marker
      (j) => !!j.tailoredResume && j.tailoredResume !== job.tailoredResume,
      setTailoring,
    );
  const draftOutreach = (job: Job) =>
    runJobAction(job, "/api/outreach", (j) => !!j.draft, setDrafting);

  // When the user comes back from the posting tab, ask whether they applied.
  useEffect(() => {
    const onFocus = () => {
      if (pendingRef.current) {
        setConfirmJob(pendingRef.current);
        pendingRef.current = null;
        setPendingApply(null);
      }
    };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, []);

  const sources = useMemo(
    () => Array.from(new Set(initial.map((j) => j.source))).sort(),
    [initial],
  );

  const visible = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return jobs
      .filter((j) => (mode === "applied" ? isApplied(j.status) : true))
      .filter((j) => {
        if (status === "all") {
          return mode === "applied"
            ? true
            : !isApplied(j.status) && j.status !== "Rejected" && j.status !== "Dismissed";
        }
        return (j.status || "New") === status;
      })
      .filter((j) => source === "all" || j.source === source)
      .filter((j) => role === "all" || (j.role || j.resumeVariant) === role)
      .filter((j) => resume === "all" || j.resumeVariant === resume)
      .filter((j) => size === "all" || companySize(j.company) === size)
      .filter((j) => j.fit === null || j.fit >= minFit)
      .filter((j) => {
        if (!postedWithin) return true;
        if (!j.posted) return false;
        const ts = Date.parse(j.posted.replace(" ", "T") + "Z");
        return Number.isFinite(ts) && Date.now() - ts <= postedWithin * 3600_000;
      })
      .filter(
        (j) =>
          !needle ||
          `${j.title} ${j.company} ${j.location}`.toLowerCase().includes(needle),
      )
      .sort((a, b) => {
        if (mode === "applied") {
          return (b.appliedDate || b.dateFound).localeCompare(a.appliedDate || a.dateFound);
        }
        if (sortBy === "posted") return (b.posted || "").localeCompare(a.posted || "");
        if (sortBy === "fit") return (b.fit ?? -1) - (a.fit ?? -1);
        return (b.dateFound + String(b.fit ?? -1).padStart(3, "0")).localeCompare(
          a.dateFound + String(a.fit ?? -1).padStart(3, "0"),
        );
      });
  }, [jobs, status, source, role, resume, size, minFit, postedWithin, sortBy, q, mode]);

  function mutate(row: number, patch: Partial<Job>, updates: Record<string, string>) {
    const prev = jobs;
    setJobs((js) => js.map((j) => (j.row === row ? { ...j, ...patch } : j)));
    pushUpdate(row, updates).catch(() => {
      setJobs(prev);
      setError("Save failed — change reverted. Try again.");
      setTimeout(() => setError(""), 5000);
    });
  }

  function markApplied(job: Job) {
    const d = job.appliedDate || today();
    mutate(job.row,
      { status: "Applied", appliedDate: d },
      { Status: "Applied", "Applied date": d });
  }

  function openPosting(job: Job) {
    pendingRef.current = job;
    setPendingApply(job);
    window.open(job.url, "_blank", "noopener");
  }

  function setStatusManual(job: Job, v: string) {
    const stampDate = v === "Applied" && !job.appliedDate;
    const extra: Record<string, string> = stampDate ? { "Applied date": today() } : {};
    mutate(job.row,
      { status: v, appliedDate: stampDate ? today() : job.appliedDate },
      { Status: v, ...extra });
  }

  const statusOptions = mode === "open" ? ["all", ...STATUSES] : ["all", ...STATUSES.filter(isApplied), "Rejected"];

  return (
    <div className="rise">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="search title / company / location…"
          className="panel w-64 px-3 py-1.5 text-xs outline-none focus:border-[var(--amber)]"
        />
        <select className="panel cell-select px-2 py-1.5 text-xs"
                value={status} onChange={(e) => setStatus(e.target.value)}>
          {statusOptions.map((s) => (
            <option key={s} value={s}>{s === "all" ? "status: all" : s}</option>
          ))}
        </select>
        <select className="panel cell-select px-2 py-1.5 text-xs"
                value={source} onChange={(e) => setSource(e.target.value)}>
          <option value="all">source: all</option>
          {sources.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <select className="panel cell-select px-2 py-1.5 text-xs"
                value={role} onChange={(e) => setRole(e.target.value)}>
          <option value="all">role: all</option>
          {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
        <select className="panel cell-select px-2 py-1.5 text-xs"
                title="Best-match master resume for the job (FDE / AIE / MLE / SDE)"
                value={resume} onChange={(e) => setResume(e.target.value)}>
          <option value="all">resume: all</option>
          {RESUME_VARIANTS.map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
        <select className="panel cell-select px-2 py-1.5 text-xs"
                title="Company size (best-effort, by company name)"
                value={size} onChange={(e) => setSize(e.target.value)}>
          <option value="all">size: all</option>
          {SIZE_BUCKETS.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <select className="panel cell-select px-2 py-1.5 text-xs"
                value={minFit} onChange={(e) => setMinFit(Number(e.target.value))}>
          {[0, 50, 60, 70, 80, 90].map((n) => (
            <option key={n} value={n}>fit ≥ {n}</option>
          ))}
        </select>
        <select className="panel cell-select px-2 py-1.5 text-xs"
                value={postedWithin} onChange={(e) => setPostedWithin(Number(e.target.value))}>
          <option value={0}>posted: any</option>
          <option value={24}>posted ≤ 24h</option>
          <option value={72}>posted ≤ 3d</option>
          <option value={168}>posted ≤ 7d</option>
        </select>
        {mode === "open" && (
          <select className="panel cell-select px-2 py-1.5 text-xs"
                  value={sortBy} onChange={(e) => setSortBy(e.target.value as typeof sortBy)}>
            <option value="found">sort: newest found</option>
            <option value="posted">sort: recently posted</option>
            <option value="fit">sort: best fit</option>
          </select>
        )}
        <span className="eyebrow ml-auto">{visible.length} shown</span>
      </div>

      {error && (
        <div className="mb-3 rounded border border-[rgba(226,109,92,0.4)] px-3 py-2 text-xs"
             style={{ color: "var(--red)" }}>{error}</div>
      )}

      {pendingApply && (
        <div className="mb-3 rounded border px-3 py-2 text-xs"
             style={{ borderColor: "rgba(255,176,0,0.4)", color: "var(--amber)" }}>
          Posting opened in a new tab — I&apos;ll ask about it when you come back.
        </div>
      )}

      <div className="panel overflow-x-auto">
        <table className="console-table">
          <thead>
            <tr>
              <th>Fit</th><th>Role</th><th>Company</th><th>Location</th>
              <th>Posted</th><th>Src</th><th>Sponsor</th>
              <th>Resume</th><th>Docs</th><th>Outreach</th>{mode === "applied" && <th>Applied</th>}<th>Status</th><th></th>
            </tr>
          </thead>
          <tbody>
            {visible.map((j) => (
              <tr key={j.row}>
                <td><FitMeter fit={j.fit} /></td>
                <td className="max-w-72">
                  <a href={j.url} target="_blank" rel="noopener"
                     className="font-semibold hover:underline"
                     title={j.why}>{j.title}</a>
                  {j.why && (
                    <div className="mt-0.5 text-[11px]" style={{ color: "var(--text-faint)" }}>
                      {j.why}
                    </div>
                  )}
                  {j.jdKeywords && (
                    <div className="mt-0.5 max-w-72 truncate text-[10px]"
                         style={{ color: "var(--cyan)" }} title={j.jdKeywords}>
                      kw: {j.jdKeywords}
                    </div>
                  )}
                </td>
                <td className="whitespace-nowrap">
                  {j.company}
                  {companySize(j.company) !== "Unknown" && (
                    <div className="text-[10px]" style={{ color: "var(--text-faint)" }}>
                      {companySize(j.company).toLowerCase()}
                    </div>
                  )}
                </td>
                <td className="max-w-40 truncate" title={j.location}>{j.location}</td>
                <td className="whitespace-nowrap" style={{ color: "var(--text-dim)" }}
                    title={j.posted || "posting date unknown"}>
                  {j.postedAge}
                </td>
                <td style={{ color: "var(--text-dim)" }}>{j.source}</td>
                <td>
                  <span style={{
                    color: j.sponsorship === "likely" ? "var(--green)"
                      : j.sponsorship === "unlikely" ? "var(--red)" : "var(--text-faint)",
                  }}>
                    {j.sponsorship || "—"}
                  </span>
                </td>
                <td>
                  {j.resumeVariant && resumeLinks[j.resumeVariant] ? (
                    <a href={resumeLinks[j.resumeVariant]} target="_blank" rel="noopener"
                       className="hover:underline" style={{ color: "var(--cyan)" }}
                       title={`Open the ${j.resumeVariant} resume — best match for this job`}>
                      {j.resumeVariant} ↗
                    </a>
                  ) : (j.resumeVariant || "—")}
                </td>
                <td className="whitespace-nowrap">
                  {j.tailoredResume && !j.tailoredResume.startsWith("FAILED") ? (
                    <span className="flex flex-col gap-0.5 text-[11px]">
                      <a href={j.tailoredResume} target="_blank" rel="noopener"
                         className="hover:underline" style={{ color: "var(--green)" }}
                         title={j.jdKeywords}>Resume ⬇</a>
                      {j.coverLetter && (
                        <a href={j.coverLetter} target="_blank" rel="noopener"
                           className="hover:underline" style={{ color: "var(--green)" }}>
                          Cover ⬇
                        </a>
                      )}
                      {j.resumeAts && <AtsBadge job={j} />}
                    </span>
                  ) : tailoring.has(j.row) ? (
                    <span className="blink text-[11px]" style={{ color: "var(--amber)" }}>
                      tailoring…
                    </span>
                  ) : (
                    <span className="flex flex-col gap-0.5">
                      {j.tailoredResume.startsWith("FAILED") && (
                        <span className="text-[11px]" style={{ color: "var(--red)" }}
                              title={j.tailoredResume}>
                          ✕ failed — hover for why
                        </span>
                      )}
                      <button onClick={() => analyze(j)}
                              className="btn-ghost px-2 py-1 text-[11px]"
                              title="Extract JD keywords + generate tailored resume & cover letter (~1 min)">
                        ✨ Tailor
                      </button>
                    </span>
                  )}
                </td>
                <td className="whitespace-nowrap">
                  {j.draft ? (
                    <span className="flex flex-col gap-0.5 text-[11px]">
                      <a href={j.draft} target="_blank" rel="noopener"
                         className="hover:underline" style={{ color: "var(--violet)" }}
                         title={j.contact}>Draft ✉</a>
                      {j.findPeople && (
                        <a href={j.findPeople} target="_blank" rel="noopener"
                           className="hover:underline" style={{ color: "var(--text-faint)" }}>
                          Find people
                        </a>
                      )}
                    </span>
                  ) : drafting.has(j.row) ? (
                    <span className="blink text-[11px]" style={{ color: "var(--amber)" }}>
                      drafting…
                    </span>
                  ) : (
                    <button onClick={() => draftOutreach(j)}
                            className="btn-ghost px-2 py-1 text-[11px]"
                            title="Find a recruiter contact and draft a personalized email into your Gmail drafts (~1 min)">
                      ✉ Draft
                    </button>
                  )}
                  <a href={`/assistant?job=${j.id}`}
                     className="mt-0.5 block text-[11px] hover:underline"
                     style={{ color: "var(--text-faint)" }}
                     title="Chat about this job: application answers, resume tweaks, cover letter">
                    💬 Ask
                  </a>
                </td>
                {mode === "applied" && (
                  <td className="whitespace-nowrap" style={{ color: "var(--text-dim)" }}>
                    {j.appliedDate || "—"}
                  </td>
                )}
                <td>
                  <span className="flex items-center gap-1">
                    {isApplied(j.status) && (
                      <span title={`Applied ${j.appliedDate}`}
                            style={{ color: "var(--green)", fontWeight: 700 }}>✓</span>
                    )}
                    <select
                      className="cell-select"
                      value={j.status || "New"}
                      onChange={(e) => setStatusManual(j, e.target.value)}
                    >
                      {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </span>
                  {mode === "open" && j.appliedDate && (
                    <div className="text-[10px]" style={{ color: "var(--text-faint)" }}>
                      applied {j.appliedDate}
                    </div>
                  )}
                </td>
                <td>
                  {!isApplied(j.status) ? (
                    <span className="flex items-center gap-1">
                      <button onClick={() => openPosting(j)} className="btn-amber px-3 py-1 text-[11px]"
                              title="Open posting in a new tab — I'll ask if you applied when you return">
                        Apply ↗
                      </button>
                      <button
                        onClick={() => mutate(j.row,
                          { status: "Dismissed" },
                          { Status: "Dismissed", Notes: "dismissed: not relevant" })}
                        className="btn-ghost px-2 py-1 text-[11px]"
                        title="Not relevant — hide this job everywhere"
                        style={{ color: "var(--red)" }}
                      >
                        ✕
                      </button>
                    </span>
                  ) : (
                    <a href={j.url} target="_blank" rel="noopener"
                       className="btn-ghost inline-block px-3 py-1 text-[11px]">
                      Open ↗
                    </a>
                  )}
                </td>
              </tr>
            ))}
            {visible.length === 0 && (
              <tr><td colSpan={mode === "applied" ? 13 : 12} className="py-10 text-center"
                      style={{ color: "var(--text-faint)" }}>
                {mode === "applied" ? "Nothing applied yet — go get them." : "No jobs match the filters."}
              </td></tr>
            )}
          </tbody>
        </table>
      </div>

      {confirmJob && typeof document !== "undefined" && createPortal(
        <div
          style={{
            position: "fixed", inset: 0, zIndex: 9999,
            display: "flex", alignItems: "center", justifyContent: "center",
            background: "rgba(5,7,9,0.78)",
          }}
          onClick={() => setConfirmJob(null)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              width: "100%", maxWidth: 420, margin: 16, padding: 24,
              background: "#11161c", borderRadius: 12,
              border: "1px solid rgba(255,176,0,0.4)",
              boxShadow: "0 20px 60px rgba(0,0,0,0.6)",
              color: "#e8e4da",
            }}
          >
            <div className="eyebrow">confirm application</div>
            <div className="display mt-2 text-lg font-bold">
              Did you apply to {confirmJob.title}?
            </div>
            <div className="mt-1 text-xs" style={{ color: "rgba(232,228,218,0.55)" }}>
              {confirmJob.company} · {confirmJob.location}
            </div>
            <div className="mt-5 flex gap-2">
              <button
                className="btn-amber px-4 py-2 text-xs"
                onClick={() => { markApplied(confirmJob); setConfirmJob(null); }}
              >
                ✓ Yes, applied
              </button>
              <button
                className="btn-ghost px-4 py-2 text-xs"
                onClick={() => setConfirmJob(null)}
              >
                Not yet
              </button>
            </div>
          </div>
        </div>,
        document.body,
      )}
    </div>
  );
}
