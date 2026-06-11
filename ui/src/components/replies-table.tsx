"use client";

import { useState } from "react";

import type { Job } from "@/lib/types";
import { StatusPill } from "@/components/status";

const NOT_A_REPLY = "not_a_reply";
const CLASS_OPTIONS = [
  { value: "next_step", label: "next step" },
  { value: "automated_ack", label: "automated ack" },
  { value: "rejection", label: "rejection" },
  { value: NOT_A_REPLY, label: "not a reply — remove" },
];

async function pushUpdate(row: number, updates: Record<string, string>) {
  const res = await fetch("/api/jobs/update", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ row, updates }),
  });
  if (!res.ok) throw new Error("update failed");
}

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
  if (replyClass === "rejection" || replyClass === "rejected") return "var(--red)";
  return "var(--text-dim)";
}

export function RepliesTable({ initial }: { initial: Job[] }) {
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
    <div className="panel overflow-x-auto">
      {error && (
        <div className="px-3 py-2 text-xs" style={{ color: "var(--red)" }}>{error}</div>
      )}
      <table className="console-table">
        <thead>
          <tr><th>Reply date</th><th>Company</th><th>Role</th><th>Class</th><th>Status</th></tr>
        </thead>
        <tbody>
          {jobs.map((j) => (
            <tr key={j.row}>
              <td className="whitespace-nowrap">{j.lastReply}</td>
              <td>{j.company}</td>
              <td>
                <a className="hover:underline" href={j.url} target="_blank" rel="noopener">
                  {j.title}
                </a>
              </td>
              <td>
                <select
                  className="panel cell-select px-2 py-1.5 text-xs"
                  style={{ color: classColor(j.replyClass) }}
                  value={CLASS_OPTIONS.some((o) => o.value === j.replyClass) ? j.replyClass : ""}
                  onChange={(e) => reclassify(j, e.target.value)}
                >
                  {!CLASS_OPTIONS.some((o) => o.value === j.replyClass) && (
                    <option value="">{j.replyClass || "—"}</option>
                  )}
                  {CLASS_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </td>
              <td><StatusPill status={j.status} /></td>
            </tr>
          ))}
          {jobs.length === 0 && (
            <tr><td colSpan={5} className="py-10 text-center"
                    style={{ color: "var(--text-faint)" }}>
              No replies yet. Once you apply to jobs and recruiters respond to
              spa9659@nyu.edu, they show up here automatically.
            </td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
