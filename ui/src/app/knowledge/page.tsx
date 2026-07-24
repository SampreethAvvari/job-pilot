import { KnowledgePanel } from "@/components/knowledge-panel";

export default function KnowledgePage() {
  return (
    <div className="rise">
      <div className="mb-5">
        <div className="eyebrow">grounding</div>
        <h1 className="display mt-1 text-2xl font-extrabold tracking-tight">Knowledge</h1>
        <p className="mt-1 text-xs" style={{ color: "var(--ink-55)" }}>
          Crawls your portfolio, rebuilds the project knowledge graph, and refreshes
          what the Assistant grounds its answers in. Runs automatically in the daily
          pipeline, use this to rebuild now after publishing new work.
        </p>
      </div>

      <KnowledgePanel />
    </div>
  );
}
