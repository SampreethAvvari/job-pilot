"use client";

// Dashboard's "Fresh matches" rail: real JobCards reading off the shared
// jobs store, so dismiss / apply / tailor / draft / ask work right from the
// homepage. Filtering (passesFit + within 72h, top 6 by effectiveRecency) is
// this component's own job; the interaction handlers are not — those come
// from `useJobActions` in jobs-view.tsx so the dashboard and the full Jobs
// registry never drift apart.

import { AssistantDrawer } from "./assistant-drawer";
import JobCard from "./job-card";
import { ConfirmApplyModal, useJobActions } from "./jobs-view";
import { useJobs } from "./jobs-store";
import EmptyState from "./ui/empty-state";
import { MIN_FIT, effectiveRecency, passesFit, withinRecency } from "@/lib/company-match";

const FRESH_HOURS = 72;
const FRESH_LIMIT = 6;

export default function FreshMatches({
  resumeLinks = {},
}: {
  resumeLinks?: Record<string, string>;
}) {
  const { jobs } = useJobs();
  const {
    busyTailor,
    busyDraft,
    dismiss,
    openPosting,
    confirmApplied,
    tailor,
    draft,
    setStatusManual,
    confirmJob,
    setConfirmJob,
    chatJob,
    setChatJob,
  } = useJobActions();

  const fresh = jobs
    .filter((j) => (j.status === "" || j.status === "New") && passesFit(j, MIN_FIT))
    .filter((j) => withinRecency(j, FRESH_HOURS))
    .sort((a, b) => effectiveRecency(b) - effectiveRecency(a))
    .slice(0, FRESH_LIMIT);

  if (fresh.length === 0) {
    return (
      <EmptyState
        title="Nothing fresh right now"
        hint="Postings above the fit floor land every 30 minutes. Check back soon."
      />
    );
  }

  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {fresh.map((j) => (
          <JobCard
            key={j.row}
            job={j}
            mode="open"
            resumeLinks={resumeLinks}
            busyTailor={busyTailor.has(j.row)}
            busyDraft={busyDraft.has(j.row)}
            onDismiss={dismiss}
            onApply={openPosting}
            onTailor={tailor}
            onDraft={draft}
            onAsk={setChatJob}
            onStatus={setStatusManual}
          />
        ))}
      </div>

      <ConfirmApplyModal
        confirmJob={confirmJob}
        setConfirmJob={setConfirmJob}
        confirmApplied={confirmApplied}
      />

      {chatJob && (
        <AssistantDrawer key={chatJob.id} job={chatJob} onClose={() => setChatJob(null)} />
      )}
    </>
  );
}
