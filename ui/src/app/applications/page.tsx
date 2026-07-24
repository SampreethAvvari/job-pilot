import { ApplicationsView } from "@/components/applications-view";

export default function ApplicationsPage() {
  return (
    <div className="rise">
      <div className="mb-5">
        <div className="eyebrow">queue</div>
        <h1 className="display mt-1 text-2xl font-extrabold tracking-tight">Applications</h1>
        <p className="mt-1 text-xs" style={{ color: "var(--ink-55)" }}>
          Read only for now. Each card is one apply run, the cover letter, the
          answers to each question, and the evidence captured along the way.
          Approve and submit controls arrive once the ATS adapters ship.
        </p>
      </div>

      <ApplicationsView />
    </div>
  );
}
