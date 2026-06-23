import { readOutreach } from "@/lib/outreach";
import type { Outreach } from "@/lib/types";
import { OutreachConsole } from "@/components/outreach-console";

export const dynamic = "force-dynamic";

export default async function OutreachPage() {
  let rows: Outreach[] = [];
  try {
    rows = await readOutreach();
  } catch {
    // Outreach tab is created on the first company-outreach run; empty until then.
  }

  return (
    <div className="rise">
      <div className="mb-5">
        <div className="eyebrow">cold outreach</div>
        <h1 className="display mt-1 text-2xl font-extrabold tracking-tight">Outreach</h1>
        <p className="mt-1 text-xs" style={{ color: "var(--text-dim)" }}>
          Search a company. JobPilot picks your best-fit resume, writes a short,
          plain-English cold email, builds a tailored cover letter, finds the right
          people via Hunter (when a key is set), and drops a draft in your Gmail tagged
          <b> [JobPilot · Company]</b> so drafts pool by company. High-confidence emails
          are pre-addressed; lower-confidence or missing ones stay blank with
          people-search links so you find them by hand. Nothing is ever sent for you.
        </p>
      </div>

      <OutreachConsole initial={rows} />
    </div>
  );
}
