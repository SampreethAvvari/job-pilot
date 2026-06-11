"use client";

import { useState } from "react";
import { createPortal } from "react-dom";
import { useRouter } from "next/navigation";

import type { AtsReport } from "@/lib/reports";

export type ResumeCardData = {
  variant: string;
  title: string;
  blurb: string;
  pdfId?: string;
  docId?: string;
};

function scoreColor(score: number) {
  return score >= 90 ? "var(--green)" : score >= 75 ? "var(--amber)" : "var(--red)";
}

export function ResumeCard({ data, report }: { data: ResumeCardData; report: AtsReport | null }) {
  const [open, setOpen] = useState(false);
  const [rebuilding, setRebuilding] = useState(false);
  const router = useRouter();
  const r = report?.report;

  function regenerate() {
    setRebuilding(true);
    fetch("/api/rebuild", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ variant: data.variant }),
    }).catch(() => {});
    const started = Date.now();
    const t = setInterval(async () => {
      if (Date.now() - started > 12 * 60_000) {
        clearInterval(t);
        setRebuilding(false);
        return;
      }
      try {
        const d = await (await fetch(`/api/reports?kind=master&key=${data.variant}`)).json();
        if (d.timestamp && d.timestamp !== report?.timestamp) {
          clearInterval(t);
          setRebuilding(false);
          router.refresh();
        }
      } catch { /* keep polling */ }
    }, 20_000);
  }

  return (
    <div className="panel p-5">
      <div className="flex items-start justify-between">
        <div>
          <div className="display text-3xl font-extrabold" style={{ color: "var(--amber)" }}>
            {data.variant}
          </div>
          <div className="mt-1 font-semibold">{data.title}</div>
          <div className="mt-1 text-[11px]" style={{ color: "var(--text-faint)" }}>
            {data.blurb}
          </div>
        </div>
        {report && (
          <button onClick={() => setOpen(true)} className="text-right"
                  title="Open PDF + full ATS report">
            <div className="display text-2xl font-extrabold"
                 style={{ color: scoreColor(report.score) }}>
              {report.score}
            </div>
            <div className="eyebrow">ats report ↗</div>
          </button>
        )}
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        {data.pdfId && (
          <a className="btn-amber px-3 py-1.5 text-[11px]" href={`/api/resume/${data.variant}`}>
            ⬇ Download PDF
          </a>
        )}
        {report && (
          <button onClick={() => setOpen(true)} className="btn-ghost px-3 py-1.5 text-[11px]">
            ATS report
          </button>
        )}
        {data.docId && (
          <a className="btn-ghost px-3 py-1.5 text-[11px]"
             href={`https://docs.google.com/document/d/${data.docId}/edit`}
             target="_blank" rel="noopener">
            Source Doc ↗
          </a>
        )}
        <button onClick={regenerate} disabled={rebuilding}
                className="btn-ghost px-3 py-1.5 text-[11px]"
                title="Up to 10 judge-guided rewrites; published only if the score improves">
          {rebuilding ? <span className="blink">↻ regenerating…</span> : "↻ Regenerate"}
        </button>
      </div>

      {open && typeof document !== "undefined" && createPortal(
        <div style={{ position: "fixed", inset: 0, zIndex: 9999, display: "flex",
                      alignItems: "center", justifyContent: "center",
                      background: "rgba(5,7,9,0.85)" }}
             onClick={() => setOpen(false)}>
          <div onClick={(e) => e.stopPropagation()}
               style={{ width: "94vw", maxWidth: 1300, height: "88vh",
                        background: "#0e1318", borderRadius: 12, overflow: "hidden",
                        border: "1px solid rgba(255,176,0,0.35)", display: "flex" }}>
            <div style={{ flex: "1 1 55%", borderRight: "1px solid rgba(255,255,255,0.08)" }}>
              <iframe src={`/api/resume/${data.variant}?inline=1`}
                      title={`${data.variant} resume`}
                      style={{ width: "100%", height: "100%", border: 0,
                               background: "#fff" }} />
            </div>
            <div style={{ flex: "1 1 45%", padding: 20, overflowY: "auto",
                          color: "var(--text)" }}>
              <div className="flex items-start justify-between">
                <div>
                  <div className="eyebrow">ats report · {data.variant}</div>
                  <div className="display text-4xl font-extrabold"
                       style={{ color: scoreColor(report?.score ?? 0) }}>
                    {report?.score}<span className="text-base font-normal"
                                         style={{ color: "var(--text-faint)" }}>/100</span>
                  </div>
                </div>
                <button onClick={() => setOpen(false)}
                        className="btn-ghost px-3 py-1 text-xs">✕ close</button>
              </div>
              {r && (
                <>
                  <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
                    {Object.entries(r.breakdown).map(([k, v]) => (
                      <div key={k} className="panel px-3 py-2">
                        <div className="eyebrow">{k.replace("_", " ")}</div>
                        <div className="font-bold">{v}</div>
                      </div>
                    ))}
                    <div className="panel px-3 py-2">
                      <div className="eyebrow">keywords</div>
                      <div className="font-bold">{Math.round(r.keyword_coverage * 100)}%</div>
                    </div>
                    <div className="panel px-3 py-2">
                      <div className="eyebrow">pages / words / attempts</div>
                      <div className="font-bold">{r.pages} / {r.words} / {r.attempts}</div>
                    </div>
                  </div>
                  <div className="eyebrow mt-5 mb-2">violations</div>
                  {r.issues.length ? (
                    <ul className="list-disc space-y-1 pl-4 text-[11px]"
                        style={{ color: "var(--text-dim)" }}>
                      {r.issues.map((i, idx) => <li key={idx}>{i}</li>)}
                    </ul>
                  ) : (
                    <div className="text-xs" style={{ color: "var(--green)" }}>
                      Clean pass — no violations under the current rubric.
                    </div>
                  )}
                  <div className="eyebrow mt-4">scored {report?.timestamp} · rubric: impact 35
                    / brevity 20 / style 15 / sections 15 / soft-skills 15 (ResumeWorded-replica)</div>
                </>
              )}
            </div>
          </div>
        </div>,
        document.body,
      )}
    </div>
  );
}
