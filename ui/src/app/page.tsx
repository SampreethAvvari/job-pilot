import Link from "next/link";

export const dynamic = "force-dynamic";

import { readJobs, type Job } from "@/lib/jobs";
import { FitMeter, StatusPill } from "@/components/status";

const ADVANCED = new Set(["Applied", "Outreach sent", "Response", "Interview", "Offer"]);
const RESPONDED = new Set(["Response", "Interview", "Offer"]);

function Tile({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="panel px-4 py-3">
      <div className="eyebrow">{label}</div>
      <div className="display mt-1 text-2xl font-extrabold"
           style={accent ? { color: "var(--amber)" } : undefined}>
        {value}
      </div>
    </div>
  );
}

export default async function Dashboard() {
  let jobs: Job[] = [];
  let loadError = "";
  try {
    jobs = await readJobs();
  } catch (e) {
    loadError = String(e);
  }

  const applied = jobs.filter((j) => ADVANCED.has(j.status));
  const responses = jobs.filter((j) => RESPONDED.has(j.status));
  const interviews = jobs.filter((j) => ["Interview", "Offer"].includes(j.status));
  const rate = applied.length ? Math.round((responses.length / applied.length) * 100) : 0;

  const top = jobs
    .filter((j) => (j.status === "New" || !j.status) && (j.fit ?? 0) >= 60)
    .sort((a, b) => (b.fit ?? 0) - (a.fit ?? 0))
    .slice(0, 8);

  const replies = jobs
    .filter((j) => j.lastReply)
    .sort((a, b) => b.lastReply.localeCompare(a.lastReply))
    .slice(0, 5);

  return (
    <div className="rise space-y-6">
      <div>
        <div className="eyebrow">mission status</div>
        <h1 className="display mt-1 text-3xl font-extrabold tracking-tight">
          The hunt, <span style={{ color: "var(--amber)" }}>quantified.</span>
        </h1>
      </div>

      {loadError && (
        <div className="panel px-4 py-3 text-xs" style={{ color: "var(--red)" }}>
          Could not load the sheet: {loadError}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Tile label="jobs found" value={String(jobs.length)} />
        <Tile label="applied" value={String(applied.length)} accent />
        <Tile label="responses" value={String(responses.length)} />
        <Tile label="interviews" value={String(interviews.length)} />
        <Tile label="response rate" value={`${rate}%`} />
      </div>

      <section>
        <div className="mb-2 flex items-baseline justify-between">
          <h2 className="display text-lg font-bold">Top open matches</h2>
          <Link href="/jobs" className="eyebrow hover:text-[var(--amber)]">
            all jobs →
          </Link>
        </div>
        <div className="panel overflow-x-auto">
          <table className="console-table">
            <thead>
              <tr><th>Fit</th><th>Role</th><th>Company</th><th>Posted</th><th>Sponsor</th></tr>
            </thead>
            <tbody>
              {top.map((j) => (
                <tr key={j.row}>
                  <td><FitMeter fit={j.fit} /></td>
                  <td>
                    <a className="font-semibold hover:underline" href={j.url}
                       target="_blank" rel="noopener">{j.title}</a>
                  </td>
                  <td>{j.company}</td>
                  <td style={{ color: "var(--text-dim)" }}>{j.postedAge}</td>
                  <td>{j.sponsorship}</td>
                </tr>
              ))}
              {top.length === 0 && (
                <tr><td colSpan={5} className="py-8 text-center"
                        style={{ color: "var(--text-faint)" }}>
                  Nothing new above threshold — hit Refresh jobs.
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h2 className="display mb-2 text-lg font-bold">Latest replies</h2>
        <div className="panel divide-y" style={{ borderColor: "var(--line-soft)" }}>
          {replies.map((j) => (
            <div key={j.row} className="flex items-center justify-between gap-3 px-4 py-3">
              <div className="min-w-0">
                <div className="truncate font-semibold">{j.company} — {j.title}</div>
                <div className="text-[11px]" style={{ color: "var(--text-faint)" }}>
                  {j.lastReply} · {j.replyClass}
                </div>
              </div>
              <StatusPill status={j.status} />
            </div>
          ))}
          {replies.length === 0 && (
            <div className="px-4 py-8 text-center text-xs" style={{ color: "var(--text-faint)" }}>
              No replies tracked yet — they appear automatically once the scanner sees
              recruiter emails.
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
