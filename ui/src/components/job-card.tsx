"use client";

// Read layer of the console centerpiece: one job rendered as a card.
// Interaction handlers arrive as props (Task 10 wires them); this task
// renders every affordance fully styled but defaults each handler to a
// no-op so the card is inert on its own.

import type { ReactNode } from "react";

import FitRing from "./ui/fit-ring";
import Badge from "./ui/badge";
import { StatusPill } from "./status";
import { AtsBadge } from "./ats-report";
import { isFreshPost, liveAge, postedTs } from "@/lib/company-match";
import { isApplied } from "@/lib/status-sets";
import { STATUSES } from "@/lib/types";
import type { Job } from "@/lib/types";

export interface JobCardProps {
  job: Job;
  mode: "open" | "applied";
  resumeLinks?: Record<string, string>;
  busyTailor?: boolean;
  busyDraft?: boolean;
  onDismiss?: (job: Job) => void;
  onApply?: (job: Job) => void;
  onTailor?: (job: Job) => void;
  onDraft?: (job: Job) => void;
  onAsk?: (job: Job) => void;
  onStatus?: (job: Job, status: string) => void;
}

const noop = () => {};

/** Meta line values, joined by a middot in render. Never a dash. */
function metaParts(job: Job): string[] {
  const age = postedTs(job.posted) ? liveAge(job.posted) : `seen ${job.dateFound}`;
  return [age, job.location, job.remote === "yes" ? "remote" : "", job.source].filter(
    (s): s is string => Boolean(s),
  );
}

function DocLink({
  href,
  color,
  title,
  children,
}: {
  href: string;
  color: string;
  title?: string;
  children: ReactNode;
}) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener"
      title={title}
      className="inline-flex items-center gap-1 font-medium hover:underline"
      style={{ color }}
    >
      {children}
    </a>
  );
}

export default function JobCard({
  job,
  mode,
  resumeLinks = {},
  busyTailor = false,
  busyDraft = false,
  onDismiss = noop,
  onApply = noop,
  onTailor = noop,
  onDraft = noop,
  onAsk = noop,
  onStatus = noop,
}: JobCardProps) {
  const applied = isApplied(job.status);
  const fresh = isFreshPost(job.posted);
  const meta = metaParts(job);

  const hasTailored = Boolean(job.tailoredResume) && !job.tailoredResume.startsWith("FAILED");
  const tailorFailed = job.tailoredResume.startsWith("FAILED");
  const variantLink = job.resumeVariant ? resumeLinks[job.resumeVariant] : "";

  // The docs strip is worth its own band only when there is something in it.
  const showDocs =
    hasTailored ||
    Boolean(job.coverLetter) ||
    Boolean(job.resumeAts) ||
    Boolean(job.draft) ||
    Boolean(job.findPeople) ||
    Boolean(variantLink) ||
    busyTailor ||
    busyDraft;

  return (
    <article className="card card-hover rise relative flex flex-col gap-3 p-5">
      {!applied && (
        <button
          type="button"
          aria-label="dismiss this job forever"
          onClick={() => onDismiss(job)}
          className="absolute right-3 top-3 grid h-7 w-7 place-items-center rounded-full text-[15px] transition-colors hover:bg-[var(--surface-2)]"
          style={{ color: "var(--ink-35)" }}
        >
          ✕
        </button>
      )}

      <header className="flex items-start gap-3 pr-8">
        <FitRing fit={job.fit} />
        <div className="min-w-0">
          <p className="eyebrow truncate">{job.company}</p>
          <h3
            className="truncate font-semibold"
            style={{ fontFamily: "var(--font-archivo)", fontSize: 16, color: "var(--ink)" }}
            title={job.title}
          >
            {job.title}
          </h3>
          <p
            className="mt-1 flex flex-wrap items-center text-[12px]"
            style={{ color: "var(--ink-55)" }}
          >
            {meta.map((m, i) => (
              <span key={i} className="inline-flex items-center">
                {i > 0 && <span className="px-1.5" style={{ color: "var(--ink-35)" }}>·</span>}
                {m}
              </span>
            ))}
          </p>
        </div>
      </header>

      {(fresh || job.sponsorship === "unclear" || job.sponsorship === "likely") && (
        <div className="flex flex-wrap items-center gap-2">
          {fresh && <span className="pill pill-new">new</span>}
          {job.sponsorship === "likely" && <Badge tone="emerald">sponsors</Badge>}
          {job.sponsorship === "unclear" && <Badge tone="neutral">sponsorship unclear</Badge>}
        </div>
      )}

      {job.why && (
        <p
          className="line-clamp-2 text-[13px] leading-relaxed"
          style={{ color: "var(--ink-70)" }}
          title={job.why}
        >
          {job.why}
        </p>
      )}

      {showDocs && (
        <div
          className="flex flex-wrap items-center gap-x-4 gap-y-1.5 rounded-xl px-3 py-2 text-[12px]"
          style={{ background: "var(--surface-2)" }}
        >
          {busyTailor ? (
            <span className="blink font-medium" style={{ color: "var(--amber)" }}>
              tailoring…
            </span>
          ) : hasTailored ? (
            <>
              <DocLink href={job.tailoredResume} color="var(--emerald)" title={job.jdKeywords}>
                resume ↓
              </DocLink>
              {job.coverLetter && (
                <DocLink href={job.coverLetter} color="var(--emerald)">
                  cover ↓
                </DocLink>
              )}
              {job.resumeAts && <AtsBadge job={job} />}
            </>
          ) : null}

          {variantLink && !hasTailored && !busyTailor && (
            <DocLink
              href={variantLink}
              color="var(--blue)"
              title={`open the ${job.resumeVariant} resume, best match for this job`}
            >
              {job.resumeVariant} ↗
            </DocLink>
          )}

          {busyDraft ? (
            <span className="blink font-medium" style={{ color: "var(--amber)" }}>
              drafting…
            </span>
          ) : (
            job.draft && (
              <DocLink href={job.draft} color="var(--violet)" title={job.contact}>
                draft ✉
              </DocLink>
            )
          )}
          {job.findPeople && !busyDraft && (
            <DocLink href={job.findPeople} color="var(--ink-55)">
              find people
            </DocLink>
          )}
        </div>
      )}

      {tailorFailed && !busyTailor && (
        <p className="text-[12px]" style={{ color: "var(--rose)" }} title={job.tailoredResume}>
          tailoring failed, hover to see why
        </p>
      )}

      <div className="mt-auto flex flex-wrap items-center gap-2 border-t pt-3" style={{ borderColor: "var(--line)" }}>
        {applied ? (
          <a
            href={job.url}
            target="_blank"
            rel="noopener"
            className="btn btn-sm btn-ghost"
          >
            open ↗
          </a>
        ) : (
          <button type="button" className="btn btn-sm btn-primary" onClick={() => onApply(job)}>
            apply ↗
          </button>
        )}

        {!hasTailored && !busyTailor && (
          <button type="button" className="btn btn-sm btn-ghost" onClick={() => onTailor(job)}>
            {tailorFailed ? "retry tailor" : "tailor"}
          </button>
        )}
        {!job.draft && !busyDraft && (
          <button type="button" className="btn btn-sm btn-ghost" onClick={() => onDraft(job)}>
            draft
          </button>
        )}
        <button type="button" className="btn btn-sm btn-ghost" onClick={() => onAsk(job)}>
          ask
        </button>

        <div className="ml-auto flex items-center gap-2">
          {mode === "applied" && applied && (
            <span className="hidden text-[11px] sm:inline" style={{ color: "var(--ink-35)" }}>
              {job.appliedDate ? `applied ${job.appliedDate}` : ""}
            </span>
          )}
          {mode === "applied" ? (
            <StatusPill status={job.status} />
          ) : (
            applied && <StatusPill status={job.status} />
          )}
          <label className="sr-only" htmlFor={`status-${job.row}`}>
            change status
          </label>
          <select
            id={`status-${job.row}`}
            className="input h-8 px-2 text-[12px]"
            value={job.status || "New"}
            onChange={(e) => onStatus(job, e.target.value)}
            title="change this job's status"
          >
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
      </div>
    </article>
  );
}
