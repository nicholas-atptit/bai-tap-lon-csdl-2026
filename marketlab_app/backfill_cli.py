"""`python -m marketlab_app.cli backfill ...` (historical OHLCV backfill, REAL_PRIVATE only).

  backfill run    --start-date 2023-01-01 --end-date latest|YYYY-MM-DD [--tickers A,B] [--dry-run] [--resume [--job-ref REF]]
  backfill backup [--no-restore-check]   verified COPY_ONLY backup of the business + ops databases
  backfill status [--job-ref REF] [--limit N]
  backfill report [--job-ref REF] [--out docs/BACKFILL_COVERAGE_REPORT.md] [--rerun-job REF --hash-before SHA]
  backfill hash   --start-date D --end-date D

Exit codes: 0 COMPLETED / DRY_RUN_OK; 10 lock busy; 20 COMPLETED_WITH_GAPS; 30 FAILED / INTERRUPTED / provider or DB error;
2 refused input or setup error.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

from .config import ROOT, Settings
from .db import DatabaseUnavailable, SqlError


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=1, default=str))


def add_parser(sub) -> None:
    bfp = sub.add_parser("backfill", help="historical OHLCV backfill (REAL_PRIVATE)")
    bfs = bfp.add_subparsers(dest="action", required=True)
    br = bfs.add_parser("run")
    br.add_argument("--start-date")
    br.add_argument("--end-date", default="latest")
    br.add_argument("--tickers", help="comma separated subset of the configured universe (default: all)")
    br.add_argument("--dry-run", action="store_true")
    br.add_argument("--resume", action="store_true", help="continue the latest unfinished job (or --job-ref)")
    br.add_argument("--job-ref")
    br.add_argument("--dataset-id", type=int)
    br.add_argument("--no-restore-check", action="store_true", help="backup: skip the test restore (VERIFYONLY + header still run)")
    bb = bfs.add_parser("backup")
    bb.add_argument("--no-restore-check", action="store_true")
    bst = bfs.add_parser("status")
    bst.add_argument("--job-ref")
    bst.add_argument("--limit", type=int, default=10)
    brp = bfs.add_parser("report")
    brp.add_argument("--job-ref")
    brp.add_argument("--out")
    brp.add_argument("--rerun-job", help="JobRef of a later job that re-ran a window of the main job (idempotency evidence)")
    brp.add_argument("--hash-before", help="values_sha256 of the rerun window taken before the rerun (backfill hash)")
    bh = bfs.add_parser("hash")
    bh.add_argument("--start-date", required=True)
    bh.add_argument("--end-date", required=True)


def _find_job(settings: Settings, ref: str) -> dict | None:
    from .eod import backfill as bf
    rows = [r for r in bf.jobs(settings, limit=1000) if r["JobRef"] == ref]
    return rows[0] if rows else None


def rerun_section(first: dict | None, rerun: dict | None, hash_before: str | None, hash_after: str | None) -> str:
    lines = ["## 5. Chạy lại cùng cửa sổ (idempotency)", "",
             "| Job | Cửa sổ | Trạng thái | Thêm mới | Không đổi | Thiếu | Trước lịch sử nguồn | Xung đột |", "|---|---|---|---|---|---|---|---|"]
    for r in (first, rerun):
        if r:
            lines.append(f"| `{r['JobRef']}` | {r['StartDate']} → {r['EndDate']} | {r['Status']} | {r['RowsInserted']} | {r['RowsUnchanged']} | "
                         f"{r['RowsMissing']} | {r['RowsNoHistory']} | {r['ConflictCount']} |")
    if hash_before:
        same = "giống hệt" if hash_before == hash_after else "KHÁC"
        lines += ["", f"SHA-256 giá trị của cửa sổ chạy lại: trước `{hash_before}`, sau `{hash_after}` → **{same}**."]
    return "\n".join(lines)


def cmd_backfill(args, settings: Settings) -> int:
    from .eod import backfill as bf
    from .eod.backup import BackupError, backup_for_backfill
    from .eod.coverage import coverage, table_hash, write_reports
    from .eod.opsstore import OpsStore

    if settings.is_demo:
        print("REFUSED: MARKETLAB_MODE=DEMO_OFFLINE uses the synthetic database; historical backfill of real data is disabled.", file=sys.stderr)
        return 2
    try:
        if args.action == "backup":
            res = backup_for_backfill(settings, restore_check=not args.no_restore_check)
            _print(res)
            return 0 if res["verified"] else 30
        if args.action == "run":
            start = dt.date.fromisoformat(args.start_date) if args.start_date else None
            tickers = [t for t in (args.tickers or "").replace(";", ",").split(",") if t.strip()] or None
            svc = bf.BackfillService(settings, trigger="CLI", progress=lambda m: print(f"[backfill] {m}", file=sys.stderr, flush=True),
                                     backup_fn=lambda: backup_for_backfill(settings, restore_check=not args.no_restore_check))
            res = svc.run(start, args.end_date, tickers, args.dry_run, args.resume, args.job_ref, args.dataset_id)
            _print(res)
            return res["exit_code"]
        if args.action == "status":
            if args.job_ref:
                job = _find_job(settings, args.job_ref)
                _print(bf.job_detail(settings, job["JobId"]) if job else {"error": "job not found"})
                return 0 if job else 2
            _print(bf.jobs(settings, limit=args.limit))
            return 0
        if args.action == "report":
            job = _find_job(settings, args.job_ref) if args.job_ref else None
            if args.job_ref and not job:
                print("job not found", file=sys.stderr)
                return 2
            cov = coverage(settings, job_id=job["JobId"] if job else None)
            extra = []
            if args.rerun_job:
                rerun = _find_job(settings, args.rerun_job)
                if not rerun:
                    print("rerun job not found", file=sys.stderr)
                    return 2
                cfg = OpsStore(settings).config()[0]
                after = table_hash(settings, cfg["DatasetId"], dt.date.fromisoformat(rerun["StartDate"]), dt.date.fromisoformat(rerun["EndDate"]))["values_sha256"]
                extra.append(rerun_section(job, rerun, args.hash_before, after))
            md, js = write_reports(cov, Path(args.out) if args.out else ROOT / "docs" / "BACKFILL_COVERAGE_REPORT.md", extra)
            _print({"markdown": str(md), "json": str(js), "coverage_status": cov["coverage_status"], "totals": cov["totals"],
                    "missing_sessions_total": cov["missing_sessions_total"], "no_history_sessions_total": cov["no_history_sessions_total"],
                    "calendar": cov["calendar"], "hash_window": cov["hash_window"]})
            return 0
        if args.action == "hash":
            cfg = OpsStore(settings).config()[0]
            _print(table_hash(settings, cfg["DatasetId"], dt.date.fromisoformat(args.start_date), dt.date.fromisoformat(args.end_date)))
            return 0
    except bf.BackfillError as exc:
        print(f"BACKFILL {exc.code}: {exc.message}", file=sys.stderr)
        return exc.exit_code
    except BackupError as exc:
        print(f"BACKUP ERROR: {exc}", file=sys.stderr)
        return 30
    except (DatabaseUnavailable, SqlError) as exc:
        print(f"DATABASE ERROR: {exc}", file=sys.stderr)
        return 30
    except ValueError as exc:
        print(f"INPUT ERROR: {exc}", file=sys.stderr)
        return 2
    return 2
