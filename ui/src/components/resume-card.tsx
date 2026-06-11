"use client";

import { useState } from "react";
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
  const [showReport, setShowReport] = useState(false);
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
          <button onClick={() => setShowReport(!showReport)}
                  className="text-right"
                  title="Open the full ATS report">
            <div className="display text-2xl font-extrabold"
                 style={{ color: scoreColor(report.score) }}>
              {report.score}
            </div>
            <div className="eyebrow">ats score ▾</div>
          </button>
        )}
      </div>

      {showReport && r && (
        <div className="mt-4 rounded border p-3 text-[11px]"
             style={{ borderColor: "var(--line)", color: "var(--text-dim)" }}>
          <div className="mb-2 flex flex-wrap gap-3">
            {Object.entries(r.breakdown).map(([k, v]) => (
              <span key={k}>
                <span className="eyebrow">{k.replace("_", " ")}</span>{" "}
                <b style={{ color: "var(--text)" }}>{v}</b>
              </span>
            ))}
            <span><span className="eyebrow">keywords</span>{" "}
              <b style={{ color: "var(--text)" }}>{Math.round(r.keyword_coverage * 100)}%</b>
            </span>
            <span><span className="eyebrow">pages</span> <b style={{ color: "var(--text)" }}>{r.pages}</b></span>
            <span><span className="eyebrow">attempts</span> <b style={{ color: "var(--text)" }}>{r.attempts}</b></span>
          </div>
          {r.issues.length ? (
            <ul className="list-disc pl-4">
              {r.issues.map((i, idx) => <li key={idx}>{i}</li>)}
            </ul>
          ) : (
            <div style={{ color: "var(--green)" }}>No violations — clean pass.</div>
          )}
          <div className="eyebrow mt-2">scored {report?.timestamp}</div>
        </div>
      )}

      <div className="mt-4 flex flex-wrap gap-2">
        {data.pdfId && (
          <a className="btn-amber px-3 py-1.5 text-[11px]"
             href={`/api/resume/${data.variant}`}>
            ⬇ Download PDF
          </a>
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
                title="Rewrite through the judge loop (up to 10 attempts); only published if the score improves">
          {rebuilding ? <span className="blink">↻ regenerating… (takes a few min)</span> : "↻ Regenerate"}
        </button>
      </div>
    </div>
  );
}
