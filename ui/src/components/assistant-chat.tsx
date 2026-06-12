"use client";

import { useEffect, useRef, useState } from "react";

import type { Job } from "@/lib/types";

type Msg = { role: "user" | "model"; text: string; links?: { label: string; href: string }[] };

const STORE = "assistant-chat-v1";

export function AssistantChat({ initialJobId }: { initialJobId?: string }) {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [model, setModel] = useState<"flash" | "pro">("flash");
  const [busy, setBusy] = useState(false);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobId, setJobId] = useState(initialJobId ?? "");
  const [showPaste, setShowPaste] = useState(false);
  const [paste, setPaste] = useState({ company: "", title: "", url: "", jd: "" });
  const [generating, setGenerating] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(STORE) ?? "[]");
      if (Array.isArray(saved) && saved.length && !initialJobId) setMessages(saved);
    } catch { /* fresh start */ }
    fetch("/api/jobs").then((r) => r.json())
      .then((d) => d.jobs && setJobs(d.jobs as Job[])).catch(() => {});
  }, [initialJobId]);

  useEffect(() => {
    localStorage.setItem(STORE, JSON.stringify(messages.slice(-40)));
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const job = jobs.find((j) => j.id === jobId);
  const pasteReady = paste.company.trim() && paste.title.trim() && paste.jd.trim().length >= 100;

  function push(m: Msg) {
    setMessages((ms) => [...ms, m]);
  }

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    const history = [...messages, { role: "user" as const, text }];
    setMessages(history);
    setBusy(true);
    try {
      const res = await fetch("/api/assistant", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: history.map(({ role, text }) => ({ role, text })),
          model,
          jobId: jobId || undefined,
        }),
      });
      const d = await res.json();
      push({ role: "model", text: d.reply ?? `Something failed: ${d.error}` });
    } catch {
      push({ role: "model", text: "Request failed. Try again." });
    } finally {
      setBusy(false);
    }
  }

  function attachPaste() {
    if (!pasteReady) return;
    push({
      role: "user",
      text: `Here is the job I am working on.\nCompany: ${paste.company}\n` +
            `Title: ${paste.title}\n${paste.url ? `URL: ${paste.url}\n` : ""}` +
            `Job description:\n${paste.jd}`,
    });
    setShowPaste(false);
  }

  async function generateDocs() {
    if (generating) return;
    setGenerating(true);
    push({ role: "model",
           text: "Running the tailoring pipeline (judge loop, ATS check, Drive upload). " +
                 "Usually 1 to 3 minutes." });
    try {
      const body = jobId
        ? { jobId }
        : { company: paste.company, title: paste.title, url: paste.url, jd: paste.jd };
      const res = await fetch("/api/assistant/track", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.error);
      const id = d.jobId as string;
      const started = Date.now();
      const timer = setInterval(async () => {
        if (Date.now() - started > 6 * 60_000) {
          clearInterval(timer);
          setGenerating(false);
          push({ role: "model",
                 text: "Still not done after 6 minutes. Check the job's row in the Jobs tab." });
          return;
        }
        try {
          const jd = await (await fetch("/api/jobs")).json();
          const fresh = (jd.jobs as Job[] | undefined)?.find((x) => x.id === id);
          if (fresh?.tailoredResume) {
            clearInterval(timer);
            setGenerating(false);
            if (fresh.tailoredResume.startsWith("FAILED")) {
              push({ role: "model", text: `Tailoring failed: ${fresh.tailoredResume}` });
            } else {
              push({
                role: "model",
                text: `Done. ATS score ${fresh.resumeAts || "n/a"}. The job is now tracked in your Jobs tab.`,
                links: [
                  { label: "Resume PDF", href: fresh.tailoredResume },
                  ...(fresh.coverLetter ? [{ label: "Cover letter PDF", href: fresh.coverLetter }] : []),
                  ...(fresh.url ? [{ label: "Apply link", href: fresh.url }] : []),
                ],
              });
            }
          }
        } catch { /* keep polling */ }
      }, 10_000);
    } catch (e) {
      setGenerating(false);
      push({ role: "model", text: `Could not start the pipeline: ${e}` });
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="panel flex flex-wrap items-center gap-2 p-3 text-xs">
        <span style={{ color: "var(--text-dim)" }}>Job context:</span>
        <select className="panel cell-select px-2 py-1.5 text-xs" value={jobId}
                onChange={(e) => setJobId(e.target.value)}>
          <option value="">none (or paste below)</option>
          {jobs.map((j) => (
            <option key={j.id} value={j.id}>{j.company} — {j.title}</option>
          ))}
        </select>
        <button className="btn-ghost px-2 py-1 text-xs"
                onClick={() => setShowPaste((s) => !s)}>
          {showPaste ? "hide" : "+ paste an untracked job"}
        </button>
        <span className="ml-auto flex items-center gap-1">
          {(["flash", "pro"] as const).map((m) => (
            <button key={m} onClick={() => setModel(m)}
                    className="px-2 py-1 text-xs"
                    style={{
                      borderRadius: 6,
                      background: model === m ? "var(--amber)" : "transparent",
                      color: model === m ? "#000" : "var(--text-dim)",
                      border: "1px solid var(--text-faint)",
                    }}
                    title={m === "flash" ? "Gemini Flash — fast, cheap" : "Gemini Pro — best writing, pricier"}>
              {m}
            </button>
          ))}
        </span>
      </div>

      {showPaste && (
        <div className="panel flex flex-col gap-2 p-3">
          <div className="flex flex-wrap gap-2">
            <input className="panel px-2 py-1.5 text-xs" placeholder="Company"
                   value={paste.company}
                   onChange={(e) => setPaste({ ...paste, company: e.target.value })} />
            <input className="panel px-2 py-1.5 text-xs" placeholder="Job title"
                   value={paste.title}
                   onChange={(e) => setPaste({ ...paste, title: e.target.value })} />
            <input className="panel grow px-2 py-1.5 text-xs" placeholder="Apply URL (optional)"
                   value={paste.url}
                   onChange={(e) => setPaste({ ...paste, url: e.target.value })} />
          </div>
          <textarea className="panel min-h-28 px-2 py-1.5 text-xs"
                    placeholder="Paste the full job description here"
                    value={paste.jd}
                    onChange={(e) => setPaste({ ...paste, jd: e.target.value })} />
          <button className="btn-amber self-start" disabled={!pasteReady}
                  onClick={attachPaste}>
            Attach job to chat
          </button>
        </div>
      )}

      <div className="panel flex min-h-[40vh] flex-col gap-3 p-4">
        {messages.length === 0 && (
          <p className="text-xs" style={{ color: "var(--text-faint)" }}>
            I answer with your real background only: resume rewrites, cover letters,
            and application questions like &quot;Why this company?&quot; or &quot;Explain a
            project&quot; in STAR form. Pick a tracked job or paste one, then ask.
          </p>
        )}
        {messages.map((m, i) => (
          <div key={i} className="text-sm" style={{
            alignSelf: m.role === "user" ? "flex-end" : "flex-start",
            maxWidth: "85%",
            whiteSpace: "pre-wrap",
            background: m.role === "user" ? "var(--bg-raised, rgba(255,255,255,0.06))" : "transparent",
            borderLeft: m.role === "model" ? "2px solid var(--amber)" : "none",
            padding: "6px 10px",
            borderRadius: 8,
          }}>
            {m.text}
            {m.links && (
              <span className="mt-1 flex gap-3 text-xs">
                {m.links.map((l) => (
                  <a key={l.href} href={l.href} target="_blank" rel="noopener"
                     className="hover:underline" style={{ color: "var(--green)" }}>
                    {l.label} ↗
                  </a>
                ))}
              </span>
            )}
          </div>
        ))}
        {busy && <span className="blink text-xs" style={{ color: "var(--amber)" }}>thinking…</span>}
        <div ref={endRef} />
      </div>

      <div className="panel flex items-end gap-2 p-3">
        <textarea
          className="panel min-h-16 grow px-2 py-1.5 text-sm"
          placeholder="Ask for a resume rewrite, a cover letter, or an application answer…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
          }}
        />
        <div className="flex flex-col gap-2">
          <button className="btn-amber" disabled={busy || !input.trim()} onClick={send}>
            Send
          </button>
          {(job || pasteReady) && (
            <button className="btn-ghost px-2 py-1 text-xs" disabled={generating}
                    onClick={generateDocs}
                    title="Runs the real pipeline: LaTeX, ATS judge, Drive PDFs">
              {generating ? "generating…" : "⚙ Generate resume + cover PDFs"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
