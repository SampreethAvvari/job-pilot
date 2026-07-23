"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import type { AtsReport } from "@/lib/reports";
import Button from "@/components/ui/button";
import Modal from "@/components/ui/modal";

export type ResumeCardData = {
  variant: string;
  title: string;
  blurb: string;
  pdfId?: string;
  docId?: string;
};

function scoreColor(score: number) {
  return score >= 90 ? "var(--emerald)" : score >= 75 ? "var(--amber)" : "var(--rose)";
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
    <div className="card p-6">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="eyebrow">{data.variant} master</p>
          <h2
            className="mt-1 truncate font-extrabold"
            style={{ fontFamily: "var(--font-archivo)", fontSize: 22, color: "var(--ink)" }}
          >
            {data.title}
          </h2>
          <p className="mt-1 text-[13px]" style={{ color: "var(--ink-55)" }}>
            {data.blurb}
          </p>
        </div>
        {report && (
          <button
            onClick={() => setOpen(true)}
            className="shrink-0 text-right"
            aria-label={`ATS score ${report.score} out of 100. Open the full report.`}
            title="Open PDF + full ATS report"
          >
            <div
              className="font-extrabold"
              style={{ fontFamily: "var(--font-archivo)", fontSize: 30, color: scoreColor(report.score) }}
            >
              {report.score}
            </div>
            <div className="eyebrow hover:underline">ats report ↗</div>
          </button>
        )}
      </div>

      <div className="mt-5 flex flex-wrap gap-2 border-t pt-4" style={{ borderColor: "var(--line)" }}>
        {data.pdfId && (
          <a className="btn btn-sm btn-primary" href={`/api/resume/${data.variant}`}>
            ⬇ Download PDF
          </a>
        )}
        {report && (
          <Button variant="ghost" size="sm" onClick={() => setOpen(true)}>
            ATS report
          </Button>
        )}
        {data.docId && (
          <a
            className="btn btn-sm btn-ghost"
            href={`https://docs.google.com/document/d/${data.docId}/edit`}
            target="_blank"
            rel="noopener"
          >
            Source Doc ↗
          </a>
        )}
        <Button
          variant="ghost"
          size="sm"
          busy={rebuilding}
          onClick={regenerate}
          title="Up to 10 judge-guided rewrites; published only if the score improves"
        >
          {rebuilding ? "Regenerating…" : "↻ Regenerate"}
        </Button>
      </div>

      <Modal open={open} onClose={() => setOpen(false)} width={1240}>
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="eyebrow">ats report · {data.variant}</p>
            <div
              className="mt-1 font-extrabold"
              style={{ fontFamily: "var(--font-archivo)", fontSize: 34, color: scoreColor(report?.score ?? 0) }}
            >
              {report?.score}
              <span className="text-base font-normal" style={{ color: "var(--ink-55)" }}>
                /100
              </span>
            </div>
          </div>
          <button onClick={() => setOpen(false)} className="btn btn-sm btn-ghost" aria-label="close">
            ✕ close
          </button>
        </div>

        <div
          className="mt-4 flex flex-col overflow-hidden rounded-xl border md:flex-row"
          style={{ borderColor: "var(--line)", height: "72vh" }}
        >
          <div
            className="h-1/2 border-b md:h-full md:flex-1 md:border-b-0 md:border-r"
            style={{ borderColor: "var(--line)" }}
          >
            <iframe
              src={`/api/resume/${data.variant}?inline=1`}
              title={`${data.variant} resume`}
              style={{ width: "100%", height: "100%", border: 0, background: "#fff" }}
            />
          </div>
          <div className="h-1/2 overflow-y-auto p-4 md:h-full md:w-[380px] md:shrink-0">
            {r && (
              <>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  {Object.entries(r.breakdown).map(([k, v]) => (
                    <div key={k} className="card px-3 py-2">
                      <div className="eyebrow">{k.replace("_", " ")}</div>
                      <div className="font-bold" style={{ color: "var(--ink)" }}>{v}</div>
                    </div>
                  ))}
                  <div className="card px-3 py-2">
                    <div className="eyebrow">keywords</div>
                    <div className="font-bold" style={{ color: "var(--ink)" }}>
                      {Math.round(r.keyword_coverage * 100)}%
                    </div>
                  </div>
                  <div className="card px-3 py-2">
                    <div className="eyebrow">pages / words / attempts</div>
                    <div className="font-bold" style={{ color: "var(--ink)" }}>
                      {r.pages} / {r.words} / {r.attempts}
                    </div>
                  </div>
                </div>
                <div className="eyebrow mt-5 mb-2">violations</div>
                {r.issues.length ? (
                  <ul className="list-disc space-y-1 pl-4 text-[11px]" style={{ color: "var(--ink-70)" }}>
                    {r.issues.map((i, idx) => <li key={idx}>{i}</li>)}
                  </ul>
                ) : (
                  <div className="text-xs" style={{ color: "var(--emerald)" }}>
                    Clean pass. No violations under the current rubric.
                  </div>
                )}
                <div className="eyebrow mt-4">
                  scored {report?.timestamp} · rubric: impact 35 / brevity 20 / style 15 / sections 15
                  {" "}/ soft skills 15 (ResumeWorded-replica)
                </div>
              </>
            )}
          </div>
        </div>
      </Modal>
    </div>
  );
}
