import { google } from "googleapis";

import { oauthClient } from "@/lib/google";

// Streams a master resume PDF straight from Drive so downloads always work.
export async function GET(
  _req: Request,
  { params }: { params: Promise<{ variant: string }> },
) {
  const { variant } = await params;
  const links: Record<string, { pdfId?: string }> = {};
  try {
    for (const r of JSON.parse(process.env.RESUMES_JSON ?? "[]")) {
      links[r.variant] = r;
    }
  } catch { /* fall through */ }
  const pdfId = links[variant]?.pdfId;
  if (!pdfId) {
    return Response.json({ error: `no pdf configured for ${variant}` }, { status: 404 });
  }
  const drive = google.drive({ version: "v3", auth: oauthClient() });
  const file = await drive.files.get(
    { fileId: pdfId, alt: "media" },
    { responseType: "arraybuffer" },
  );
  const inline = new URL(_req.url).searchParams.get("inline");
  const disposition = inline ? "inline" : "attachment";
  return new Response(file.data as ArrayBuffer, {
    headers: {
      "Content-Type": "application/pdf",
      "Content-Disposition": `${disposition}; filename="resume_${variant}.pdf"`,
      "Cache-Control": "no-store",
    },
  });
}
