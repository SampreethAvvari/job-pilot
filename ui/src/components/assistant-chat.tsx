"use client";

import { useEffect, useRef, useState } from "react";

import type { Job } from "@/lib/types";
import Button from "@/components/ui/button";

type Attachment = { mimeType: string; data: string; name: string };
type Msg = {
  role: "user" | "model";
  text: string;
  links?: { label: string; href: string }[];
  attachments?: Attachment[];
};

const FILE_TYPES = "image/png,image/jpeg,image/webp,application/pdf";
const MAX_FILE_MB = 10;

export function AssistantChat({
  initialJobId,
  lockedJob,
}: {
  initialJobId?: string;
  lockedJob?: Job; // per-job drawer: context fixed, selector/paste hidden
}) {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [model, setModel] = useState<"flash" | "pro">("flash");
  const [busy, setBusy] = useState(false);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobId, setJobId] = useState(lockedJob?.id ?? initialJobId ?? "");
  const [jobJd, setJobJd] = useState("");
  const [jdNote, setJdNote] = useState("");
  const [showPaste, setShowPaste] = useState(false);
  const [paste, setPaste] = useState({ company: "", title: "", url: "", jd: "" });
  const [generating, setGenerating] = useState(false);
  const [pending, setPending] = useState<Attachment[]>([]);
  const endRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (lockedJob) return; // selector not shown when the job is fixed
    fetch("/api/jobs").then((r) => r.json())
      .then((d) => d.jobs && setJobs(d.jobs as Job[])).catch(() => {});
  }, [lockedJob]);

  // Resolve the best JD (stored, else live-fetched from the posting) per job.
  useEffect(() => {
    let live = true;
    async function resolveJd() {
      if (!jobId) { setJobJd(""); setJdNote(""); return; }
      setJdNote("loading job description…");
      try {
        const d = await (
          await fetch(`/api/assistant/jd?jobId=${encodeURIComponent(jobId)}`)
        ).json();
        if (!live) return;
        setJobJd(d.jd ?? "");
        setJdNote(
          d.source === "fetched" ? "loaded full job description from the posting link"
            : d.source === "stored" ? "using the saved job description"
            : "no job description found. Paste it or attach a screenshot below.",
        );
      } catch {
        if (live) setJdNote("could not load the job description");
      }
    }
    resolveJd();
    return () => { live = false; };
  }, [jobId]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const job = lockedJob ?? jobs.find((j) => j.id === jobId);
  const pasteReady = paste.company.trim() && paste.title.trim() && paste.jd.trim().length >= 100;

  function push(m: Msg) {
    setMessages((ms) => [...ms, m]);
  }

  async function addFiles(files: FileList | null) {
    if (!files) return;
    for (const f of Array.from(files)) {
      if (f.size > MAX_FILE_MB * 1024 * 1024) {
        push({ role: "model", text: `${f.name} is over ${MAX_FILE_MB}MB, skipped.` });
        continue;
      }
      const data = await new Promise<string>((resolve, reject) => {
        const r = new FileReader();
        r.onload = () => resolve(String(r.result).split(",")[1] ?? "");
        r.onerror = reject;
        r.readAsDataURL(f);
      });
      setPending((p) => [...p, { mimeType: f.type, data, name: f.name }]);
    }
    if (fileRef.current) fileRef.current.value = "";
  }

  async function send() {
    const text = input.trim();
    if ((!text && pending.length === 0) || busy) return;
    setInput("");
    const userMsg: Msg = {
      role: "user",
      text: text || "See the attached file(s).",
      attachments: pending.length ? pending : undefined,
    };
    setPending([]);
    const history = [...messages, userMsg];
    setMessages(history);
    setBusy(true);
    try {
      const res = await fetch("/api/assistant", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: history.map(({ role, text, attachments }) => ({
            role, text,
            attachments: attachments?.map(({ mimeType, data }) => ({ mimeType, data })),
          })),
          model,
          jobId: jobId || undefined,
          jobJd: jobJd || undefined,
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

  function clearChat() {
    setMessages([]);
    setPending([]);
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
      <div className="card flex flex-wrap items-center gap-2 p-3 text-xs">
        {lockedJob ? (
          <span style={{ color: "var(--ink-55)" }}>
            Job: <b style={{ color: "var(--ink)" }}>{lockedJob.company}</b> · {lockedJob.title}
          </span>
        ) : (
          <>
            <span style={{ color: "var(--ink-55)" }}>Job context:</span>
            <select className="input text-xs" value={jobId}
                    onChange={(e) => setJobId(e.target.value)}>
              <option value="">none (or paste below)</option>
              {jobs.map((j) => (
                <option key={j.id} value={j.id}>{j.company} · {j.title}</option>
              ))}
            </select>
            <Button variant="ghost" size="sm" onClick={() => setShowPaste((s) => !s)}>
              {showPaste ? "hide" : "+ paste an untracked job"}
            </Button>
          </>
        )}
        <span className="ml-auto flex items-center gap-1">
          {messages.length > 0 && (
            <Button variant="ghost" size="sm" onClick={clearChat}
                    title="Start a fresh conversation, nothing is saved anyway">
              ⟳ clear chat
            </Button>
          )}
          {(["flash", "pro"] as const).map((m) => (
            <Button key={m} size="sm"
                    variant={model === m ? "primary" : "ghost"}
                    onClick={() => setModel(m)}
                    title={m === "flash"
                      ? "Gemini Flash, fast and cheap"
                      : "Gemini Pro, best writing but pricier"}>
              {m}
            </Button>
          ))}
        </span>
      </div>

      {jobId && jdNote && (
        <span className="px-1 text-[11px]" style={{ color: "var(--ink-35)" }}>
          {jdNote}
        </span>
      )}

      {showPaste && (
        <div className="card flex flex-col gap-2 p-3">
          <div className="flex flex-wrap gap-2">
            <input className="input text-xs" placeholder="Company"
                   value={paste.company}
                   onChange={(e) => setPaste({ ...paste, company: e.target.value })} />
            <input className="input text-xs" placeholder="Job title"
                   value={paste.title}
                   onChange={(e) => setPaste({ ...paste, title: e.target.value })} />
            <input className="input grow text-xs" placeholder="Apply URL (optional)"
                   value={paste.url}
                   onChange={(e) => setPaste({ ...paste, url: e.target.value })} />
          </div>
          <textarea className="input text-xs"
                    style={{ height: "auto", minHeight: "7rem", padding: "8px 12px", lineHeight: 1.5 }}
                    placeholder="Paste the full job description here"
                    value={paste.jd}
                    onChange={(e) => setPaste({ ...paste, jd: e.target.value })} />
          <Button className="self-start" disabled={!pasteReady} onClick={attachPaste}>
            Attach job to chat
          </Button>
        </div>
      )}

      <div className="card flex min-h-[40vh] flex-col gap-3 p-4">
        {messages.length === 0 && (
          <p className="text-xs" style={{ color: "var(--ink-35)" }}>
            I answer with your real background only: resume rewrites, cover letters,
            and application questions like &quot;Why this company?&quot; or &quot;Explain a
            project&quot; in STAR form. Pick a tracked job or paste one, then ask.
          </p>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className={m.role === "model" ? "card text-sm" : "text-sm"}
            style={{
              alignSelf: m.role === "user" ? "flex-end" : "flex-start",
              maxWidth: "85%",
              whiteSpace: "pre-wrap",
              color: "var(--ink)",
              background: m.role === "user" ? "var(--blue-soft)" : undefined,
              borderLeft: m.role === "model" ? "2px solid var(--blue)" : undefined,
              padding: "8px 12px",
              borderRadius: m.role === "user" ? 12 : undefined,
            }}
          >
            {m.attachments && m.attachments.length > 0 && (
              <span className="mb-1 flex flex-wrap gap-1 text-[10px]"
                    style={{ color: "var(--ink-55)" }}>
                {m.attachments.map((a, k) => <span key={k}>📎 {a.name}</span>)}
              </span>
            )}
            {m.text}
            {m.links && (
              <span className="mt-1 flex gap-3 text-xs">
                {m.links.map((l) => (
                  <a key={l.href} href={l.href} target="_blank" rel="noopener"
                     className="hover:underline" style={{ color: "var(--emerald)" }}>
                    {l.label} ↗
                  </a>
                ))}
              </span>
            )}
          </div>
        ))}
        {busy && <span className="blink text-xs" style={{ color: "var(--blue)" }}>thinking…</span>}
        <div ref={endRef} />
      </div>

      <div className="card flex flex-col gap-2 p-3">
        {pending.length > 0 && (
          <span className="flex flex-wrap gap-2 text-[11px]" style={{ color: "var(--ink-55)" }}>
            {pending.map((a, k) => (
              <span key={k} className="flex items-center gap-1">
                📎 {a.name}
                <button onClick={() => setPending((p) => p.filter((_, i) => i !== k))}
                        style={{ color: "var(--rose)" }}>✕</button>
              </span>
            ))}
          </span>
        )}
        <div className="flex items-end gap-2">
        <textarea
          className="input grow text-sm"
          style={{ height: "auto", minHeight: "4rem", padding: "8px 12px", lineHeight: 1.5 }}
          placeholder="Ask for a resume rewrite, a cover letter, or an application answer…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
          }}
        />
        <div className="flex flex-col gap-2">
          <input ref={fileRef} type="file" multiple accept={FILE_TYPES} hidden
                 onChange={(e) => addFiles(e.target.files)} />
          <Button variant="ghost" size="sm"
                  onClick={() => fileRef.current?.click()}
                  title="Attach screenshots or PDFs (JD screenshots, your current resume)">
            📎 attach
          </Button>
          <Button disabled={busy || (!input.trim() && pending.length === 0)} onClick={send}>
            Send
          </Button>
          {(job || pasteReady) && (
            <Button variant="ghost" size="sm" busy={generating} onClick={generateDocs}
                    title="Runs the real pipeline: LaTeX, ATS judge, Drive PDFs">
              {generating ? "generating…" : "⚙ Generate resume + cover PDFs"}
            </Button>
          )}
        </div>
        </div>
      </div>
    </div>
  );
}
