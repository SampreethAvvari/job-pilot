// Word-level LCS diff for the tailoring report panel: which words of the
// tailored text are new vs the baseline. Pure, no deps.

export type DiffSeg = { text: string; added: boolean };

function norm(w: string): string {
  return w.toLowerCase().replace(/^[^a-z0-9%$]+|[^a-z0-9%$]+$/g, "");
}

export function diffWords(baseline: string, tailored: string): DiffSeg[] {
  const a = baseline.split(/\s+/).filter(Boolean);
  const b = tailored.split(/\s+/).filter(Boolean);
  if (!b.length) return [];
  // Sections are bullet-sized; cap the table to stay O(small).
  if (!a.length || a.length * b.length > 250_000) {
    return [{ text: b.join(" "), added: !a.length }];
  }
  const an = a.map(norm);
  const bn = b.map(norm);
  const m = a.length;
  const n = b.length;
  const dp: number[][] = Array.from({ length: m + 1 }, () =>
    new Array<number>(n + 1).fill(0),
  );
  for (let i = m - 1; i >= 0; i--) {
    for (let j = n - 1; j >= 0; j--) {
      dp[i][j] =
        an[i] === bn[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const added: boolean[] = new Array(n).fill(true);
  let i = 0;
  let j = 0;
  while (i < m && j < n) {
    if (an[i] === bn[j]) {
      added[j] = false;
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) i++;
    else j++;
  }
  const segs: DiffSeg[] = [];
  for (let k = 0; k < n; k++) {
    const last = segs[segs.length - 1];
    if (last && last.added === added[k]) last.text += ` ${b[k]}`;
    else segs.push({ text: b[k], added: added[k] });
  }
  return segs;
}
