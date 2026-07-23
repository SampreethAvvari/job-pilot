import { latestReports } from "@/lib/reports";
import { ResumeCard, type ResumeCardData } from "@/components/resume-card";

export const dynamic = "force-dynamic";

// Every tailored resume now derives from a single AIE master (Task 5); a
// rebuild trigger for any other variant returns a skip message. RESUMES_JSON
// may still list the retired FDE/MLE/SDE variants until the env cleanup in
// Task 18, so this page filters down to the one that is still real.
const AIE_PLACEHOLDER: ResumeCardData = {
  variant: "AIE",
  title: "AI Engineer",
  blurb: "The single master every tailored resume is built from.",
};

function masterResume(): ResumeCardData {
  try {
    const parsed = JSON.parse(process.env.RESUMES_JSON ?? "[]");
    if (Array.isArray(parsed)) {
      const aie = parsed.find(
        (c): c is ResumeCardData => Boolean(c) && c.variant === "AIE",
      );
      if (aie) return aie;
    }
  } catch { /* fall through */ }
  return AIE_PLACEHOLDER;
}

export default async function ResumesPage() {
  const master = masterResume();
  const reports = await latestReports("master");
  return (
    <div className="rise">
      <div className="mb-5">
        <div className="eyebrow">armory</div>
        <h1
          className="mt-1 text-2xl font-extrabold tracking-tight"
          style={{ fontFamily: "var(--font-archivo)", color: "var(--ink)" }}
        >
          Master resume <span style={{ color: "var(--blue)" }}>· AIE</span>
        </h1>
        <p className="mt-1 text-[13px]" style={{ color: "var(--ink-70)" }}>
          Every tailored resume starts from this master.
        </p>
        <p className="mt-1 text-xs" style={{ color: "var(--ink-55)" }}>
          Scored by the calibrated ATS judge (ResumeWorded-replica rubric). Click
          the score for the full report. Regenerate runs up to 10 judge-guided
          rewrites and only publishes improvements.
        </p>
      </div>

      <div className="mx-auto max-w-2xl">
        <ResumeCard data={master} report={reports[master.variant] ?? null} />
      </div>
    </div>
  );
}
