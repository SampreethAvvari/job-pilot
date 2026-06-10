import { readJobs } from "@/lib/jobs";
import { StatusPill } from "@/components/status";

export const dynamic = "force-dynamic";

export default async function RepliesPage() {
  const jobs = await readJobs();
  const replies = jobs
    .filter((j) => j.lastReply || j.replyClass)
    .sort((a, b) => b.lastReply.localeCompare(a.lastReply));

  return (
    <div className="rise">
      <div className="mb-5">
        <div className="eyebrow">comms</div>
        <h1 className="display mt-1 text-2xl font-extrabold tracking-tight">Replies</h1>
        <p className="mt-1 text-xs" style={{ color: "var(--text-dim)" }}>
          The scanner reads your inbox each run, matches recruiter emails to tracked
          applications, and moves status forward. Your manual edits always win.
        </p>
      </div>

      <div className="panel overflow-x-auto">
        <table className="console-table">
          <thead>
            <tr><th>Reply date</th><th>Company</th><th>Role</th><th>Class</th><th>Status</th></tr>
          </thead>
          <tbody>
            {replies.map((j) => (
              <tr key={j.row}>
                <td className="whitespace-nowrap">{j.lastReply}</td>
                <td>{j.company}</td>
                <td>
                  <a className="hover:underline" href={j.url} target="_blank" rel="noopener">
                    {j.title}
                  </a>
                </td>
                <td style={{
                  color: j.replyClass === "interview" ? "var(--amber)"
                    : j.replyClass === "rejected" ? "var(--red)" : "var(--text-dim)",
                }}>
                  {j.replyClass || "—"}
                </td>
                <td><StatusPill status={j.status} /></td>
              </tr>
            ))}
            {replies.length === 0 && (
              <tr><td colSpan={5} className="py-10 text-center"
                      style={{ color: "var(--text-faint)" }}>
                No replies yet. Once you apply to jobs and recruiters respond to
                spa9659@nyu.edu, they show up here automatically.
              </td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
