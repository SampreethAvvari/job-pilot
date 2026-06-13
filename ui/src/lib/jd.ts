// Server-side job-description recovery, mirroring the pipeline's tailor._fetch_jd:
// use the stored excerpt when it is substantial, else pull the live posting page.
const MIN_JD = 200;
const MAX_JD = 6000;

export function jdIsThin(jd: string): boolean {
  return jd.trim().length < MIN_JD;
}

export async function fetchJd(url: string): Promise<string> {
  if (!url) return "";
  try {
    const res = await fetch(url, {
      headers: { "User-Agent": "Mozilla/5.0 (compatible; JobPilot)" },
      redirect: "follow",
    });
    if (!res.ok) return "";
    const html = await res.text();
    return html
      .replace(/<script[\s\S]*?<\/script>/gi, " ")
      .replace(/<style[\s\S]*?<\/style>/gi, " ")
      .replace(/<[^>]+>/g, " ")
      .replace(/&[a-z]+;/gi, " ")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, MAX_JD);
  } catch {
    return "";
  }
}
