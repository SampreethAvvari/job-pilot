import { readJobs } from "@/lib/jobs";
import { RepliesView } from "@/components/replies-view";

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
        <p className="mt-1 text-xs" style={{ color: "var(--ink-55)" }}>
          The scanner reads your inbox each run, matches recruiter emails to tracked
          applications, and moves status forward. Your manual edits always win, use
          the Class dropdown to correct a misread, or remove a non-reply entirely.
        </p>
      </div>

      <RepliesView initial={replies} />
    </div>
  );
}
