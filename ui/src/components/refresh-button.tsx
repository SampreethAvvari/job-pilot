"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import Button from "@/components/ui/button";

type State = "idle" | "starting" | "running" | "done" | "failed";

export function RefreshButton() {
  const [state, setState] = useState<State>("idle");
  const [elapsed, setElapsed] = useState(0);
  const startedAt = useRef(0);
  const router = useRouter();
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = () => {
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
  };

  const poll = useCallback(() => {
    stopPolling();
    if (!startedAt.current) startedAt.current = Date.now();
    timer.current = setInterval(async () => {
      setElapsed(Math.floor((Date.now() - startedAt.current) / 60000));
      try {
        const res = await fetch("/api/refresh");
        const data = await res.json();
        if (data.state === "RUNNING") return;
        stopPolling();
        startedAt.current = 0;
        setState(data.state === "FAILED" ? "failed" : "done");
        router.refresh();
        setTimeout(() => setState("idle"), 5000);
      } catch {
        /* keep polling */
      }
    }, 8000);
  }, [router]);

  useEffect(() => {
    // Surface an already-running pipeline on load.
    fetch("/api/refresh")
      .then((r) => r.json())
      .then((d) => {
        if (d.state === "RUNNING") {
          setState("running");
          poll();
        }
      })
      .catch(() => {});
    return stopPolling;
  }, [poll]);

  async function trigger() {
    setState("starting");
    try {
      const res = await fetch("/api/refresh", { method: "POST" });
      if (!res.ok) throw new Error();
      setState("running");
      poll();
    } catch {
      setState("failed");
      setTimeout(() => setState("idle"), 5000);
    }
  }

  const busy = state === "starting" || state === "running";
  const label = {
    idle: "⟳ Refresh jobs",
    starting: "Starting…",
    running: `Fetching fresh jobs… ${elapsed}m (takes ~3 to 6 min)`,
    done: "✓ Done. New jobs are in.",
    failed: "✗ Run failed",
  }[state];

  return (
    <Button variant="ghost" size="sm" onClick={trigger} busy={busy}
            title="Fetch and score fresh jobs from all sources now">
      {label}
    </Button>
  );
}
