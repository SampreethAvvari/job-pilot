import { GoogleAuth } from "google-auth-library";

import { PROJECT, REGION } from "./google";

const auth = new GoogleAuth({
  scopes: ["https://www.googleapis.com/auth/cloud-platform"],
});

const JOB = `projects/${PROJECT}/locations/${REGION}/jobs/jobpilot`;
const BASE = "https://run.googleapis.com/v2";

export type RunState = "RUNNING" | "SUCCEEDED" | "FAILED" | "NONE";

export async function triggerRun(): Promise<void> {
  // Console refresh = fast mode: fetch + score + record only (~3-6 min).
  await runWithArgs(["--fast"]);
}

async function runWithArgs(args: string[]): Promise<void> {
  const client = await auth.getClient();
  await client.request({
    url: `${BASE}/${JOB}:run`,
    method: "POST",
    data: { overrides: { containerOverrides: [{ args }] } },
  });
}

export async function triggerTailor(jobId: string): Promise<void> {
  await runWithArgs(["--tailor-job", jobId]);
}

export async function triggerOutreach(jobId: string): Promise<void> {
  await runWithArgs(["--outreach-job", jobId]);
}

export async function latestRun(): Promise<{ state: RunState; started: string }> {
  const client = await auth.getClient();
  const res = await client.request<{
    executions?: {
      createTime?: string;
      completionTime?: string;
      succeededCount?: number;
      failedCount?: number;
    }[];
  }>({ url: `${BASE}/${JOB}/executions?pageSize=1`, method: "GET" });
  const ex = res.data.executions?.[0];
  if (!ex) return { state: "NONE", started: "" };
  const started = ex.createTime ?? "";
  if (!ex.completionTime) return { state: "RUNNING", started };
  return { state: (ex.failedCount ?? 0) > 0 ? "FAILED" : "SUCCEEDED", started };
}
