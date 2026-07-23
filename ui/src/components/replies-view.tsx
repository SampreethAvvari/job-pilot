"use client";

// Inbox-card read layer for recruiter replies. The status-walk rules in
// correction()/reclassify() are ported byte-for-byte from replies-table.tsx
// (the pre-redesign semantics reference) — they encode pipeline behavior
// (not_a_reply clears the reply and walks Status back, rejection closes the
// job, next_step advances Response) that must not drift on a visual pass.

import { useState } from "react";

import type { Job } from "@/lib/types";
import { StatusPill } from "@/components/status";
import EmptyState from "@/components/ui/empty-state";
import { pushUpdate } from "@/lib/update";

const NOT_A_REPLY = "not_a_reply";
const CLASS_OPTIONS = [
  { value: "next_step", label: "next step" },
  { value: "automated_ack", label: "automated ack" },
  { value: "rejection", label: "rejection" },
  { value: NOT_A_REPLY, label: "not a reply — remove" },
];

/** Sheet updates for a manual reclassification, mirroring pipeline semantics:
 * rejection closes the job, next_step moves it to Response (forward only), and
 * "not a reply" erases the reply and walks Status back to where it was. */
function correction(job: Job, value: string): Record<string, string> {
  if (value === NOT_A_REPLY) {
    const updates: Record<string, string> = { "Reply class": "", "Last reply": "" };
    if (job.status === "Response") {
      updates["Status"] = job.appliedDate ? "Applied" : "Outreach sent";
    }
    return updates;
  }
  const updates: Record<string, string> = { "Reply class": value };
  if (value === "rejection") updates["Status"] = "Rejected";
  if (value === "next_step" && (job.status === "Applied" || job.status === "Outreach sent")) {
    updates["Status"] = "Response";
  }
  return updates;
}

function classColor(replyClass: string): string {
  if (replyClass === "next_step" || replyClass === "interview") return "var(--amber)";
  if (replyClass === "rejection" || replyClass === "rejected") return "var(--rose)";
  return "var(--ink-55)";
}

export function RepliesView({ initial }: { initial: Job[] }) {
  const [jobs, setJobs] = useState(initial);
  const [error, setError] = useState("");

  async function reclassify(job: Job, value: string) {
    const updates = correction(job, value);
    setJobs((js) =>
      value === NOT_A_REPLY
        ? js.filter((j) => j.row !== job.row)
        : js.map((j) =>
            j.row === job.row
              ? { ...j, replyClass: value, status: updates["Status"] ?? j.status }
              : j,
          ),
    );
    try {
      await pushUpdate(job.row, updates);
    } catch {
      setError("Update failed — reload the page and try again.");
    }
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-3">
      {error && (
        <div className="text-[13px]" style={{ color: "var(--rose)" }} role="alert">
          {error}
        </div>
      )}
      {jobs.length === 0 ? (
        <EmptyState
          title="No replies yet"
          hint="Inbox watch checks your mail every hour."
        />
      ) : (
        jobs.map((j) => <ReplyCard key={j.row} job={j} onReclassify={reclassify} />)
      )}
    </div>
  );
}

function ReplyCard({
  job,
  onReclassify,
}: {
  job: Job;
  onReclassify: (job: Job, value: string) => void;
}) {
  return (
    <article className="card card-hover rise flex flex-wrap items-center gap-3 p-4">
      <div className="min-w-0 flex-1 basis-56">
        <p className="eyebrow truncate">{job.company}</p>
        {job.url ? (
          <a
            href={job.url}
            target="_blank"
            rel="noopener"
            className="truncate font-semibold hover:underline"
            style={{ fontFamily: "var(--font-archivo)", fontSize: 15, color: "var(--ink)" }}
            title={job.title}
          >
            {job.title}
          </a>
        ) : (
          <p
            className="truncate font-semibold"
            style={{ fontFamily: "var(--font-archivo)", fontSize: 15, color: "var(--ink)" }}
            title={job.title}
          >
            {job.title}
          </p>
        )}
      </div>

      <span className="shrink-0 font-mono text-[12px]" style={{ color: "var(--ink-55)" }}>
        {job.lastReply}
      </span>

      <div className="shrink-0">
        <StatusPill status={job.status} />
      </div>

      <div className="shrink-0">
        <label className="sr-only" htmlFor={`reply-class-${job.row}`}>
          reply classification
        </label>
        <select
          id={`reply-class-${job.row}`}
          className="input btn-sm"
          style={{ color: classColor(job.replyClass) }}
          value={CLASS_OPTIONS.some((o) => o.value === job.replyClass) ? job.replyClass : ""}
          onChange={(e) => onReclassify(job, e.target.value)}
        >
          {!CLASS_OPTIONS.some((o) => o.value === job.replyClass) && (
            <option value="">{job.replyClass || "—"}</option>
          )}
          {CLASS_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>
    </article>
  );
}
