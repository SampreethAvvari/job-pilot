// Resume metadata comes from the RESUMES_JSON env var (array of
// {variant,title,blurb,pdfId,docId}) so personal documents stay out of the repo.

type ResumeCard = {
  variant: string;
  title: string;
  blurb: string;
  pdfId?: string;
  docId?: string;
};

const PLACEHOLDER: ResumeCard[] = [
  { variant: "FDE", title: "Forward Deployed Engineer", blurb: "Customer-facing, end-to-end ownership framing." },
  { variant: "MLE", title: "ML Engineer", blurb: "Training, RAG, ML-infrastructure framing." },
  { variant: "SDE", title: "Software Engineer", blurb: "Backend / distributed-systems framing." },
  { variant: "AIE", title: "AI Engineer", blurb: "GenAI / LLM-platform framing." },
];

function resumes(): ResumeCard[] {
  try {
    const parsed = JSON.parse(process.env.RESUMES_JSON ?? "[]");
    if (Array.isArray(parsed) && parsed.length) return parsed;
  } catch { /* fall through */ }
  return PLACEHOLDER;
}

export default function ResumesPage() {
  const cards = resumes();
  return (
    <div className="rise">
      <div className="mb-5">
        <div className="eyebrow">armory</div>
        <h1 className="display mt-1 text-2xl font-extrabold tracking-tight">Resumes</h1>
        <p className="mt-1 text-xs" style={{ color: "var(--text-dim)" }}>
          One-page ATS-optimized masters. The scorer picks the best variant per job —
          it&apos;s linked in every job row. Configure via the RESUMES_JSON env var.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {cards.map((r) => (
          <div key={r.variant} className="panel p-5">
            <div className="display text-3xl font-extrabold"
                 style={{ color: "var(--amber)" }}>{r.variant}</div>
            <div className="mt-1 font-semibold">{r.title}</div>
            <div className="mt-1 text-[11px]" style={{ color: "var(--text-faint)" }}>
              {r.blurb}
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              {r.pdfId && (
                <a className="btn-amber px-3 py-1.5 text-[11px]"
                   href={`https://drive.google.com/file/d/${r.pdfId}/view`}
                   target="_blank" rel="noopener">
                  Master PDF ↗
                </a>
              )}
              {r.pdfId && (
                <a className="btn-ghost px-3 py-1.5 text-[11px]"
                   href={`https://drive.google.com/uc?export=download&id=${r.pdfId}`}
                   target="_blank" rel="noopener">
                  Download
                </a>
              )}
              {r.docId && (
                <a className="btn-ghost px-3 py-1.5 text-[11px]"
                   href={`https://docs.google.com/document/d/${r.docId}/edit`}
                   target="_blank" rel="noopener">
                  Source Doc
                </a>
              )}
              {!r.pdfId && !r.docId && (
                <span className="text-[11px]" style={{ color: "var(--text-faint)" }}>
                  Set RESUMES_JSON on the service to link your PDFs.
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
