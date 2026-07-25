"use client";

import { useCallback, useEffect, useState } from "react";

import Badge from "@/components/ui/badge";
import Button from "@/components/ui/button";
import Card from "@/components/ui/card";

type RunState = "RUNNING" | "SUCCEEDED" | "FAILED" | "NONE";

const STATE_TONE: Record<RunState, "amber" | "emerald" | "rose" | "neutral"> = {
  RUNNING: "amber",
  SUCCEEDED: "emerald",
  FAILED: "rose",
  NONE: "neutral",
};

const STATE_LABEL: Record<RunState, string> = {
  RUNNING: "Running",
  SUCCEEDED: "Succeeded",
  FAILED: "Failed",
  NONE: "No runs yet",
};

export function KnowledgePanel() {
  const [state, setState] = useState<RunState>("NONE");
  const [started, setStarted] = useState("");

  const refresh = useCallback(async () => {
    try {
      const res = await fetch("/api/portfolio-graph");
      const data = (await res.json()) as { state: RunState; started: string };
      setState(data.state);
      setStarted(data.started);
    } catch {
      /* keep the last known state and try again on the next poll */
    }
  }, []);

  // Load the current state on mount (declared inline so the effect body
  // itself never invokes a setState-bearing function synchronously).
  useEffect(() => {
    let live = true;
    fetch("/api/portfolio-graph")
      .then((r) => r.json())
      .then((data: { state: RunState; started: string }) => {
        if (!live) return;
        setState(data.state);
        setStarted(data.started);
      })
      .catch(() => {
        /* keep the last known state and try again on the next poll */
      });
    return () => {
      live = false;
    };
  }, []);

  // Poll while a run is in flight, and stop as soon as it leaves RUNNING.
  useEffect(() => {
    if (state !== "RUNNING") return;
    const id = setInterval(refresh, 15000);
    return () => clearInterval(id);
  }, [state, refresh]);

  async function rebuild() {
    setState("RUNNING");
    try {
      await fetch("/api/portfolio-graph", { method: "POST" });
    } finally {
      refresh();
    }
  }

  return (
    <Card className="flex flex-col items-start gap-3 p-5">
      <Button busy={state === "RUNNING"} onClick={rebuild}>
        {state === "RUNNING" ? "Rebuilding…" : "Rebuild portfolio knowledge"}
      </Button>
      <div className="flex flex-wrap items-center gap-2 text-xs" style={{ color: "var(--ink-55)" }}>
        <span>Last run</span>
        <span className={state === "RUNNING" ? "blink" : undefined}>
          <Badge tone={STATE_TONE[state]}>{STATE_LABEL[state]}</Badge>
        </span>
        {started && <span>{new Date(started).toLocaleString()}</span>}
      </div>
    </Card>
  );
}

export function RepoKnowledgePanel() {
  const [state, setState] = useState<RunState>("NONE");
  const [started, setStarted] = useState("");

  const refresh = useCallback(async () => {
    try {
      const res = await fetch("/api/repo-graph");
      const data = (await res.json()) as { state: RunState; started: string };
      setState(data.state);
      setStarted(data.started);
    } catch {
      /* keep the last known state and try again on the next poll */
    }
  }, []);

  // Load the current state on mount (declared inline so the effect body
  // itself never invokes a setState-bearing function synchronously).
  useEffect(() => {
    let live = true;
    fetch("/api/repo-graph")
      .then((r) => r.json())
      .then((data: { state: RunState; started: string }) => {
        if (!live) return;
        setState(data.state);
        setStarted(data.started);
      })
      .catch(() => {
        /* keep the last known state and try again on the next poll */
      });
    return () => {
      live = false;
    };
  }, []);

  // Poll while a run is in flight, and stop as soon as it leaves RUNNING.
  useEffect(() => {
    if (state !== "RUNNING") return;
    const id = setInterval(refresh, 15000);
    return () => clearInterval(id);
  }, [state, refresh]);

  async function rebuild() {
    setState("RUNNING");
    try {
      await fetch("/api/repo-graph", { method: "POST" });
    } finally {
      refresh();
    }
  }

  return (
    <Card className="flex flex-col items-start gap-3 p-5">
      <Button busy={state === "RUNNING"} onClick={rebuild}>
        {state === "RUNNING" ? "Rebuilding…" : "Rebuild repo knowledge"}
      </Button>
      <p className="text-xs" style={{ color: "var(--ink-55)" }}>
        Crawls your GitHub contributions and refreshes the repo graph.
      </p>
      <div className="flex flex-wrap items-center gap-2 text-xs" style={{ color: "var(--ink-55)" }}>
        <span>Last run</span>
        <span className={state === "RUNNING" ? "blink" : undefined}>
          <Badge tone={STATE_TONE[state]}>{STATE_LABEL[state]}</Badge>
        </span>
        {started && <span>{new Date(started).toLocaleString()}</span>}
      </div>
    </Card>
  );
}
