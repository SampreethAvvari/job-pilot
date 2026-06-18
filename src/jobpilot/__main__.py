"""CLI entrypoint: python -m jobpilot [--dry-run] [--sources a,b] [--config path]."""

from __future__ import annotations

import argparse

from jobpilot.config import Config
from jobpilot.pipeline import run


def main() -> None:
    parser = argparse.ArgumentParser(prog="jobpilot")
    parser.add_argument("--dry-run", action="store_true", help="no Google/Gemini calls")
    parser.add_argument("--sources", default="", help="comma-separated subset of sources")
    parser.add_argument("--config", default="profile.yaml")
    parser.add_argument("--tailor-job", default="", help="tailor a single job by Job ID")
    parser.add_argument("--explain-job", default="",
                        help="rebuild the tailoring transparency report for one Job ID")
    parser.add_argument("--outreach-job", default="", help="draft outreach for one Job ID")
    parser.add_argument("--company-outreach", default="",
                        help="draft a company-wide cold-email (by company name)")
    parser.add_argument("--variant", default="",
                        help="force a resume variant for --company-outreach (AIE/FDE/MLE/SDE)")
    parser.add_argument("--fast", action="store_true",
                        help="fetch+score+record only (console refresh)")
    parser.add_argument("--inbox-watch", action="store_true",
                        help="check watched inboxes for replies and alert (skips pipeline)")
    parser.add_argument("--refresh-knowledge", action="store_true",
                        help="rebuild the Assistant knowledge pack (skips pipeline)")
    parser.add_argument("--rebuild-resume", default="",
                        help="regenerate a master resume variant through the judge loop")
    args = parser.parse_args()

    cfg = Config.load(args.config)

    if args.inbox_watch:
        import os
        from datetime import datetime, timezone

        from jobpilot import inboxwatch
        from jobpilot.gauth import credentials, inbox_credentials
        from jobpilot.scorer import make_gemini_llm

        creds = credentials()
        sid = os.environ.get("JOBPILOT_SPREADSHEET_ID") or cfg.sheet.spreadsheet_id
        llm = make_gemini_llm(cfg, schema=inboxwatch.FindingBatch)
        for note in inboxwatch.watch(creds, inbox_credentials(), sid, cfg, llm,
                                     datetime.now(timezone.utc)):
            print(note)
        return

    if args.refresh_knowledge:
        import os
        from datetime import datetime, timezone

        from jobpilot import knowledge
        from jobpilot.gauth import credentials

        creds = credentials()
        sid = os.environ.get("JOBPILOT_SPREADSHEET_ID") or cfg.sheet.spreadsheet_id
        for note in knowledge.refresh(creds, sid, cfg, datetime.now(timezone.utc)):
            print(note)
        return

    if args.rebuild_resume:
        import os
        from datetime import datetime, timezone

        from jobpilot.gauth import credentials
        from jobpilot.rebuild import rebuild_master
        from jobpilot.tailor import make_tailor_llm

        creds = credentials()
        sid = os.environ.get("JOBPILOT_SPREADSHEET_ID") or cfg.sheet.spreadsheet_id
        print(rebuild_master(creds, sid, args.rebuild_resume.upper(), cfg,
                             make_tailor_llm(cfg), datetime.now(timezone.utc)))
        return

    if args.company_outreach:
        import os
        from datetime import datetime, timezone

        import httpx

        from jobpilot import company_outreach
        from jobpilot.gauth import credentials
        from jobpilot.tailor import make_tailor_llm

        creds = credentials()
        sid = os.environ.get("JOBPILOT_SPREADSHEET_ID") or cfg.sheet.spreadsheet_id
        print(company_outreach.run(
            creds, sid, args.company_outreach, args.variant, cfg,
            make_tailor_llm(cfg), httpx.Client(timeout=30),
            datetime.now(timezone.utc)))
        return

    if args.tailor_job or args.outreach_job or args.explain_job:
        import os
        from datetime import datetime, timezone

        import httpx

        from jobpilot import sheets
        from jobpilot.gauth import credentials
        from jobpilot.outreach import outreach_row
        from jobpilot.tailor import make_tailor_llm, tailor_row

        creds = credentials()
        sid = os.environ.get("JOBPILOT_SPREADSHEET_ID") or cfg.sheet.spreadsheet_id
        job_id = args.tailor_job or args.outreach_job or args.explain_job
        rows = sheets.read_rows(creds, sid)
        row = next((r for r in rows if r["Job ID"] == job_id), None)
        if row is None:
            raise SystemExit(f"job id not found: {job_id}")
        llm = make_tailor_llm(cfg)
        if args.tailor_job:
            print(tailor_row(creds, sid, row, cfg, llm, datetime.now(timezone.utc)))
        elif args.explain_job:
            from jobpilot.explain import explain_job_row

            print(explain_job_row(creds, sid, row, cfg, llm,
                                  datetime.now(timezone.utc)))
        else:
            print(outreach_row(creds, sid, row, cfg, llm, httpx.Client(timeout=30)))
        return

    only = [s.strip() for s in args.sources.split(",") if s.strip()] or None
    run(cfg, dry_run=args.dry_run, only=only, fast=args.fast)


if __name__ == "__main__":
    main()
