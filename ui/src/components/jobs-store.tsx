"use client";

// One shared client store for the Jobs sheet, replacing five independent
// pollers (jobs-table, replies-view, etc.) that each fetched /api/jobs on
// their own timer. Ported semantics from the old jobs-table.tsx:
//   - pushUpdate: lib/update.ts (verbatim copy of the old inline helper)
//   - mutate: optimistic setState + revert on failure (old lines 159-167)
//   - pollUntil: the runJobAction poll loop (old lines 60-89), split so the
//     caller fires the trigger fetch itself and just asks the store to poll.

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

import type { Job } from "@/lib/types";
import { pushUpdate } from "@/lib/update";

type BusyKind = "tailor" | "draft";

type JobsContextValue = {
  jobs: Job[];
  refresh: () => Promise<void>;
  mutate: (row: number, local: Partial<Job>, sheet: Record<string, string>) => void;
  busyTailor: Set<number>;
  busyDraft: Set<number>;
  markBusy: (kind: BusyKind, row: number) => void;
  pollUntil: (row: number, col: BusyKind, predicate: (j: Job) => boolean) => void;
  error: string;
};

const JobsContext = createContext<JobsContextValue | null>(null);

export function JobsProvider({
  initial,
  children,
}: {
  initial: Job[];
  children: ReactNode;
}) {
  const [jobs, setJobs] = useState<Job[]>(initial);
  const [error, setError] = useState("");
  const [busyTailor, setBusyTailor] = useState<Set<number>>(new Set());
  const [busyDraft, setBusyDraft] = useState<Set<number>>(new Set());
  // Active pollUntil interval handles, so the provider can clear every
  // outstanding timer on unmount instead of letting them run past it.
  const pollTimers = useRef<Set<ReturnType<typeof setInterval>>>(new Set());

  const refresh = useCallback(async () => {
    try {
      const d = await (await fetch("/api/jobs")).json();
      if (d.jobs) setJobs(d.jobs as Job[]);
    } catch {
      /* keep the last good state on a transient failure */
    }
  }, []);

  // Single 60s poller for the whole console — was five independent ones.
  useEffect(() => {
    const t = setInterval(refresh, 60_000);
    return () => {
      clearInterval(t);
      // Intentionally reading the ref's live value at cleanup time, not a
      // snapshot from when this effect ran: pollTimers is a mutable timer
      // registry (populated later by pollUntil calls), not a DOM node ref,
      // so we want whatever is outstanding right now.
      // eslint-disable-next-line react-hooks/exhaustive-deps
      const timers = pollTimers.current;
      for (const handle of timers) clearInterval(handle);
      timers.clear();
    };
  }, [refresh]);

  // Optimistic update, revert + banner on failure — ported from
  // jobs-table.tsx:159-167, but the revert now targets only the mutated
  // row (functionally, via setJobs(js => ...)) so it composes with
  // concurrent edits — e.g. the 60s refresh or another row's own mutate —
  // landing in between, instead of clobbering the whole array back to a
  // stale snapshot.
  const mutate = useCallback(
    (row: number, local: Partial<Job>, sheet: Record<string, string>) => {
      const prevRow = jobs.find((j) => j.row === row);
      setJobs((js) => js.map((j) => (j.row === row ? { ...j, ...local } : j)));
      pushUpdate(row, sheet).catch(() => {
        setJobs((js) => js.map((j) => (j.row === row && prevRow ? prevRow : j)));
        setError("Save failed — change reverted. Try again.");
        setTimeout(() => setError(""), 5000);
      });
    },
    [jobs],
  );

  const markBusy = useCallback((kind: BusyKind, row: number) => {
    const setBusy = kind === "tailor" ? setBusyTailor : setBusyDraft;
    setBusy((s) => new Set(s).add(row));
  }, []);

  // Exact port of jobs-table.tsx:60-89's poll loop (runJobAction), minus the
  // trigger fetch — the caller does `markBusy` + its own POST, then calls
  // this to poll for completion.
  const pollUntil = useCallback(
    (row: number, col: BusyKind, predicate: (j: Job) => boolean) => {
      const setBusy = col === "tailor" ? setBusyTailor : setBusyDraft;
      const started = Date.now();
      const stop = () => {
        clearInterval(t);
        pollTimers.current.delete(t);
      };
      const t = setInterval(async () => {
        if (Date.now() - started > 4 * 60_000) {
          stop();
          setBusy((s) => {
            const n = new Set(s);
            n.delete(row);
            return n;
          });
          return;
        }
        try {
          const d = await (await fetch("/api/jobs")).json();
          const fresh = (d.jobs as Job[] | undefined)?.find((x) => x.row === row);
          if (fresh && predicate(fresh)) {
            stop();
            setJobs((js) => js.map((x) => (x.row === row ? { ...x, ...fresh } : x)));
            setBusy((s) => {
              const n = new Set(s);
              n.delete(row);
              return n;
            });
          }
        } catch {
          /* keep polling */
        }
      }, 15_000);
      pollTimers.current.add(t);
    },
    [],
  );

  const value: JobsContextValue = {
    jobs,
    refresh,
    mutate,
    busyTailor,
    busyDraft,
    markBusy,
    pollUntil,
    error,
  };

  return <JobsContext.Provider value={value}>{children}</JobsContext.Provider>;
}

export function useJobs(): JobsContextValue {
  const ctx = useContext(JobsContext);
  if (!ctx) throw new Error("useJobs must be used within a JobsProvider");
  return ctx;
}

/** Same context, but tolerant of missing provider — nav.tsx uses this so it
 * can reuse the shared jobs list on job pages while falling back to its own
 * fetch on pages that never mount a JobsProvider. */
export function useJobsOptional(): JobsContextValue | null {
  return useContext(JobsContext);
}
