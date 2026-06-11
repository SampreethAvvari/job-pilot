"use client";

// ATS score badge: hover = compact summary card, click = pinned full
// transparency report panel (keyword provenance, diffs, rationale).
// Portal-rendered (BL-13: never position fixed inside transformed ancestors).

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import type { Job } from "@/lib/types";
import { diffWords } from "@/lib/word-diff";

type KeywordFate = {
  keyword: string;
  jd_quote: string;
  in_baseline: boolean;
  action: "already_present" | "added" | "not_addable";
  section: string;
  before: string;
  after: string;
  reason: string;
};

type TailorReport = {
  precision: string;
  jd: { summary: string; requirements: string[]; nice_to_haves: string[] };
  keywords: KeywordFate[];
  resume_rationale: string;
  cover_rationale: string;
  master_suggestions: string[];
  diff_sections: { section: string; baseline: string; tailored: string }[];
  diff_pdf: string;
  ats: JudgeReport;
};

type JudgeReport = {
  score?: number;
  breakdown?: Record<string, number>;
  keyword_coverage?: number;
  attempts?: number;
  issues?: string[];
};

const CATEGORY_MAX: Record<string, number> = {
  impact: 35, brevity: 20, style: 15, sections: 15, soft_skills: 15,
};

const ACTION_LABEL: Record<KeywordFate["action"], [string, string]> = {
  already_present: ["already in resume", "var(--text-dim)"],
  added: ["added", "var(--green)"],
  not_addable: ["genuinely missing", "var(--red)"],
};

function sourceLink(url: string, quote: string): string {
  if (!url || !quote) return url;
  return `${url}#:~:text=${encodeURIComponent(quote.slice(0, 120))}`;
}

function ScoreBars({ ats }: { ats: JudgeReport }) {
  if (!ats.breakdown) return null;
  return (
    <div className="flex flex-col gap-1">
      {Object.entries(ats.breakdown).map(([k, v]) => {
        const max = CATEGORY_MAX[k] ?? 100;
        return (
          <div key={k} className="flex items-center gap-2 text-[11px]">
            <span className="w-20 shrink-0" style={{ color: "var(--text-dim)" }}>
              {k.replace("_", " ")}
            </span>
            <span className="h-1.5 w-32 overflow-hidden rounded"
                  style={{ background: "var(--panel-2)" }}>
              <span className="block h-full rounded"
                    style={{
                      width: `${(100 * v) / max}%`,
                      background: v / max >= 0.85 ? "var(--green)" : "var(--amber)",
                    }} />
            </span>
            <span style={{ color: "var(--text-faint)" }}>{v}/{max}</span>
          </div>
        );
      })}
      {ats.keyword_coverage != null && (
        <div className="text-[11px]" style={{ color: "var(--text-dim)" }}>
          JD keyword coverage {Math.round(ats.keyword_coverage * 100)}%
          {ats.attempts ? ` · best of ${ats.attempts} attempt(s)` : ""}
        </div>
      )}
    </div>
  );
}

function HighlightedDiff({ baseline, tailored }: { baseline: string; tailored: string }) {
  return (
    <p className="text-xs leading-5">
      {diffWords(baseline, tailored).map((s, i) =>
        s.added ? (
          <mark key={i} style={{
            background: "rgba(91,217,122,0.18)", color: "var(--green)",
            borderRadius: 3, padding: "0 2px",
          }}>
            {s.text}
          </mark>
        ) : (
          <span key={i} style={{ color: "var(--text-dim)" }}>{s.text}</span>
        ),
      ).reduce<React.ReactNode[]>((acc, el, i) => (i ? [...acc, " ", el] : [el]), [])}
    </p>
  );
}

export function AtsBadge({ job }: { job: Job }) {
  const ref = useRef<HTMLButtonElement>(null);
  const loaded = useRef(false);
  const [card, setCard] = useState<{ top: number; left: number } | null>(null);
  const [pinned, setPinned] = useState(false);
  const [report, setReport] = useState<TailorReport | null>(null);
  const [judge, setJudge] = useState<JudgeReport | null>(null);
  const [fetched, setFetched] = useState(false);
  const [generating, setGenerating] = useState(false);

  async function load() {
    if (loaded.current) return;
    loaded.current = true;
    try {
      const r = await (await fetch(`/api/reports?kind=tailor&key=${job.id}`)).json();
      if (r?.report) setReport(r.report as TailorReport);
      else {
        const j = await (await fetch(`/api/reports?kind=job&key=${job.id}`)).json();
        if (j?.report) setJudge(j.report as JudgeReport);
      }
    } catch { /* panel shows the fallback */ }
    setFetched(true);
  }

  function generate() {
    setGenerating(true);
    fetch("/api/explain", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jobId: job.id }),
    }).catch(() => {});
    const started = Date.now();
    const t = setInterval(async () => {
      if (Date.now() - started > 6 * 60_000) {
        clearInterval(t);
        setGenerating(false);
        return;
      }
      try {
        const r = await (await fetch(`/api/reports?kind=tailor&key=${job.id}`)).json();
        if (r?.report) {
          clearInterval(t);
          setReport(r.report as TailorReport);
          setGenerating(false);
        }
      } catch { /* keep polling */ }
    }, 15_000);
  }

  useEffect(() => {
    if (!pinned) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setPinned(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [pinned]);

  const ats: JudgeReport = report?.ats ?? judge ?? {};
  const added = report?.keywords.filter((k) => k.action === "added") ?? [];
  const missing = report?.keywords.filter((k) => k.action === "not_addable") ?? [];

  return (
    <>
      <button
        ref={ref}
        onMouseEnter={() => {
          load();
          const r = ref.current?.getBoundingClientRect();
          if (r) setCard({ top: r.bottom + 6, left: Math.max(8, r.right - 320) });
        }}
        onMouseLeave={() => setCard(null)}
        onClick={() => { load(); setCard(null); setPinned(true); }}
        className="hover:underline"
        title="Hover for a summary — click for the full tailoring report"
        style={{
          color: Number(job.resumeAts) >= 90 ? "var(--green)" : "var(--amber)",
          cursor: "pointer",
        }}
      >
        ATS {job.resumeAts}
      </button>

      {card && !pinned && typeof document !== "undefined" && createPortal(
        <div style={{
          position: "fixed", top: card.top, left: card.left, zIndex: 9998,
          width: 320, padding: 14, pointerEvents: "none",
          background: "#11161c", borderRadius: 10,
          border: "1px solid var(--line)", boxShadow: "0 16px 48px rgba(0,0,0,0.55)",
          color: "var(--text)",
        }}>
          <div className="eyebrow">ats {job.resumeAts} · {job.company}</div>
          <div className="mt-2">
            <ScoreBars ats={ats} />
          </div>
          <div className="mt-2 text-[11px]" style={{ color: "var(--text-dim)" }}>
            {report
              ? `${added.length} keyword(s) added · ${missing.length} genuinely missing`
              : fetched
                ? "No transparency report yet — click to generate one"
                : "loading report…"}
          </div>
          <div className="mt-1 text-[11px]" style={{ color: "var(--text-faint)" }}>
            click to pin the full report
          </div>
        </div>,
        document.body,
      )}

      {pinned && typeof document !== "undefined" && createPortal(
        <div
          style={{
            position: "fixed", inset: 0, zIndex: 9999, display: "flex",
            alignItems: "center", justifyContent: "center",
            background: "rgba(5,7,9,0.78)",
          }}
          onClick={() => setPinned(false)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              width: "min(920px, 94vw)", maxHeight: "88vh", overflowY: "auto",
              margin: 16, padding: 24, background: "#11161c", borderRadius: 12,
              border: "1px solid var(--line)", boxShadow: "0 20px 60px rgba(0,0,0,0.6)",
              color: "var(--text)",
            }}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="eyebrow">tailoring report · ATS {job.resumeAts}</div>
                <div className="display mt-1 text-lg font-bold">
                  {job.title}
                </div>
                <div className="text-xs" style={{ color: "var(--text-dim)" }}>
                  {job.company} · {job.resumeVariant} variant
                  {report?.precision === "pdf" && " · reconstructed from PDFs"}
                </div>
              </div>
              <button className="btn-ghost px-2 py-1 text-xs" onClick={() => setPinned(false)}>
                ✕
              </button>
            </div>

            <div className="mt-3 flex flex-wrap gap-3 text-[11px]">
              {job.url && (
                <a href={job.url} target="_blank" rel="noopener" className="hover:underline"
                   style={{ color: "var(--cyan)" }}>Job posting ↗</a>
              )}
              {job.tailoredResume && (
                <a href={job.tailoredResume} target="_blank" rel="noopener"
                   className="hover:underline" style={{ color: "var(--green)" }}>Resume ⬇</a>
              )}
              {job.coverLetter && (
                <a href={job.coverLetter} target="_blank" rel="noopener"
                   className="hover:underline" style={{ color: "var(--green)" }}>Cover ⬇</a>
              )}
              {report?.diff_pdf && (
                <a href={report.diff_pdf} target="_blank" rel="noopener"
                   className="hover:underline" style={{ color: "var(--violet)" }}
                   title="Baseline vs tailored with additions underlined">
                  Highlighted diff PDF ⬇
                </a>
              )}
            </div>

            {!report && (
              <div className="mt-5">
                <div className="eyebrow">no transparency report yet</div>
                <p className="mt-2 text-xs" style={{ color: "var(--text-dim)" }}>
                  This job was tailored before transparency reports existed. Generate one
                  from the stored PDFs (~1–2 min): keyword provenance, what was added, and
                  what is genuinely missing.
                </p>
                <button
                  className="btn-amber mt-3 px-4 py-2 text-xs"
                  disabled={generating || !job.tailoredResume}
                  onClick={generate}
                >
                  {generating ? "generating…" : "Generate report"}
                </button>
                {judge && (
                  <div className="mt-5">
                    <div className="eyebrow">ats breakdown</div>
                    <div className="mt-2"><ScoreBars ats={judge} /></div>
                    {judge.issues && judge.issues.length > 0 && (
                      <ul className="mt-3 flex flex-col gap-1 text-[11px]"
                          style={{ color: "var(--text-dim)" }}>
                        {judge.issues.slice(0, 12).map((i, n) => <li key={n}>· {i}</li>)}
                      </ul>
                    )}
                  </div>
                )}
              </div>
            )}

            {report && (
              <>
                <div className="mt-5">
                  <div className="eyebrow">pulled from the posting</div>
                  {report.jd.summary && (
                    <p className="mt-2 text-xs leading-5" style={{ color: "var(--text-dim)" }}>
                      {report.jd.summary}
                    </p>
                  )}
                  <div className="mt-2 grid gap-3 sm:grid-cols-2">
                    {report.jd.requirements.length > 0 && (
                      <div>
                        <div className="text-[11px] font-bold" style={{ color: "var(--text)" }}>
                          Requirements
                        </div>
                        <ul className="mt-1 flex flex-col gap-1 text-[11px]"
                            style={{ color: "var(--text-dim)" }}>
                          {report.jd.requirements.map((r, i) => <li key={i}>· {r}</li>)}
                        </ul>
                      </div>
                    )}
                    {report.jd.nice_to_haves.length > 0 && (
                      <div>
                        <div className="text-[11px] font-bold" style={{ color: "var(--text)" }}>
                          Nice to have
                        </div>
                        <ul className="mt-1 flex flex-col gap-1 text-[11px]"
                            style={{ color: "var(--text-dim)" }}>
                          {report.jd.nice_to_haves.map((r, i) => <li key={i}>· {r}</li>)}
                        </ul>
                      </div>
                    )}
                  </div>
                </div>

                <div className="mt-5">
                  <div className="eyebrow">keywords · where they came from · what happened</div>
                  <table className="mt-2 w-full text-[11px]">
                    <thead>
                      <tr style={{ color: "var(--text-faint)" }}>
                        <th className="pb-1 pr-2 text-left font-normal">keyword</th>
                        <th className="pb-1 pr-2 text-left font-normal">source in the JD</th>
                        <th className="pb-1 pr-2 text-left font-normal">baseline</th>
                        <th className="pb-1 text-left font-normal">outcome</th>
                      </tr>
                    </thead>
                    <tbody className="align-top">
                      {report.keywords.map((k, i) => {
                        const [label, color] = ACTION_LABEL[k.action] ?? ["?", "var(--text-dim)"];
                        return (
                          <tr key={i} style={{ borderTop: "1px solid var(--line-soft)" }}>
                            <td className="py-1.5 pr-2 font-bold whitespace-nowrap">{k.keyword}</td>
                            <td className="py-1.5 pr-2" style={{ color: "var(--text-dim)" }}>
                              {k.jd_quote ? (
                                <a href={sourceLink(job.url, k.jd_quote)} target="_blank"
                                   rel="noopener" className="hover:underline"
                                   title="Open the posting at this sentence">
                                  “{k.jd_quote}” ↗
                                </a>
                              ) : "—"}
                            </td>
                            <td className="py-1.5 pr-2 whitespace-nowrap"
                                style={{ color: k.in_baseline ? "var(--green)" : "var(--text-faint)" }}>
                              {k.in_baseline ? "✓ had it" : "✕ missing"}
                            </td>
                            <td className="py-1.5">
                              <span style={{ color }}>{label}</span>
                              {k.action === "added" && (
                                <div className="mt-0.5" style={{ color: "var(--text-dim)" }}>
                                  {k.section && <span>→ {k.section}. </span>}
                                  {k.after && <HighlightedDiff baseline={k.before} tailored={k.after} />}
                                </div>
                              )}
                              {k.reason && (
                                <div className="mt-0.5" style={{ color: "var(--text-faint)" }}>
                                  {k.reason}
                                </div>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                {report.diff_sections.some((d) => d.baseline !== d.tailored) && (
                  <div className="mt-5">
                    <div className="eyebrow">what changed vs the baseline (additions highlighted)</div>
                    <div className="mt-2 flex flex-col gap-3">
                      {report.diff_sections
                        .filter((d) => d.tailored && d.baseline !== d.tailored)
                        .map((d, i) => (
                          <div key={i}>
                            <div className="text-[11px] font-bold">{d.section}</div>
                            <HighlightedDiff baseline={d.baseline} tailored={d.tailored} />
                          </div>
                        ))}
                    </div>
                  </div>
                )}

                {(report.resume_rationale || report.cover_rationale) && (
                  <div className="mt-5">
                    <div className="eyebrow">thinking &amp; rationale</div>
                    {report.resume_rationale && (
                      <p className="mt-2 text-xs leading-5" style={{ color: "var(--text-dim)" }}>
                        <b style={{ color: "var(--text)" }}>Resume:</b> {report.resume_rationale}
                      </p>
                    )}
                    {report.cover_rationale && (
                      <p className="mt-2 text-xs leading-5" style={{ color: "var(--text-dim)" }}>
                        <b style={{ color: "var(--text)" }}>Cover letter:</b> {report.cover_rationale}
                      </p>
                    )}
                  </div>
                )}

                {report.master_suggestions.length > 0 && (
                  <div className="mt-5">
                    <div className="eyebrow">genuinely missing — worth adding to your master?</div>
                    <ul className="mt-2 flex flex-col gap-1 text-[11px]"
                        style={{ color: "var(--text-dim)" }}>
                      {report.master_suggestions.map((s, i) => <li key={i}>· {s}</li>)}
                    </ul>
                  </div>
                )}

                <div className="mt-5">
                  <div className="eyebrow">ats breakdown</div>
                  <div className="mt-2"><ScoreBars ats={report.ats} /></div>
                </div>
              </>
            )}
          </div>
        </div>,
        document.body,
      )}
    </>
  );
}
