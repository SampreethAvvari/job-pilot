// Server-side only: variant -> resume PDF link, supplied via the RESUME_LINKS env
// var (JSON object, e.g. {"FDE":"https://drive.google.com/file/d/.../view"}).
// Kept out of the repo so personal documents never live in source control.
export function resumeLinksFromEnv(): Record<string, string> {
  try {
    return JSON.parse(process.env.RESUME_LINKS ?? "{}");
  } catch {
    return {};
  }
}
