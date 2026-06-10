"""Resume gate CLI — runs the calibrated judge (src/jobpilot/judge.py).

Usage:
  1. Compile your variants to resumes/resume_<VARIANT>.pdf (pdflatex, see FORK-SETUP)
     with the .tex sources in private/ or src/jobpilot/resumes/ (or pass --dir).
  2. python scripts/ats_check.py [--min 90] [--verbose]

Prints score, category breakdown, keyword coverage, and every violation.
Exits non-zero if any resume fails the gate (score < min, >1 page, coverage < 85%).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from jobpilot.judge import KEYWORDS, judge, passes  # noqa: E402

ROOT = Path(__file__).parent.parent
DEFAULT_DIRS = [ROOT / "private", ROOT / "src" / "jobpilot" / "resumes"]
PDF_DIR = ROOT / "resumes"


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="", help="directory holding resume_<V>.tex files")
    ap.add_argument("--min", type=float, default=90.0)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    tex_dirs = [Path(args.dir)] if args.dir else DEFAULT_DIRS
    ok_all = True
    for variant, kws in KEYWORDS.items():
        tex = next((d / f"resume_{variant}.tex" for d in tex_dirs
                    if (d / f"resume_{variant}.tex").exists()), None)
        pdf = PDF_DIR / f"resume_{variant}.pdf"
        if tex is None or not pdf.exists():
            print(f"{variant}: SKIPPED (need {'tex' if tex is None else 'pdf'})")
            continue
        report = judge(tex.read_text(encoding="utf-8"), pdf.read_bytes(), kws)
        ok = passes(report, args.min)
        ok_all = ok_all and ok
        b = report["breakdown"]
        print(f"\n{variant}: {report['score']}/100  {'OK' if ok else 'FAIL'}"
              f"  [impact {b['impact']}/35 | brevity {b['brevity']}/20 | "
              f"style {b['style']}/15 | sections {b['sections']}/15 | "
              f"soft {b['soft_skills']}/15]  kw {report['keyword_coverage']:.0%}"
              f"  {report['pages']}pg {report['words']}w")
        shown = report["issues"] if args.verbose else report["issues"][:14]
        for i in shown:
            print("   -", i)
        if len(report["issues"]) > len(shown):
            print(f"   ... {len(report['issues']) - len(shown)} more (--verbose)")
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
