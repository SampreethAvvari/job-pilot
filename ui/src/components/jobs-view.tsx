"use client";

// The jobs grid + filter/sort bar. Replaces the old jobs-table render path;
// the `visible` filter/sort pipeline is ported from jobs-table.tsx (the
// pre-redesign semantics reference) with the freshness-first defaults from
// Task 9: 75 fit floor, a 14 day posted window, and posted-recency sort.
//
// Interaction handlers (dismiss / apply / tailor / draft / ask / status) are
// Task 10, wired here off the shared store. The flows are ported from the
// pre-redesign jobs-table.tsx (the semantics reference):
//   - dismiss + undo toast: optimistic mutate, revert via the toast action
//   - apply: openPosting + window-focus confirm modal (old lines 100-112, 174-178, 444-487)
//   - tailor / draft: markBusy + POST + pollUntil for the value change (old lines 59-98)
//   - status select: setStatusManual with the Applied date stamp (old lines 180-186)

import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";

import JobCard from "./job-card";
import { AssistantDrawer } from "./assistant-drawer";
import { FilterBar, Segmented } from "./ui/filter-bar";
import EmptyState from "./ui/empty-state";
import Skeleton from "./ui/skeleton";
import Modal from "./ui/modal";
import Button from "./ui/button";
import { useToast } from "./ui/toast";
import { useJobs } from "./jobs-store";
import {
  MIN_FIT,
  effectiveRecency,
  norm,
  passesFit,
  withinRecency,
} from "@/lib/company-match";
import { companySize, SIZE_BUCKETS } from "@/lib/company-size";
import { isApplied } from "@/lib/status-sets";
import { ROLES, STATUSES } from "@/lib/types";
import type { Job } from "@/lib/types";

type Mode = "open" | "applied";
type SortKey = "recent" | "fit" | "found";

interface JobsViewProps {
  mode: Mode;
  defaultStatus?: string;
  resumeLinks?: Record<string, string>;
  /**
   * Normalized company-name aliases (from `companyAliases` on the server).
   * When set, only jobs whose normalized company matches one of these show.
   * We pass the whole alias set, not a single name, so the client re-filter
   * stays in step with the server's `jobsForCompany` slug-alias match even
   * after the shared store's 60s refresh refetches every job.
   */
  companyAliases?: string[];
}

const FIT_OPTIONS = [0, 60, 70, 75, 80, 90];
const POSTED_OPTIONS: { value: number; label: string }[] = [
  { value: 24, label: "24h" },
  { value: 72, label: "3d" },
  { value: 168, label: "7d" },
  { value: 336, label: "14d" },
  { value: 0, label: "all" },
];
const SORT_OPTIONS = [
  { value: "recent", label: "recent" },
  { value: "fit", label: "best fit" },
  { value: "found", label: "newest found" },
];

/** Local date stamp, YYYY-MM-DD. Ported from jobs-table.tsx:24-26. */
function today(): string {
  return new Date().toISOString().slice(0, 10);
}

function SkeletonCard() {
  return (
    <div className="card flex flex-col gap-3 p-5">
      <div className="flex items-start gap-3">
        <Skeleton className="h-11 w-11 rounded-full" />
        <div className="flex-1">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="mt-2 h-4 w-4/5" />
          <Skeleton className="mt-2 h-3 w-3/5" />
        </div>
      </div>
      <Skeleton className="h-3 w-full" />
      <Skeleton className="h-3 w-11/12" />
      <div className="mt-2 flex gap-2 border-t pt-3" style={{ borderColor: "var(--line)" }}>
        <Skeleton className="h-7 w-20" />
        <Skeleton className="h-7 w-16" />
      </div>
    </div>
  );
}

export default function JobsView({
  mode,
  defaultStatus,
  resumeLinks = {},
  companyAliases,
}: JobsViewProps) {
  const { jobs, busyTailor, busyDraft, error, mutate, markBusy, pollUntil } = useJobs();
  const toast = useToast();

  // The store seeds synchronously from the server payload, so a populated
  // list never flashes skeletons. `loaded` only guards the genuinely-empty
  // first paint (SSR + hydrate) before we know the list is really empty.
  // useSyncExternalStore gives the canonical mount flag (false on the server,
  // true after hydration) without a setState-in-effect.
  const loaded = useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );

  const [q, setQ] = useState("");
  const [status, setStatus] = useState(defaultStatus ?? (mode === "open" ? "New" : "all"));
  const [source, setSource] = useState("all");
  const [role, setRole] = useState("all");
  const [size, setSize] = useState("all");
  const [minFit, setMinFit] = useState(mode === "open" ? MIN_FIT : 0);
  const [postedWithin, setPostedWithin] = useState(mode === "open" ? 336 : 0);
  const [sortBy, setSortBy] = useState<SortKey>("recent");

  // Apply flow: the posting opens in a new tab, and one job at a time is held
  // in `pendingRef`. When the window regains focus we surface the confirm
  // modal for that job. Only one pending confirm exists at a time — opening a
  // second posting replaces the first — so the single focus listener never
  // stacks confirms (ported from jobs-table.tsx:52-53,100-112,174-178).
  const pendingRef = useRef<Job | null>(null);
  const [confirmJob, setConfirmJob] = useState<Job | null>(null);
  const [chatJob, setChatJob] = useState<Job | null>(null);

  useEffect(() => {
    const onFocus = () => {
      if (pendingRef.current) {
        setConfirmJob(pendingRef.current);
        pendingRef.current = null;
      }
    };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, []);

  // Optimistic status -> Dismissed with a "dismissed: not relevant" note; the
  // card leaves the grid at once (the `visible` memo excludes Dismissed). The
  // toast's Undo restores the prior status and clears the note.
  function dismiss(job: Job) {
    const prev = job.status;
    mutate(
      job.row,
      { status: "Dismissed" },
      { Status: "Dismissed", Notes: "dismissed: not relevant" },
    );
    toast({
      message: `Dismissed ${job.company}. It will not come back.`,
      actionLabel: "Undo",
      onAction: () => mutate(job.row, { status: prev }, { Status: prev, Notes: "" }),
    });
  }

  function openPosting(job: Job) {
    pendingRef.current = job;
    window.open(job.url, "_blank", "noopener");
  }

  function confirmApplied(job: Job) {
    const d = job.appliedDate || today();
    mutate(
      job.row,
      { status: "Applied", appliedDate: d },
      { Status: "Applied", "Applied date": d },
    );
    setConfirmJob(null);
  }

  // Fire the trigger POST, mark the row busy, then poll for the value CHANGE.
  // Waiting for a change (not just presence) lets a retry on a FAILED row
  // resolve when the marker flips (ported from jobs-table.tsx:90-96).
  function tailor(job: Job) {
    const before = job.tailoredResume;
    markBusy("tailor", job.row);
    fetch("/api/tailor", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jobId: job.id }),
    }).catch(() => {});
    pollUntil(job.row, "tailor", (j) => Boolean(j.tailoredResume) && j.tailoredResume !== before);
  }

  function draft(job: Job) {
    markBusy("draft", job.row);
    fetch("/api/outreach", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jobId: job.id }),
    }).catch(() => {});
    pollUntil(job.row, "draft", (j) => Boolean(j.draft));
  }

  // Manual status change; moving to Applied stamps today's date once
  // (ported from jobs-table.tsx:180-186).
  function setStatusManual(job: Job, v: string) {
    const stampDate = v === "Applied" && !job.appliedDate;
    const extra: Record<string, string> = stampDate ? { "Applied date": today() } : {};
    mutate(
      job.row,
      { status: v, appliedDate: stampDate ? today() : job.appliedDate },
      { Status: v, ...extra },
    );
  }

  const scoped = useMemo(() => {
    if (!companyAliases) return jobs;
    const set = new Set(companyAliases);
    return jobs.filter((j) => set.has(norm(j.company)));
  }, [jobs, companyAliases]);

  const sources = useMemo(
    () => Array.from(new Set(scoped.map((j) => j.source))).filter(Boolean).sort(),
    [scoped],
  );

  const statusOptions =
    mode === "open" ? ["all", ...STATUSES] : ["all", ...STATUSES.filter(isApplied), "Rejected"];

  const visible = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return scoped
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
      .filter((j) => size === "all" || companySize(j.company) === size)
      .filter((j) => (mode === "applied" ? true : passesFit(j, minFit)))
      .filter((j) => {
        if (mode === "applied" || !postedWithin) return true;
        return withinRecency(j, postedWithin);
      })
      .filter(
        (j) =>
          !needle || `${j.title} ${j.company} ${j.location}`.toLowerCase().includes(needle),
      )
      .sort((a, b) => {
        if (mode === "applied") {
          return (b.appliedDate || b.dateFound).localeCompare(a.appliedDate || a.dateFound);
        }
        if (sortBy === "fit") return (b.fit ?? -1) - (a.fit ?? -1);
        if (sortBy === "found") {
          return (b.dateFound + String(b.fit ?? -1).padStart(3, "0")).localeCompare(
            a.dateFound + String(a.fit ?? -1).padStart(3, "0"),
          );
        }
        // "recent": real posted age, freshest first
        return effectiveRecency(b) - effectiveRecency(a);
      });
  }, [scoped, mode, q, status, source, role, size, minFit, postedWithin, sortBy]);

  const selectClass = "input h-9 text-[12.5px]";

  return (
    <div className="rise flex flex-col gap-4">
      <FilterBar>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="search title, company, location"
          className="input w-56"
          aria-label="search jobs"
        />

        <select
          className={selectClass}
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          aria-label="filter by status"
        >
          {statusOptions.map((s) => (
            <option key={s} value={s}>
              {s === "all" ? "status: all" : s}
            </option>
          ))}
        </select>

        <select
          className={selectClass}
          value={source}
          onChange={(e) => setSource(e.target.value)}
          aria-label="filter by source"
        >
          <option value="all">source: all</option>
          {sources.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>

        <select
          className={selectClass}
          value={role}
          onChange={(e) => setRole(e.target.value)}
          aria-label="filter by role"
        >
          <option value="all">role: all</option>
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>

        <select
          className={selectClass}
          value={size}
          onChange={(e) => setSize(e.target.value)}
          aria-label="filter by company size"
          title="company size, best effort by company name"
        >
          <option value="all">size: all</option>
          {SIZE_BUCKETS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>

        {mode === "open" && (
          <>
            <select
              className={selectClass}
              value={minFit}
              onChange={(e) => setMinFit(Number(e.target.value))}
              aria-label="minimum fit"
            >
              {FIT_OPTIONS.map((n) => (
                <option key={n} value={n}>
                  {n === 0 ? "fit: any" : `fit ≥ ${n}`}
                </option>
              ))}
            </select>

            <select
              className={selectClass}
              value={postedWithin}
              onChange={(e) => setPostedWithin(Number(e.target.value))}
              aria-label="posted within"
            >
              {POSTED_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  posted: {o.label}
                </option>
              ))}
            </select>

            <Segmented
              value={sortBy}
              onChange={(v) => setSortBy(v as SortKey)}
              options={SORT_OPTIONS}
            />
          </>
        )}

        <span className="eyebrow ml-auto whitespace-nowrap">{visible.length} shown</span>
      </FilterBar>

      {error && (
        <div
          className="card px-4 py-2.5 text-[13px]"
          style={{ borderColor: "var(--rose)", color: "var(--rose)" }}
          role="alert"
        >
          {error}
        </div>
      )}

      {scoped.length === 0 && !loaded ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      ) : visible.length === 0 ? (
        <EmptyState title="No jobs match" hint="Fresh postings land every 30 minutes." />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {visible.map((j) => (
            <JobCard
              key={j.row}
              job={j}
              mode={mode}
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
      )}

      <Modal open={confirmJob !== null} onClose={() => setConfirmJob(null)} width={420}>
        {confirmJob && (
          <div>
            <p className="eyebrow">confirm application</p>
            <h2
              className="mt-2 font-semibold"
              style={{ fontFamily: "var(--font-archivo)", fontSize: 20, color: "var(--ink)" }}
            >
              Did you apply to {confirmJob.company}?
            </h2>
            <p className="mt-1 text-[13px]" style={{ color: "var(--ink-55)" }}>
              {[confirmJob.title, confirmJob.location].filter(Boolean).join(" · ")}
            </p>
            <div className="mt-5 flex gap-2">
              <Button
                variant="primary"
                size="sm"
                autoFocus
                onClick={() => confirmApplied(confirmJob)}
              >
                Yes, applied
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setConfirmJob(null)}>
                Not yet
              </Button>
            </div>
          </div>
        )}
      </Modal>

      {chatJob && (
        <AssistantDrawer key={chatJob.id} job={chatJob} onClose={() => setChatJob(null)} />
      )}
    </div>
  );
}
