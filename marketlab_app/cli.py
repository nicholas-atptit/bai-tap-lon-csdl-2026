"""Command line: python -m marketlab_app.cli <command>

  eod sync     [--date YYYY-MM-DD] [--dry-run] [--dataset-id N] [--if-needed] [--trigger CLI|SCHEDULER]
  eod backfill --from YYYY-MM-DD --to YYYY-MM-DD [--dry-run] [--max-sessions N] [--continue-on-error]
  eod status   [--dataset-id N] [--limit 10]
  eod reconcile list|approve|reject ...
  backfill run|backup|status|report|hash ...   (see marketlab_app/backfill_cli.py)
  serve        [--port 8000]

Exit codes: 0 SUCCESS / DRY_RUN_OK / NO_SESSION; 10 SKIPPED; 20 PARTIAL; 30 FAILED; 2 configuration/setup error.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys

from .config import ConfigError, Settings, load_settings
from .db import DatabaseUnavailable, SqlError, connect, query


def setup_logging(settings: Settings, name: str) -> None:
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    path = settings.log_dir / f"{name}_{dt.date.today():%Y%m%d}.log"
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not any(isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", "") == str(path) for h in root.handlers):
        fh = logging.FileHandler(path, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(fmt)
        root.addHandler(sh)


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=1, default=str))


def cmd_eod(args, settings: Settings) -> int:
    from .eod.opsstore import OpsStore
    from .eod.service import EodService, EodSetupError

    if settings.is_demo and args.action in ("sync", "backfill"):
        print("REFUSED: MARKETLAB_MODE=DEMO_OFFLINE uses the synthetic database; EOD sync of real data is disabled. "
              "Use REAL_PRIVATE with a REAL_PRIVATE database.", file=sys.stderr)
        return 2
    svc = EodService(settings, trigger=getattr(args, "trigger", "CLI"))
    try:
        if args.action == "sync":
            date = dt.date.fromisoformat(args.date) if args.date else None
            if args.if_needed:
                cfg = svc.resolve_config(args.dataset_id)
                from .eod.calendar import default_session_date
                d = date or default_session_date()
                done = svc.already_succeeded(cfg["DatasetId"], d)
                if done and not args.dry_run:
                    _print({"status": "ALREADY_SUCCEEDED", "session_date": d.isoformat(), "eod_run_id": done, "exit_code": 0})
                    return 0
            r = svc.sync_session(date, args.dataset_id, args.dry_run)
            _print(r.to_dict())
            return r.exit_code
        if args.action == "backfill":
            if dt.date.fromisoformat(args.date_from) < settings.history_start:
                print(f"REFUSED: --from is before the history floor {settings.history_start} (MARKETLAB_HISTORY_START)", file=sys.stderr)
                return 2
            res = svc.backfill(dt.date.fromisoformat(args.date_from), dt.date.fromisoformat(args.date_to), args.dataset_id,
                               args.dry_run, args.max_sessions, stop_on_error=not args.continue_on_error)
            _print({k: v for k, v in res.items() if k != "runs"} | {"runs": [
                {k: r[k] for k in ("eod_run_id", "session_date", "status", "error_code", "inserted", "unchanged", "requested", "message")}
                for r in res["runs"]]})
            return res["exit_code"]
        ops = OpsStore(settings)
        if args.action == "status":
            cfg = svc.resolve_config(args.dataset_id)
            runs, total = ops.runs(cfg["DatasetId"], args.limit, 0)
            with connect(settings) as c:
                ds = query(c, "SELECT DatasetId,DatasetCode,DataKind,ObservedThrough FROM dbo.Dataset WHERE DatasetId=?", (cfg["DatasetId"],))[0]
            _print({"dataset": ds, **ops.last_status(cfg["DatasetId"]), "recent_runs": runs, "total_runs": total})
            return 0
        if args.action == "reconcile":
            cfg = svc.resolve_config(args.dataset_id)
            if args.recon_action == "list":
                _print(ops.reconciliation(cfg["DatasetId"], args.status, args.limit))
                return 0
            if not args.reviewer or not args.note:
                print("--reviewer and --note are required for a review decision", file=sys.stderr)
                return 2
            if args.recon_action == "reject":
                _print(ops.review(args.id, "REJECTED", args.reviewer, args.note) or {"error": "not found or already reviewed"})
                return 0
            # approve: explicit human decision; applies the provider value through usp_InsertDailyPrice @AllowUpdate=1
            if not args.i_understand_this_overwrites_a_closed_price:
                print("Approval overwrites a stored closed price. Re-run with --i-understand-this-overwrites-a-closed-price", file=sys.stderr)
                return 2
            items = [r for r in ops.reconciliation(cfg["DatasetId"], "PENDING_REVIEW", 1000) if r["ReconId"] == args.id]
            if not items:
                print("reconciliation item not found or not pending", file=sys.stderr)
                return 2
            it = items[0]
            with connect(settings) as c:
                c.cursor().execute("EXEC dbo.usp_InsertDailyPrice ?,?,?,?,?,?,?,?,1", cfg["DatasetId"], it["StockId"], it["TradeDate"],
                                   it["ProviderOpen"], it["ProviderHigh"], it["ProviderLow"], it["ProviderClose"], it["ProviderVolume"])
            _print(ops.review(args.id, "APPROVED_UPDATE", args.reviewer, args.note))
            return 0
    except EodSetupError as exc:
        print(f"SETUP ERROR: {exc}", file=sys.stderr)
        return 2
    except (DatabaseUnavailable, SqlError) as exc:
        print(f"DATABASE ERROR: {exc}", file=sys.stderr)
        return 30
    except ValueError as exc:
        print(f"INPUT ERROR: {exc}", file=sys.stderr)
        return 2
    return 2


def cmd_check(settings: Settings) -> int:
    import pyodbc

    from . import queries
    from .eod.opsstore import OpsStore
    result: dict = {"config": settings.redacted(), "checks": {}}
    ok = True
    drivers = pyodbc.drivers()
    result["checks"]["odbc_driver"] = {"ok": settings.sql_driver in drivers, "available": [d for d in drivers if "SQL" in d]}
    ok &= result["checks"]["odbc_driver"]["ok"]
    try:
        with connect(settings) as c:
            st = queries.schema_status(c)
            kinds = queries.dataset_kinds(c)
        expected = "SYNTHETIC" if settings.is_demo else "REAL_PRIVATE"
        result["checks"]["database"] = {"ok": True}
        result["checks"]["schema"] = {"ok": not st["missing"] and st["marketlab_schema"] == "1.0", **st}
        result["checks"]["mode"] = {"ok": bool(kinds) and set(kinds) == {expected}, "expected": expected, "dataset_kinds": kinds}
        ok &= result["checks"]["schema"]["ok"] and result["checks"]["mode"]["ok"]
    except (DatabaseUnavailable, SqlError) as exc:
        result["checks"]["database"] = {"ok": False, "error": str(exc)}
        ok = False
    if not settings.is_demo:
        ops_ok, why = OpsStore(settings).available()
        result["checks"]["ops_database"] = {"ok": ops_ok, "detail": why, "blocking": False}
        result["checks"]["provider_python"] = {"ok": bool(settings.provider_python), "blocking": False}
        result["checks"]["ops_token"] = {"ok": bool(settings.ops_token), "blocking": False}
    result["ok"] = bool(ok)
    _print(result)
    return 0 if ok else 3


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m marketlab_app.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("eod")
    es = e.add_subparsers(dest="action", required=True)
    s = es.add_parser("sync")
    s.add_argument("--date")
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--dataset-id", type=int)
    s.add_argument("--if-needed", action="store_true", help="exit 0 without a new run when this session already has SUCCESS")
    s.add_argument("--trigger", choices=["CLI", "SCHEDULER"], default="CLI")
    b = es.add_parser("backfill")
    b.add_argument("--from", dest="date_from", required=True)
    b.add_argument("--to", dest="date_to", required=True)
    b.add_argument("--dry-run", action="store_true")
    b.add_argument("--dataset-id", type=int)
    b.add_argument("--max-sessions", type=int)
    b.add_argument("--continue-on-error", action="store_true")
    st = es.add_parser("status")
    st.add_argument("--dataset-id", type=int)
    st.add_argument("--limit", type=int, default=10)
    rc = es.add_parser("reconcile")
    rc.add_argument("recon_action", choices=["list", "approve", "reject"])
    rc.add_argument("--dataset-id", type=int)
    rc.add_argument("--status", choices=["PENDING_REVIEW", "APPROVED_UPDATE", "REJECTED"])
    rc.add_argument("--limit", type=int, default=50)
    rc.add_argument("--id", type=int)
    rc.add_argument("--reviewer")
    rc.add_argument("--note")
    rc.add_argument("--i-understand-this-overwrites-a-closed-price", action="store_true")
    sv = sub.add_parser("serve")
    sv.add_argument("--port", type=int)
    sub.add_parser("check", help="validate .env, ODBC driver, DB connectivity, schema and mode (no server)")
    from .backfill_cli import add_parser as add_backfill_parser
    add_backfill_parser(sub)
    args = ap.parse_args(argv)
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"CONFIG ERROR: {exc}", file=sys.stderr)
        return 2
    if args.cmd == "check":
        return cmd_check(settings)
    if args.cmd == "serve":
        import uvicorn
        from .web_app import create_app
        setup_logging(settings, "web")
        # log_config=None: uvicorn loggers propagate to the root logger -> var/logs/api_<date>.log (+ stderr).
        # Request lines contain path + query only; the ops token travels in a header and is never logged.
        uvicorn.run(create_app(settings), host=settings.host, port=args.port or settings.port, log_level="info",
                    log_config=None, proxy_headers=False, server_header=False)
        return 0
    if args.cmd == "backfill":
        from .backfill_cli import cmd_backfill
        setup_logging(settings, "backfill")
        return cmd_backfill(args, settings)
    setup_logging(settings, "eod")
    return cmd_eod(args, settings)


if __name__ == "__main__":
    raise SystemExit(main())
