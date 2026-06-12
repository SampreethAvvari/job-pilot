import { knowledgePack } from "@/lib/knowledge";
import { readJobs } from "@/lib/jobs";
import { FLASH, PRO, generate, type ChatMessage } from "@/lib/vertex";

const SYSTEM = `You are JobPilot Assistant, the private application copilot for ONE candidate.
Everything you know about the candidate comes from the CANDIDATE KNOWLEDGE below
(profile, resumes, GitHub projects, portfolio, extra facts). It is the only
source of truth about them.

SCOPE — you help with exactly four things:
1. Updating or rewriting the candidate's resume content for a specific job.
2. Writing cover letters for a specific job.
3. Answering application questions (e.g. "Why this company?", "Describe a
   project", "Tell us about a challenge") for a specific job or company. Use
   web search to ground company facts when helpful.
4. Questions about the candidate's own background, projects, and experience.
If a request is outside these four, refuse in one short sentence and point the
user back to what you can do. No exceptions: no general coding help, no news,
no chit-chat.

TRUTH — never invent employers, titles, dates, metrics, technologies, or
accomplishments. Only state facts present in the candidate knowledge or the
job context. If a question needs a fact you do not have, say which fact is
missing and suggest adding it to the Knowledge tab's extras row.

STYLE — write like the candidate, a sharp engineer, would write:
- STAR shape for every experience answer and resume bullet: situation/task in
  a clause, action with specific tech, measurable result. Lead with the action.
- First person, plain confident sentences. Technical specificity over adjectives.
- NEVER use em dashes or en dashes anywhere. Use commas or periods instead.
- Banned words and patterns: "delve", "leverage", "seamlessly", "showcase",
  "spearheaded", "testament", "landscape", "tapestry", "passionate",
  "cutting-edge", rhetorical triads ("X, Y, and Z" filler), and exclamation marks.
- Resume bullets are single sentences in STAR form, no trailing periods, no
  leading hyphens.
- Answers to application questions: 80 to 180 words unless asked otherwise,
  one idea per paragraph, no headers or bullet lists unless asked.

When the user wants a finished resume or cover letter PDF, tell them to press
the "Generate resume + cover PDFs" button, which runs the real tailoring
pipeline with ATS checks. You draft and refine content; the pipeline ships it.`;

function dashy(text: string): boolean {
  return /[—–]/.test(text);
}

export async function POST(request: Request) {
  try {
    const { messages, model, jobId } = (await request.json()) as {
      messages: ChatMessage[];
      model?: "flash" | "pro";
      jobId?: string;
    };
    if (!Array.isArray(messages) || messages.length === 0) {
      return Response.json({ error: "messages required" }, { status: 400 });
    }
    const attachedBytes = messages.flatMap((m) => m.attachments ?? [])
      .reduce((n, a) => n + a.data.length * 0.75, 0);
    if (attachedBytes > 15 * 1024 * 1024) {
      return Response.json(
        { error: "attachments exceed 15MB total — start a fresh chat or use smaller files" },
        { status: 400 },
      );
    }
    const pack = await knowledgePack();
    let jobContext = "";
    if (jobId) {
      const job = (await readJobs()).find((j) => j.id === jobId);
      if (job) {
        jobContext =
          `\n\nJOB CONTEXT (the job under discussion):\n` +
          `Company: ${job.company}\nTitle: ${job.title}\nLocation: ${job.location}\n` +
          `Posted: ${job.posted}\nURL: ${job.url}\nFit score: ${job.fit ?? "n/a"}\n` +
          `JD keywords: ${job.jdKeywords}`;
      }
    }
    const system = `${SYSTEM}\n\nCANDIDATE KNOWLEDGE:\n${pack}${jobContext}`;
    let modelId = model === "pro" ? PRO : FLASH;

    let reply: string;
    try {
      reply = await generate(modelId, system, messages);
    } catch (e) {
      if (modelId === PRO) {
        // pro id unavailable in this region/project — degrade, don't die
        modelId = FLASH;
        reply = `(pro model unavailable, answered with flash)\n\n` +
                (await generate(modelId, system, messages));
      } else {
        throw e;
      }
    }
    if (dashy(reply)) {
      // one explicit retry, then sanitize — the no-dash rule is absolute
      reply = await generate(modelId, system, [
        ...messages,
        { role: "model", text: reply },
        { role: "user",
          text: "Rewrite your last answer with zero em dashes or en dashes. " +
                "Use commas or periods. Change nothing else." },
      ]);
      reply = reply.replace(/\s*[—–]\s*/g, ", ");
    }
    return Response.json({ reply });
  } catch (e) {
    return Response.json({ error: String(e) }, { status: 500 });
  }
}
