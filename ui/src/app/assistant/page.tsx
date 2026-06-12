import { AssistantChat } from "@/components/assistant-chat";

export const dynamic = "force-dynamic";

export default async function AssistantPage({
  searchParams,
}: {
  searchParams: Promise<{ job?: string }>;
}) {
  const { job } = await searchParams;

  return (
    <div className="rise">
      <div className="mb-5">
        <div className="eyebrow">copilot</div>
        <h1 className="display mt-1 text-2xl font-extrabold tracking-tight">Assistant</h1>
        <p className="mt-1 text-xs" style={{ color: "var(--text-dim)" }}>
          Grounded in your resumes, GitHub, portfolio, and the Knowledge tab —
          and nothing else. Resume rewrites, cover letters, and application
          answers only; finished PDFs run through the same ATS-checked pipeline
          as auto-tailoring.
        </p>
      </div>

      <AssistantChat initialJobId={job} />
    </div>
  );
}
