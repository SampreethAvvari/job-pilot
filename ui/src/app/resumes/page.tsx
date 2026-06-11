import { latestReports } from "@/lib/reports";
import { ResumeCard, type ResumeCardData } from "@/components/resume-card";

export const dynamic = "force-dynamic";

const PLACEHOLDER: ResumeCardData[] = [
  { variant: "FDE", title: "Forward Deployed Engineer", blurb: "Customer-facing, end-to-end ownership framing." },
  { variant: "MLE", title: "ML Engineer", blurb: "Training, RAG, ML-infrastructure framing." },
  { variant: "SDE", title: "Software Engineer", blurb: "Backend / distributed-systems framing." },
  { variant: "AIE", title: "AI Engineer", blurb: "GenAI / LLM-platform framing." },
];

function resumes(): ResumeCardData[] {
  try {
    const parsed = JSON.parse(process.env.RESUMES_JSON ?? "[]");
    if (Array.isArray(parsed) && parsed.length) return parsed;
  } catch { /* fall through */ }
  return PLACEHOLDER;
}

export default async function ResumesPage() {
  const cards = resumes();
  const reports = await latestReports("master");
  return (
    <div className="rise">
      <div className="mb-5">
        <div className="eyebrow">armory</div>
        <h1 className="display mt-1 text-2xl font-extrabold tracking-tight">Resumes</h1>
        <p className="mt-1 text-xs" style={{ color: "var(--text-dim)" }}>
          One-page masters scored by the calibrated ATS judge (ResumeWorded-replica
          rubric). Click a score for the full report. Regenerate runs up to 10
          judge-guided rewrites and only publishes improvements.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {cards.map((c) => (
          <ResumeCard key={c.variant} data={c} report={reports[c.variant] ?? null} />
        ))}
      </div>
    </div>
  );
}
