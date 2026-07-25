"use client";

import { useEffect, useState } from "react";

import Badge from "./ui/badge";
import Card from "./ui/card";
import EmptyState from "./ui/empty-state";
import type { Application } from "@/lib/types";

type Tone = "blue" | "emerald" | "violet" | "amber" | "rose" | "neutral";

const STATUS_TONE: Record<string, Tone> = {
  queued: "neutral",
  filling: "blue",
  needs_review: "blue",
  needs_input: "amber",
  approved: "emerald",
  submitting: "blue",
  submitted: "emerald",
  failed: "rose",
  captcha_blocked: "rose",
  manual_required: "rose",
  check_email: "amber",
};

const STATUS_LABEL: Record<string, string> = {
  queued: "Queued",
  filling: "Filling",
  needs_review: "Needs review",
  needs_input: "Needs input",
  approved: "Approved",
  submitting: "Submitting",
  submitted: "Submitted",
  failed: "Failed",
  captcha_blocked: "Captcha blocked",
  manual_required: "Manual required",
  check_email: "Check email",
};

function statusTone(status: string): Tone {
  return STATUS_TONE[status] ?? "neutral";
}

function statusLabel(status: string): string {
  return STATUS_LABEL[status] ?? (status || "Unknown");
}

export function ApplicationsView() {
  const [applications, setApplications] = useState<Application[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let live = true;
    fetch("/api/applications")
      .then((r) => r.json())
      .then((d) => {
        if (!live) return;
        if (Array.isArray(d.applications)) setApplications(d.applications as Application[]);
      })
      .catch(() => {
        // Keep the list empty, the empty state below explains it either way.
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, []);

  if (loading) {
    return <EmptyState title="Loading applications" hint="One moment." />;
  }

  if (applications.length === 0) {
    return (
      <EmptyState
        title="No applications yet"
        hint="Once the apply pipeline queues a job, it shows up here for review."
      />
    );
  }

  return (
    <div className="rise grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {applications.map((a) => (
        <ApplicationCard key={a.row} a={a} />
      ))}
    </div>
  );
}

function ApplicationCard({ a }: { a: Application }) {
  return (
    <Card className="flex flex-col gap-3 p-5">
      <header className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p
            className="truncate font-semibold"
            style={{ fontFamily: "var(--font-archivo)", fontSize: 16, color: "var(--ink)" }}
            title={`${a.company} · ${a.title}`}
          >
            {a.company} · {a.title}
          </p>
          <p className="mt-0.5 truncate text-[12px]" style={{ color: "var(--ink-55)" }}>
            {a.ats || "custom"}
            {a.location && ` · ${a.location}`}
          </p>
        </div>
        <Badge tone={statusTone(a.status)}>{statusLabel(a.status)}</Badge>
      </header>

      {(a.coverLetter || a.evidence) && (
        <div className="flex flex-wrap items-center gap-3 text-[12.5px]">
          {a.coverLetter && (
            <a
              href={a.coverLetter}
              target="_blank"
              rel="noopener"
              className="hover:underline"
              style={{ color: "var(--blue)" }}
            >
              Cover letter ↗
            </a>
          )}
          {a.evidence && (
            <a
              href={a.evidence}
              target="_blank"
              rel="noopener"
              className="hover:underline"
              style={{ color: "var(--blue)" }}
            >
              Evidence ↗
            </a>
          )}
        </div>
      )}

      {a.questions.length > 0 && (
        <details>
          <summary
            className="cursor-pointer select-none text-[12.5px]"
            style={{ color: "var(--ink-55)" }}
          >
            {a.questions.length} question{a.questions.length === 1 ? "" : "s"}
          </summary>
          <div
            className="mt-2 flex flex-col gap-2.5 border-t pt-2.5"
            style={{ borderColor: "var(--line)" }}
          >
            {a.questions.map((q, i) => (
              <div key={i} className="text-[12.5px]">
                <p className="font-medium" style={{ color: "var(--ink)" }}>
                  {q.label}
                </p>
                <p className="mt-0.5" style={{ color: "var(--ink-55)" }}>
                  {q.answer || "no answer yet"}
                </p>
                {q.screenshot && (
                  <a
                    href={q.screenshot}
                    target="_blank"
                    rel="noopener"
                    className="mt-0.5 inline-block hover:underline"
                    style={{ color: "var(--blue)" }}
                  >
                    Screenshot ↗
                  </a>
                )}
              </div>
            ))}
          </div>
        </details>
      )}

      <div
        className="mt-auto border-t pt-3 text-[11px]"
        style={{ borderColor: "var(--line)", color: "var(--ink-35)" }}
      >
        updated {a.updated || "never"}
      </div>
    </Card>
  );
}
