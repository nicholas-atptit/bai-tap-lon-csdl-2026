"""Historical OHLCV backfill (REAL_PRIVATE only), built on the existing EOD pipeline:

  provider adapter (kbs_bridge / FakeProvider in tests)
    -> validate_candle (same rules as daily EOD)
    -> ops.BackfillStaging (ops DB; checkpoint per ticker x year chunk in ops.BackfillFetch)
    -> ops.usp_EodApplySession, ONE transaction per session date (same procedure as daily EOD)
    -> ops audit: ops.EodRun (TriggerKind BACKFILL) + EodRunItem + PriceLoadLineage + PriceReconciliation
       + ops.BackfillSession (per-session checkpoint) + ops.BackfillJob (totals, backup evidence).

Rules
  * No TradeDate before settings.history_start (2023-01-01) is fetched-into-staging, written, or reported.
  * Session calendar = dates of the provider reference series (VN30 index) in the window: weekends and holidays are
    never "missing"; a date in dbo.TradingDay that the provider does not list is reported, never invented.
  * Same key + same values -> UNCHANGED (idempotent). Same key + different values -> CONFLICT: queued in
    ops.PriceReconciliation for human review, the stored row is NEVER overwritten.
  * Historical session (<= Dataset.ObservedThrough): written for the tickers that have a validated candle; tickers
    without one are MISSING (provider gap/error), NO_HISTORY (no provider candle on or before that date, e.g. listed
    later) or REJECTED_ROW. Such a session is PARTIAL, never SUCCESS / "30/30".
  * Session after ObservedThrough: same all-or-nothing rule as daily EOD (complete configured universe or nothing),
    so ObservedThrough only moves forward over complete sessions.
  * Atomic per session: a failing session rolls back alone; earlier sessions stay committed.
  * --resume reuses the staged provider data (no full re-download), refetches only FAILED chunks and re-processes only
    sessions that are not final.
  * Real (non dry-run) jobs require a verified backup of the business and ops databases first (marketlab_app.eod.backup).
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import json
import logging
import socket
import time
import traceback
import uuid
from decimal import Decimal

from .. import queries
from ..config import Settings
from ..db import DatabaseUnavailable, SqlError, connect, query, query_sets
from .calendar import now_vn, parse_cutoff
from .normalize import Candle, ValidationIssue, parse_trade_date, validate_candle
from .opsstore import OpsStore, _safe
from .providers import Provider, ProviderError, build_provider

log = logging.getLogger("marketlab.backfill")
EXIT = {"COMPLETED": 0, "DRY_RUN_OK": 0, "COMPLETED_WITH_GAPS": 20, "FAILED": 30, "INTERRUPTED": 30}
FINAL_SESSION = ("COMPLETE",)
LATEST_LOOKBACK_DAYS = 20
MAX_CONSECUTIVE_SQL_FAILURES = 3


class BackfillError(RuntimeError):
    def __init__(self, code: str, message: str, exit_code: int = 2):
        super().__init__(f"{code}: {message}")
        self.code, self.message, self.exit_code = code, message, exit_code


def year_chunks(start: dt.date, end: dt.date) -> list[tuple[dt.date, dt.date]]:
    out, a = [], start
    while a <= end:
        b = min(dt.date(a.year, 12, 31), end)
        out.append((a, b))
        a = b + dt.timedelta(days=1)
    return out


def completed_candidate(clock: dt.datetime | None, cutoff: str) -> dt.date:
    """Latest calendar date whose session can be complete now: today after the cutoff, else yesterday (VN time)."""
    local = now_vn(clock)
    d = local.date() if local.time() >= parse_cutoff(cutoff) else local.date() - dt.timedelta(days=1)
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d


def latest_completed_session(reference_dates: set[dt.date], candidate: dt.date) -> dt.date | None:
    """Provider evidence: the last reference candle on or before the candidate date (holidays handled by the provider)."""
    return max((d for d in reference_dates if d <= candidate), default=None)


def classify_session(session: dt.date, tickers: list[str], staged: dict[str, dict[dt.date, Candle]],
                     first_date: dict[str, dt.date | None], fetch_ok_through: dict[str, dt.date | None],
                     rejected_dates: dict[str, set[dt.date]]) -> dict[str, str]:
    """Per ticker: PRESENT | MISSING | NO_HISTORY | REJECTED_ROW. Pure (unit-tested).
    NO_HISTORY only when every chunk up to `session` was fetched successfully and the provider has no candle on or
    before `session` for that ticker; a failed fetch or a hole after the first candle is MISSING."""
    out = {}
    for t in tickers:
        if session in staged.get(t, {}):
            out[t] = "PRESENT"
        elif session in rejected_dates.get(t, set()):
            out[t] = "REJECTED_ROW"
        else:
            ok_through = fetch_ok_through.get(t)
            first = first_date.get(t)
            if ok_through is not None and ok_through >= session and (first is None or first > session):
                out[t] = "NO_HISTORY"
            else:
                out[t] = "MISSING"
    return out


class BackfillService:
    def __init__(self, settings: Settings, provider: Provider | None = None, clock: dt.datetime | None = None,
                 ops: OpsStore | None = None, trigger: str = "CLI", sleep=time.sleep, backup_fn=None, progress=None):
        self.settings = settings
        self.clock = clock
        self.ops = ops or OpsStore(settings)
        self.trigger = trigger
        self._provider = provider
        self.sleep = sleep
        self.backup_fn = backup_fn
        self.progress = progress or (lambda msg: None)
        self.ops_db = self.ops.db
        self.db = settings.sql_database

    # ---- helpers ---------------------------------------------------------------------------------------------
    def provider(self) -> Provider:
        if self._provider is None:
            if self.settings.is_demo:
                raise ProviderError("MODE_DEMO_OFFLINE", "backfill is disabled in DEMO_OFFLINE")
            self._provider = build_provider(dataclasses.replace(
                self.settings, provider_min_interval_seconds=max(self.settings.provider_min_interval_seconds,
                                                                 self.settings.backfill_min_interval_seconds)))
        return self._provider

    def today(self) -> dt.date:
        return now_vn(self.clock).date()

    def _ops(self, sql: str, params: tuple | list = ()) -> list[dict]:
        with connect(self.settings, self.ops_db) as c:
            return query(c, sql, params, self.settings)

    def _ops_exec(self, sql: str, *params) -> None:
        with connect(self.settings, self.ops_db) as c:
            c.cursor().execute(sql, *params)

    def schema_ready(self) -> None:
        v = self._ops("SELECT MAX(Version) AS v FROM ops.SchemaVersion")[0]["v"]
        if (v or 0) < 3:
            raise BackfillError("OPS_SCHEMA_V3_MISSING", f"ops database {self.ops_db} is at schema v{v}; run python -m marketlab_app.deploy ops-db "
                                "(applies sql/16_ops_schema_v3_backfill.sql)")

    def resolve(self, dataset_id: int | None) -> tuple[dict, list[dict], dict]:
        ok, why = self.ops.available()
        if not ok:
            raise BackfillError("OPS_UNAVAILABLE", why)
        cfgs = self.ops.config(dataset_id)
        if len(cfgs) != 1:
            raise BackfillError("EOD_CONFIG", f"{len(cfgs)} enabled ops.EodConfig row(s) for {self.db}"
                                + (f" dataset {dataset_id}" if dataset_id else "") + " (exactly one required; pass --dataset-id)")
        cfg = cfgs[0]
        with connect(self.settings) as c:
            ds = queries.dataset_exists(c, cfg["DatasetId"])
            st = queries.schema_status(c)
            uni = queries.universe(c, cfg["DatasetId"], cfg["IndexCode"], dt.date.fromisoformat(str(cfg["UniverseAsOf"])))
        if ds is None or ds["DataKind"] != "REAL_PRIVATE":
            raise BackfillError("DATASET_NOT_REAL_PRIVATE", "backfill writes only into REAL_PRIVATE datasets")
        if not st["eod_extension"]:
            raise BackfillError("EOD_EXTENSION_MISSING", "sql/13_eod_extension.sql is not applied to this business database")
        if st["user_tables"] != 13 or st["missing"]:
            raise BackfillError("SCHEMA_NOT_13_TABLES", f"business schema check failed: {st}")
        if not uni:
            raise BackfillError("UNIVERSE_EMPTY", "no configured universe members")
        return cfg, uni, ds

    # ---- lock (cross-process: CLI, web, scheduler) -----------------------------------------------------------
    def _acquire_lock(self, dataset_id: int):
        """Session-level applock held on a dedicated ops connection for the whole job (released when it closes)."""
        import pyodbc

        from ..db import connection_string
        c = pyodbc.connect(connection_string(self.settings, self.ops_db), timeout=self.settings.sql_login_timeout, autocommit=True)
        cur = c.cursor()
        cur.execute("DECLARE @r int; EXEC @r=sys.sp_getapplock @Resource=?, @LockMode='Exclusive', @LockOwner='Session', @LockTimeout=0; SELECT @r",
                    f"MarketLab.Backfill.{self.db}.{dataset_id}")
        if cur.fetchone()[0] < 0:
            c.close()
            raise BackfillError("LOCK_BUSY", "another backfill job holds the lock for this dataset", 10)
        return c

    def _release_lock(self, c, dataset_id: int) -> None:
        # explicit release: pyodbc pooling returns the connection to the pool without resetting the session, so a
        # session-owned applock would otherwise survive close() inside a long-lived process (the web server)
        try:
            c.cursor().execute("EXEC sys.sp_releaseapplock @Resource=?, @LockOwner='Session'", f"MarketLab.Backfill.{self.db}.{dataset_id}")
        except Exception:  # noqa: BLE001 - lock already gone with the session
            pass
        finally:
            try:
                c.close()
            except Exception:  # noqa: BLE001
                pass

    # ---- job rows ---------------------------------------------------------------------------------------------
    def _create_job(self, cfg, start, end, end_spec, tickers, uni, dry_run) -> tuple[int, str]:
        ref = str(uuid.uuid4())
        full = sorted(tickers) == sorted(u["Ticker"] for u in uni)
        with connect(self.settings, self.ops_db) as c:
            cur = c.cursor()
            cur.execute("""INSERT ops.BackfillJob(JobRef,DatabaseName,DatasetId,SourceCode,StartDate,EndDate,EndDateSpec,TickersJson,UniverseSize,
                             IsFullUniverse,IsDryRun,Status,HostName,TriggerKind,HeartbeatAtUtc)
                           OUTPUT INSERTED.JobId VALUES(?,?,?,?,?,?,?,?,?,?,?,'CREATED',?,?,SYSUTCDATETIME())""",
                        ref, self.db, cfg["DatasetId"], cfg["SourceCode"], start, end, end_spec[:20], json.dumps(tickers), len(uni),
                        1 if full else 0, 1 if dry_run else 0, socket.gethostname()[:128], self.trigger)
            return int(cur.fetchone()[0]), ref

    def _job(self, job_id: int) -> dict:
        return self._ops("SELECT * FROM ops.BackfillJob WHERE JobId=?", (job_id,))[0]

    def find_resumable(self, dataset_id: int, job_ref: str | None, dry_run: bool) -> dict | None:
        if job_ref:
            r = self._ops("SELECT * FROM ops.BackfillJob WHERE JobRef=? AND DatabaseName=? AND DatasetId=?", (job_ref, self.db, dataset_id))
            if not r:
                raise BackfillError("JOB_NOT_FOUND", f"no backfill job {job_ref} for {self.db}")
            return r[0]
        r = self._ops("""SELECT TOP 1 * FROM ops.BackfillJob WHERE DatabaseName=? AND DatasetId=? AND IsDryRun=?
                          AND Status IN ('CREATED','FETCHING','APPLYING','FAILED','INTERRUPTED','COMPLETED_WITH_GAPS') ORDER BY JobId DESC""",
                      (self.db, dataset_id, 1 if dry_run else 0))
        return r[0] if r else None

    def _status(self, job_id: int, status: str, code: str | None = None, message: str | None = None, final: bool = False) -> None:
        self._ops_exec(f"""UPDATE ops.BackfillJob SET Status=?,ErrorCode=?,Message=?,HeartbeatAtUtc=SYSUTCDATETIME()
                           {",FinishedAtUtc=SYSUTCDATETIME()" if final else ",FinishedAtUtc=NULL"} WHERE JobId=?""",
                       status, code, _safe(message, self.settings), job_id)

    def _totals(self, job_id: int) -> None:
        self._ops_exec("""UPDATE j SET SessionsProcessed=s.n,RowsInserted=s.i,RowsUnchanged=s.u,RowsWouldInsert=s.w,RowsMissing=s.m,
                            RowsNoHistory=s.nh,RowsRejected=s.r,ConflictCount=s.c,HeartbeatAtUtc=SYSUTCDATETIME()
                          FROM ops.BackfillJob j CROSS APPLY (SELECT COUNT(*) n,ISNULL(SUM(Inserted),0) i,ISNULL(SUM(Unchanged),0) u,
                            ISNULL(SUM(WouldInsert),0) w,ISNULL(SUM(Missing),0) m,ISNULL(SUM(NoHistory),0) nh,ISNULL(SUM(Rejected),0) r,
                            ISNULL(SUM(Conflicts),0) c FROM ops.BackfillSession WHERE JobId=j.JobId) s WHERE j.JobId=?""", job_id)

    # ---- public entry -----------------------------------------------------------------------------------------
    def run(self, start_date: dt.date | None, end_spec: str = "latest", tickers: list[str] | None = None, dry_run: bool = False,
            resume: bool = False, job_ref: str | None = None, dataset_id: int | None = None, backup: dict | None = None) -> dict:
        if self.settings.is_demo:
            raise BackfillError("MODE_DEMO_OFFLINE", "DEMO_OFFLINE uses the synthetic database; historical backfill of real data is disabled")
        self.schema_ready()
        cfg, uni, ds = self.resolve(dataset_id)
        dataset_id = cfg["DatasetId"]
        try:                                       # configuration errors fail fast, before any job row or retry/backoff
            self.provider()
        except ProviderError as exc:
            raise BackfillError(exc.code, exc.message, 2) from None
        lock = self._acquire_lock(dataset_id)      # before any job row: a busy lock leaves nothing behind
        job_id = None
        try:
            job_id, ref, start, end, tickers = self._open_job(cfg, uni, start_date, end_spec, tickers, dry_run, resume, job_ref)
            return self._execute(job_id, ref, cfg, uni, tickers, start, end, dry_run, backup)
        except KeyboardInterrupt:
            if job_id:
                self._totals(job_id)
                self._status(job_id, "INTERRUPTED", "INTERRUPTED", "interrupted by operator; resume with --resume", final=True)
            raise
        except BackfillError as exc:
            if job_id:
                self._totals(job_id)
                self._status(job_id, "FAILED", exc.code, exc.message, final=True)
            raise
        except Exception as exc:  # noqa: BLE001 - every failure is recorded on the job
            log.error("backfill job failed: %s", traceback.format_exc())
            code = "DB_UNAVAILABLE" if isinstance(exc, DatabaseUnavailable) else (f"SQL_{exc.number}" if isinstance(exc, SqlError) else "INTERNAL_ERROR")
            if job_id:
                self._totals(job_id)
                self._status(job_id, "FAILED", code, f"{type(exc).__name__}: {str(exc)[:400]}", final=True)
            raise BackfillError(code, str(exc)[:400], 30) from None
        finally:
            self._release_lock(lock, dataset_id)

    def _open_job(self, cfg, uni, start_date, end_spec, tickers, dry_run, resume, job_ref):
        dataset_id = cfg["DatasetId"]
        floor = self.settings.history_start
        job = self.find_resumable(dataset_id, job_ref, dry_run) if (resume or job_ref) else None
        if (resume or job_ref) and job is None:
            raise BackfillError("NOTHING_TO_RESUME", "no unfinished backfill job for this dataset (start a new one without --resume)")
        if job is not None:
            if bool(job["IsDryRun"]) != dry_run:
                raise BackfillError("RESUME_MODE_MISMATCH", f"job {job['JobRef']} is {'a dry run' if job['IsDryRun'] else 'a real run'}")
            if start_date and start_date.isoformat() != job["StartDate"]:
                raise BackfillError("RESUME_RANGE_MISMATCH", f"job {job['JobRef']} covers {job['StartDate']}..{job['EndDate']}")
            start, end = dt.date.fromisoformat(job["StartDate"]), dt.date.fromisoformat(job["EndDate"])
            tickers = json.loads(job["TickersJson"])
            job_id, ref = job["JobId"], job["JobRef"]
            self._ops_exec("UPDATE ops.BackfillJob SET ResumeCount=ResumeCount+1 WHERE JobId=?", job_id)
            # runs of THIS job left RUNNING by a killed process: the session transaction either committed or rolled back
            # inside SQL Server; the session is re-applied below (idempotent) and the stale audit row is closed.
            self._ops_exec("""UPDATE ops.EodRun SET Status='FAILED',ErrorCode='ABANDONED',FinishedAtUtc=SYSUTCDATETIME(),
                              Message=N'backfill process ended before recording completion; session re-applied on resume'
                              WHERE BatchRef=? AND TriggerKind='BACKFILL' AND Status='RUNNING'""", ref)
            self.progress(f"resuming job {ref} ({start}..{end}, {len(tickers)} tickers)")
            return job_id, ref, start, end, tickers
        start = start_date or floor
        if start < floor:
            raise BackfillError("BEFORE_HISTORY_START", f"start {start} is before the history floor {floor}: refused")
        names = {u["Ticker"] for u in uni}
        tickers = sorted({t.strip().upper() for t in tickers}) if tickers else sorted(names)
        bad = [t for t in tickers if t not in names]
        if bad:
            raise BackfillError("TICKER_NOT_IN_UNIVERSE", f"not in the configured universe: {', '.join(bad[:10])}")
        end = self._resolve_end(cfg, end_spec)
        if end < start:
            raise BackfillError("EMPTY_RANGE", f"end {end} < start {start}")
        job_id, ref = self._create_job(cfg, start, end, end_spec, tickers, uni, dry_run)
        self.progress(f"job {ref} created: {start}..{end} ({end_spec}), {len(tickers)} tickers, dry_run={dry_run}")
        return job_id, ref, start, end, tickers

    def _resolve_end(self, cfg: dict, end_spec: str) -> dt.date:
        candidate = completed_candidate(self.clock, str(cfg["CutoffLocalTime"])[:5])
        if end_spec != "latest":
            try:
                d = dt.date.fromisoformat(end_spec)
            except ValueError:
                raise BackfillError("BAD_END_DATE", "end date must be YYYY-MM-DD or 'latest'") from None
            if d > candidate:
                raise BackfillError("END_NOT_COMPLETED", f"{d} is not a completed session yet (latest possible {candidate}, Asia/Ho_Chi_Minh, cutoff {str(cfg['CutoffLocalTime'])[:5]})")
            return d
        ref = cfg["CalendarReferenceSymbol"]
        try:
            res = self.provider().fetch([ref], candidate - dt.timedelta(days=LATEST_LOOKBACK_DAYS), min(candidate + dt.timedelta(days=1), self.today()))
        except ProviderError as exc:
            raise BackfillError(exc.code, f"cannot determine the latest completed session: {exc.message}", 30) from None
        if res.errors.get(ref):
            raise BackfillError("PROVIDER_ERROR", f"reference {ref}: {res.errors[ref][:200]}", 30)
        dates = set()
        for r in res.rows.get(ref, []):
            try:
                dates.add(parse_trade_date(r.get("time")))
            except ValidationIssue:
                continue
        latest = latest_completed_session(dates, candidate)
        if latest is None:
            raise BackfillError("NO_COMPLETED_SESSION", f"provider shows no {ref} session in the {LATEST_LOOKBACK_DAYS} days before {candidate}", 30)
        return latest

    # ---- execution ----------------------------------------------------------------------------------------------
    def _execute(self, job_id, ref, cfg, uni, tickers, start, end, dry_run, backup) -> dict:
        job = self._job(job_id)
        if not dry_run and self.trigger != "TEST" and not job.get("BackupVerifiedAtUtc"):
            ev = backup or (self.backup_fn() if self.backup_fn else None)
            if not ev or not ev.get("verified"):
                raise BackfillError("BACKUP_REQUIRED", "a verified backup of the business and ops databases is required before a real backfill "
                                    "(python -m marketlab_app.cli backfill backup, or let backfill run take it)")
            self._ops_exec("UPDATE ops.BackfillJob SET BackupFile=?,BackupVerifiedAtUtc=SYSUTCDATETIME() WHERE JobId=?",
                           "; ".join(b["file"] for b in ev["backups"])[:400], job_id)
        self._status(job_id, "FETCHING")
        ref_symbol = cfg["CalendarReferenceSymbol"]
        self._fetch_all(job_id, tickers, ref_symbol, start, end)
        self._status(job_id, "APPLYING")
        summary = self._apply_all(job_id, ref, cfg, uni, tickers, ref_symbol, start, end, dry_run)
        self._totals(job_id)
        job = self._job(job_id)
        fetch_failed = self._ops("SELECT COUNT(*) AS n FROM ops.BackfillFetch WHERE JobId=? AND Status='FAILED'", (job_id,))[0]["n"]
        sess = self._ops("SELECT Status, COUNT(*) AS n FROM ops.BackfillSession WHERE JobId=? GROUP BY Status", (job_id,))
        counts = {r["Status"]: r["n"] for r in sess}
        planned = summary["sessions_planned"]
        if dry_run:
            status, code = "DRY_RUN_OK", None
            msg = (f"dry run: {planned} session(s); would insert {job['RowsWouldInsert']}, unchanged {job['RowsUnchanged']}, "
                   f"missing {job['RowsMissing']}, no provider history {job['RowsNoHistory']}, rejected {job['RowsRejected']}, conflicts {job['ConflictCount']}")
        elif counts.get("FAILED"):
            status, code = "FAILED", "SESSION_FAILURES"
            msg = f"{counts['FAILED']} session(s) failed and were rolled back; resume with --resume"
        elif counts.get("COMPLETE", 0) == planned and not fetch_failed:
            status, code, msg = "COMPLETED", None, f"{planned} complete session(s); inserted {job['RowsInserted']}, unchanged {job['RowsUnchanged']}"
        else:
            status, code = "COMPLETED_WITH_GAPS", "GAPS_REMAIN"
            msg = (f"{counts.get('COMPLETE', 0)}/{planned} complete session(s); inserted {job['RowsInserted']}, unchanged {job['RowsUnchanged']}, "
                   f"missing {job['RowsMissing']}, no provider history {job['RowsNoHistory']}, rejected {job['RowsRejected']}, conflicts {job['ConflictCount']}"
                   + (f", {fetch_failed} failed fetch chunk(s)" if fetch_failed else ""))
        if summary.get("tickers_only_dates"):
            msg += (f"; {len(summary['tickers_only_dates'])} session(s) taken from stock candles because the reference series omitted them "
                    f"({', '.join(summary['tickers_only_dates'][:5])})")
        if summary.get("calendar_db_only"):
            msg += f"; {len(summary['calendar_db_only'])} dbo.TradingDay date(s) absent from the provider calendar (reported, not changed)"
        self._status(job_id, status, code, msg, final=True)
        job = self._job(job_id)
        return {"job_id": job_id, "job_ref": ref, "status": status, "error_code": code, "message": msg, "exit_code": EXIT[status],
                "start_date": start.isoformat(), "end_date": end.isoformat(), "tickers": len(tickers), "dry_run": dry_run,
                "sessions_planned": planned, "session_status_counts": counts, "fetch_failed_chunks": fetch_failed,
                "rows_inserted": job["RowsInserted"], "rows_unchanged": job["RowsUnchanged"], "rows_would_insert": job["RowsWouldInsert"],
                "rows_missing": job["RowsMissing"], "rows_no_history": job["RowsNoHistory"], "rows_rejected": job["RowsRejected"],
                "conflicts": job["ConflictCount"], "fetch_calls": job["FetchCalls"], "fetch_retries": job["FetchRetries"],
                "calendar_db_only": summary.get("calendar_db_only", []), "extra_provider_dates": summary.get("extra_dates", 0),
                "calendar_evidence": summary.get("calendar_evidence", {}), "tickers_only_dates": summary.get("tickers_only_dates", []),
                "reference_only_dates": summary.get("reference_only_dates", [])}

    # ---- fetch phase ---------------------------------------------------------------------------------------------
    def _fetch_all(self, job_id: int, tickers: list[str], ref_symbol: str, start: dt.date, end: dt.date) -> None:
        symbols = [ref_symbol] + tickers
        chunks = year_chunks(start, end)
        for attempt in range(1, self.settings.backfill_fetch_passes + 1):
            done = {(r["Ticker"], r["ChunkStart"]) for r in
                    self._ops("SELECT Ticker, ChunkStart FROM ops.BackfillFetch WHERE JobId=? AND Status='FETCHED'", (job_id,))}
            pending = [(a, b, [s for s in symbols if (s, a.isoformat()) not in done]) for a, b in chunks]
            pending = [(a, b, syms) for a, b, syms in pending if syms]
            if not pending:
                return
            if attempt > 1:
                wait = self.settings.backfill_retry_base_seconds * (3 ** (attempt - 2))
                self.progress(f"retry pass {attempt}: {sum(len(p[2]) for p in pending)} (symbol, chunk) fetch(es) after {wait:.0f}s backoff")
                self.sleep(wait)
                self._ops_exec("UPDATE ops.BackfillJob SET FetchRetries=FetchRetries+? WHERE JobId=?", sum(len(p[2]) for p in pending), job_id)
            for a, b, syms in pending:
                self._fetch_chunk(job_id, syms, ref_symbol, a, b)

    def _fetch_chunk(self, job_id: int, syms: list[str], ref_symbol: str, a: dt.date, b: dt.date) -> None:
        req_end = min(b + dt.timedelta(days=1), self.today())   # KBS 'end' may be exclusive; drop later candles below
        self.progress(f"fetch {a}..{b}: {len(syms)} symbol(s)")
        self._ops_exec("UPDATE ops.BackfillJob SET FetchCalls=FetchCalls+1,HeartbeatAtUtc=SYSUTCDATETIME() WHERE JobId=?", job_id)
        try:
            res = self.provider().fetch(syms, a, req_end)
            fatal = None
        except ProviderError as exc:
            res, fatal = None, exc
        if res is not None and res.meta:
            self._ops_exec("UPDATE ops.BackfillJob SET ProviderMeta=? WHERE JobId=?",
                           _safe(json.dumps({k: res.meta.get(k) for k in ("source", "package", "package_version", "pandas_version", "basis_note",
                                                                         "bridge_finished_utc", "called_utc")}, default=str), self.settings, 4000), job_id)
        for s in syms:
            if fatal is not None:
                self._record_fetch(job_id, s, a, b, s == ref_symbol, "FAILED", 1, 0, 0, 0, 0, None, None, fatal.code, fatal.message)
                continue
            if res.errors.get(s):
                attempts = (res.meta.get("attempts") or {}).get(s, self.settings.provider_max_attempts)
                self._record_fetch(job_id, s, a, b, s == ref_symbol, "FAILED", attempts or 1, 0, 0, 0, 0, None, None, "PROVIDER_ERROR", res.errors[s][:500])
                continue
            self._stage(job_id, s, a, b, s == ref_symbol, res.rows.get(s, []), (res.meta.get("attempts") or {}).get(s, 1),
                        (res.meta.get("empty") or {}).get(s))

    def _stage(self, job_id: int, sym: str, a: dt.date, b: dt.date, is_ref: bool, raw_rows: list[dict], attempts: int,
               empty_note: str | None = None) -> None:
        floor = self.settings.history_start
        good: dict[dt.date, Candle] = {}
        conflicted: set[dt.date] = set()
        rejects: list[tuple] = []
        out_of_window = 0
        last = None
        unordered = 0
        for i, raw in enumerate(raw_rows):
            try:
                d = parse_trade_date(raw.get("time"))
            except ValidationIssue as exc:
                rejects.append((i, str(raw.get("time"))[:40], None, exc.code, exc.detail[:400]))
                continue
            if d < a or d > b or d < floor:
                out_of_window += 1
                continue
            if last is not None and d < last:
                unordered += 1
            last = d
            try:
                cd = validate_candle(sym, raw)
            except ValidationIssue as exc:
                rejects.append((i, str(raw.get("time"))[:40], d, exc.code, exc.detail[:400]))
                continue
            prev = good.get(d)
            if prev is not None and prev.values() != cd.values():
                conflicted.add(d)
                rejects.append((i, str(raw.get("time"))[:40], d, "SOURCE_DUPLICATE_CONFLICT", f"{sym} {d} has two different candles"))
                continue
            good[d] = cd
        for d in conflicted:
            good.pop(d, None)
        with connect(self.settings, self.ops_db, autocommit=False) as c:
            cur = c.cursor()
            cur.execute("DELETE ops.BackfillStaging WHERE JobId=? AND Ticker=? AND TradeDate BETWEEN ? AND ?", job_id, sym, a, b)
            cur.execute("DELETE ops.BackfillReject WHERE JobId=? AND Ticker=? AND ChunkStart=?", job_id, sym, a)
            cur.execute("DELETE ops.BackfillFetch WHERE JobId=? AND Ticker=? AND ChunkStart=?", job_id, sym, a)
            if good:
                cur.fast_executemany = True
                cur.executemany("INSERT ops.BackfillStaging(JobId,Ticker,TradeDate,OpenPrice,HighPrice,LowPrice,ClosePrice,Volume) VALUES(?,?,?,?,?,?,?,?)",
                                [(job_id, sym, d, x.open, x.high, x.low, x.close, x.volume) for d, x in sorted(good.items())])
                cur.fast_executemany = False
            if rejects:
                cur.executemany("INSERT ops.BackfillReject(JobId,Ticker,ChunkStart,RowNo,RawTime,TradeDate,Code,Detail) VALUES(?,?,?,?,?,?,?,?)",
                                [(job_id, sym, a, *r) for r in rejects])
            notes = ([f"provider reported no data for this window: {empty_note}"] if empty_note else []) +                     ([f"{unordered} out-of-order row(s) re-sorted"] if unordered else [])
            msg = "; ".join(notes)[:600] or None
            cur.execute("""INSERT ops.BackfillFetch(JobId,Ticker,ChunkStart,ChunkEnd,IsReference,Status,Attempts,RowsReceived,RowsStaged,RowsRejected,
                             RowsOutOfWindow,FirstDate,LastDate,ErrorCode,Message) VALUES(?,?,?,?,?,'FETCHED',?,?,?,?,?,?,?,NULL,?)""",
                        job_id, sym, a, b, 1 if is_ref else 0, int(attempts or 1), len(raw_rows), len(good), len(rejects), out_of_window,
                        min(good) if good else None, max(good) if good else None, msg)
            c.commit()

    def _record_fetch(self, job_id, sym, a, b, is_ref, status, attempts, received, staged, rejected, oow, first, last, code, message) -> None:
        with connect(self.settings, self.ops_db, autocommit=False) as c:
            cur = c.cursor()
            cur.execute("DELETE ops.BackfillFetch WHERE JobId=? AND Ticker=? AND ChunkStart=?", job_id, sym, a)
            cur.execute("""INSERT ops.BackfillFetch(JobId,Ticker,ChunkStart,ChunkEnd,IsReference,Status,Attempts,RowsReceived,RowsStaged,RowsRejected,
                             RowsOutOfWindow,FirstDate,LastDate,ErrorCode,Message) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        job_id, sym, a, b, 1 if is_ref else 0, status, int(attempts), received, staged, rejected, oow, first, last, code,
                        _safe(message, self.settings, 600))
            c.commit()

    # ---- apply phase ---------------------------------------------------------------------------------------------
    def _load_staged(self, job_id: int, syms: list[str]) -> dict[str, dict[dt.date, Candle]]:
        out: dict[str, dict[dt.date, Candle]] = {s: {} for s in syms}
        with connect(self.settings, self.ops_db) as c:
            cur = c.cursor()
            cur.execute("SELECT Ticker,TradeDate,OpenPrice,HighPrice,LowPrice,ClosePrice,Volume FROM ops.BackfillStaging WHERE JobId=? ORDER BY Ticker,TradeDate", job_id)
            for t, d, o, h, lo, cl, v in cur.fetchall():
                if t in out:
                    d = d if isinstance(d, dt.date) else dt.date.fromisoformat(str(d))
                    out[t][d] = Candle(t, d, Decimal(o), Decimal(h), Decimal(lo), Decimal(cl), int(v))
        return out

    def _apply_all(self, job_id, ref, cfg, uni, tickers, ref_symbol, start, end, dry_run) -> dict:
        dataset_id = cfg["DatasetId"]
        stock_ids = {u["Ticker"]: u["StockId"] for u in uni}
        staged = self._load_staged(job_id, [ref_symbol] + tickers)
        fetches = self._ops("SELECT Ticker,ChunkStart,ChunkEnd,Status FROM ops.BackfillFetch WHERE JobId=?", (job_id,))
        chunks = year_chunks(start, end)
        status_of = {(f["Ticker"], f["ChunkStart"]): f["Status"] for f in fetches}
        fetch_ok_through: dict[str, dt.date | None] = {}
        for t in tickers:
            ok = None
            for a, b in chunks:
                if status_of.get((t, a.isoformat())) == "FETCHED":
                    ok = b
                else:
                    break
            fetch_ok_through[t] = ok
        ref_chunks_ok = [(a, b) for a, b in chunks if status_of.get((ref_symbol, a.isoformat())) == "FETCHED"]
        # Session calendar = provider evidence: a weekday with a reference-series candle, OR with candles for at least half
        # of the job tickers (the KBS index series was observed to omit a real session intermittently: 2025-04-04 present in
        # one call, absent in the next, while all 30 stocks had candles). Only inside chunks where the reference was fetched.
        def in_ok(d):
            return start <= d <= end and any(a <= d <= b for a, b in ref_chunks_ok)
        ref_dates = {d for d in staged[ref_symbol] if in_ok(d)}
        per_day: dict[dt.date, int] = {}
        for t in tickers:
            for d in staged[t]:
                if in_ok(d) and d.weekday() < 5:
                    per_day[d] = per_day.get(d, 0) + 1
        threshold = max(1, -(-len(tickers) // 2))
        tick_dates = {d for d, k in per_day.items() if k >= threshold}
        calendar = sorted(ref_dates | tick_dates)
        evidence = {d: ("REFERENCE+TICKERS" if d in ref_dates and d in tick_dates else "REFERENCE_ONLY" if d in ref_dates else "TICKERS_ONLY")
                    for d in calendar}
        if not ref_chunks_ok:
            raise BackfillError("REFERENCE_UNAVAILABLE", f"provider reference series {ref_symbol} could not be fetched; no session calendar, nothing applied", 30)
        uncovered = [(a, b) for a, b in chunks if (a, b) not in ref_chunks_ok]
        rejected_dates: dict[str, set[dt.date]] = {t: set() for t in tickers}
        for r in self._ops("SELECT Ticker,TradeDate FROM ops.BackfillReject WHERE JobId=? AND TradeDate IS NOT NULL", (job_id,)):
            if r["Ticker"] in rejected_dates:
                rejected_dates[r["Ticker"]].add(dt.date.fromisoformat(r["TradeDate"]))
        first_date = {t: (min(staged[t]) if staged[t] else None) for t in tickers}
        cal_set = set(calendar)
        extra_dates = sum(1 for t in tickers for d in staged[t] if d not in cal_set and start <= d <= end and not any(a <= d <= b for a, b in uncovered))
        with connect(self.settings) as c:
            db_days = [dt.date.fromisoformat(r["TradeDate"]) for r in
                       query(c, "SELECT TradeDate FROM dbo.TradingDay WHERE DatasetId=? AND TradeDate BETWEEN ? AND ?", (dataset_id, start, end))]
            observed = dt.date.fromisoformat(queries.dataset_exists(c, dataset_id)["ObservedThrough"])
        calendar_db_only = sorted(d.isoformat() for d in db_days if d not in cal_set and not any(a <= d <= b for a, b in uncovered))
        done = {r["SessionDate"]: r for r in self._ops("SELECT SessionDate,Status,Missing,Rejected FROM ops.BackfillSession WHERE JobId=?", (job_id,))}
        full_universe = sorted(tickers) == sorted(stock_ids)
        self._ops_exec("UPDATE ops.BackfillJob SET SessionsPlanned=? WHERE JobId=?", len(calendar), job_id)
        consecutive_sql = 0
        tail_blocked = None
        for n, session in enumerate(calendar, start=1):
            prev = done.get(session.isoformat())
            if prev and (prev["Status"] in FINAL_SESSION or (prev["Status"] in ("PARTIAL", "DRY_RUN_PARTIAL", "DRY_RUN_OK") and prev["Missing"] == 0 and prev["Rejected"] == 0)):
                continue
            states = classify_session(session, tickers, staged, first_date, fetch_ok_through, rejected_dates)
            if session > observed and tail_blocked is not None:
                # ObservedThrough must never jump over a session that could not be written completely
                self._session_row(job_id, session, "NOT_WRITTEN", "TAIL_BLOCKED_BY_EARLIER_GAP", None,
                                  {"Requested": len(tickers), "Present": sum(1 for t in tickers if states[t] == "PRESENT"),
                                   "Missing": sum(1 for t in tickers if states[t] == "MISSING"),
                                   "NoHistory": sum(1 for t in tickers if states[t] == "NO_HISTORY"),
                                   "Rejected": sum(1 for t in tickers if states[t] == "REJECTED_ROW")}, 0, 0, 0, 0, None,
                                  f"not written: earlier session {tail_blocked} after ObservedThrough is incomplete")
                continue
            status = self._apply_session(job_id, ref, dataset_id, cfg["SourceCode"], session, tickers, states, staged, stock_ids,
                                         dry_run, observed, full_universe, evidence[session])
            if session > observed:
                if status not in ("COMPLETE", "DRY_RUN_OK"):
                    tail_blocked = session
                elif not dry_run:
                    with connect(self.settings) as c:
                        observed = dt.date.fromisoformat(queries.dataset_exists(c, dataset_id)["ObservedThrough"])
            consecutive_sql = consecutive_sql + 1 if status == "FAILED" else 0
            if consecutive_sql >= MAX_CONSECUTIVE_SQL_FAILURES:
                raise BackfillError("REPEATED_SQL_FAILURES", f"{consecutive_sql} consecutive session failures (last {session}); stopped, earlier sessions committed", 30)
            if n % 25 == 0 or n == len(calendar):
                self._totals(job_id)
                self.progress(f"applied {n}/{len(calendar)} session(s) (last {session})")
        ev_counts: dict[str, int] = {}
        for v in evidence.values():
            ev_counts[v] = ev_counts.get(v, 0) + 1
        self.progress(f"calendar evidence: {ev_counts}")
        return {"sessions_planned": len(calendar), "calendar_db_only": calendar_db_only, "extra_dates": extra_dates,
                "calendar_evidence": ev_counts, "tickers_only_dates": sorted(d.isoformat() for d, v in evidence.items() if v == "TICKERS_ONLY"),
                "reference_only_dates": sorted(d.isoformat() for d, v in evidence.items() if v == "REFERENCE_ONLY")}

    def _stored(self, dataset_id: int, session: dt.date, sids: list[int]) -> dict[int, tuple]:
        with connect(self.settings) as c:
            rows = query(c, f"""SELECT StockId,OpenPrice,HighPrice,LowPrice,ClosePrice,Volume FROM dbo.DailyPrice
                                WHERE DatasetId=? AND TradeDate=? AND StockId IN ({','.join('?' for _ in sids)})""", [dataset_id, session] + sids)
        return {r["StockId"]: (Decimal(str(r["OpenPrice"])), Decimal(str(r["HighPrice"])), Decimal(str(r["LowPrice"])),
                               Decimal(str(r["ClosePrice"])), int(r["Volume"])) for r in rows}

    def _proc(self, dataset_id, session, run_ref, present, staged, stock_ids, dry_run):
        payload = json.dumps([staged[t][session].as_payload(stock_ids[t]) for t in present])
        expected = json.dumps(sorted(stock_ids[t] for t in present))
        with connect(self.settings) as c:
            return query_sets(c, "EXEC ops.usp_EodApplySession @DatasetId=?, @SessionDate=?, @EodRunRef=?, @PricesJson=?, @ExpectedStockIdsJson=?, @DryRun=?",
                              (dataset_id, session, run_ref, payload, expected, 1 if dry_run else 0), self.settings)

    def _apply_session(self, job_id, job_ref, dataset_id, source, session, tickers, states, staged, stock_ids, dry_run,
                       observed, full_universe, evidence: str = "REFERENCE+TICKERS") -> str:
        """Applies one session in its own transaction; returns the BackfillSession status."""
        present = [t for t in tickers if states[t] == "PRESENT"]
        missing = [t for t in tickers if states[t] == "MISSING"]
        nohist = [t for t in tickers if states[t] == "NO_HISTORY"]
        rejected = [t for t in tickers if states[t] == "REJECTED_ROW"]
        gaps = missing + rejected + nohist
        tail = session > observed
        items = []
        for t in missing:
            items.append({"ticker": t, "stock_id": stock_ids[t], "outcome": "MISSING", "detail": "no validated provider candle for this session (provider gap or failed fetch)"})
        for t in nohist:
            items.append({"ticker": t, "stock_id": stock_ids[t], "outcome": "NO_HISTORY", "detail": "provider has no candle for this ticker on or before this date (listed later / history starts later)"})
        for t in rejected:
            items.append({"ticker": t, "stock_id": stock_ids[t], "outcome": "REJECTED_ROW", "detail": "provider candle failed validation (ops.BackfillReject)"})
        base = {"Requested": len(tickers), "Present": len(present), "Missing": len(missing), "NoHistory": len(nohist), "Rejected": len(rejected)}
        miss_text = ", ".join((f"{t}:M" for t in missing)) or None
        if tail and (gaps or not full_universe):
            why = ("session after Dataset.ObservedThrough needs the complete configured universe (same all-or-nothing rule as daily EOD); "
                   f"{len(gaps)} ticker(s) without a candle" if gaps else "session after ObservedThrough cannot be written by a ticker-subset job")
            self._session_row(job_id, session, "NOT_WRITTEN", "TAIL_REQUIRES_COMPLETE_UNIVERSE", None, base, 0, 0, 0, 0, miss_text, why, evidence)
            return "NOT_WRITTEN"
        if not present:
            self._session_row(job_id, session, "NOT_WRITTEN", "NO_PROVIDER_DATA", None, base, 0, 0, 0, 0, miss_text,
                              "no ticker has a validated candle for this provider session", evidence)
            return "NOT_WRITTEN"
        run_id = run_ref = None
        if not dry_run:
            run_id, run_ref = self.ops.start_run(dataset_id, session, source, "BACKFILL", False, job_ref)
        run_ref = run_ref or f"dry-{job_ref}"
        conflicts: list[dict] = []
        to_apply = list(present)
        sets = None
        error = None
        for _ in range(2):
            try:
                sets = self._proc(dataset_id, session, run_ref, to_apply, staged, stock_ids, dry_run)
                break
            except SqlError as exc:
                if exc.number == 51145 and not conflicts:
                    stored = self._stored(dataset_id, session, [stock_ids[t] for t in to_apply])
                    for t in to_apply:
                        s = stored.get(stock_ids[t])
                        if s is not None and s != staged[t][session].values():
                            cd = staged[t][session]
                            conflicts.append({"ticker": t, "stock_id": stock_ids[t], "trade_date": session, "stored": s,
                                              "provider": (cd.open, cd.high, cd.low, cd.close, cd.volume)})
                    to_apply = [t for t in to_apply if t not in {x["ticker"] for x in conflicts}]
                    if not conflicts:
                        error = exc
                        break
                    if not to_apply:
                        sets = None
                        break
                    continue
                error = exc
                break
        recon_added = 0
        if conflicts and not dry_run:
            recon_added = self.ops.add_reconciliation(run_id, dataset_id, conflicts, "SESSION_CONFLICT")
        for x in conflicts:
            items.append({"ticker": x["ticker"], "stock_id": x["stock_id"], "outcome": "CONFLICT",
                          "detail": "stored closed price differs from provider; kept stored row, queued for review"})
        if error is not None:
            for t in to_apply:
                items.append({"ticker": t, "stock_id": stock_ids[t], "outcome": "NOT_WRITTEN", "detail": f"session rolled back: SQL {error.number}"})
            if run_id:
                self.ops.add_items(run_id, items)
                self.ops.finish_run(run_id, "FAILED", requested=len(tickers), received=len(present), error_code=f"SQL_{error.number}",
                                    message=error.message, observed_before=observed.isoformat())
            self._session_row(job_id, session, "FAILED", f"SQL_{error.number}", run_id, base, 0, 0, 0, len(conflicts), miss_text, error.message[:900], evidence)
            return "FAILED"
        inserted = unchanged = would = 0
        observed_after = observed.isoformat()
        if sets:
            outcomes, summary = sets[0], sets[1][0]
            for o in outcomes:
                items.append({"ticker": o["Ticker"], "stock_id": o["StockId"], "outcome": o["Outcome"], "detail": None})
            inserted, unchanged, would = summary["InsertedCount"], summary["UnchangedCount"], summary["WouldInsertCount"]
            observed_after = summary["ObservedThroughAfter"]
        complete = full_universe and not gaps and not conflicts
        if dry_run:
            status = "DRY_RUN_OK" if complete else "DRY_RUN_PARTIAL"
            msg = f"dry run (rolled back): would insert {would}, unchanged {unchanged}"
        else:
            status = "COMPLETE" if complete else "PARTIAL"
            msg = f"inserted {inserted}, unchanged {unchanged} of {len(tickers)}"
            if run_id:
                self.ops.add_items(run_id, items)
                keys = [(o["StockId"], session) for o in (sets[0] if sets else []) if o["Outcome"] == "INSERTED"]
                self.ops.add_lineage(run_id, dataset_id, source, keys)
                code = None
                if not complete:
                    code = ("REVISION_CONFLICT" if conflicts else "MISSING_TICKERS" if (missing or rejected) else
                            "NO_PROVIDER_HISTORY" if nohist else "SUBSET_JOB")
                self.ops.finish_run(run_id, "SUCCESS" if complete else "PARTIAL", requested=len(tickers), received=len(present),
                                    inserted=inserted, unchanged=unchanged, rejected=len(rejected), error_code=code,
                                    message=(f"historical backfill job {job_ref}: {msg}"
                                             + (f"; missing {len(missing)}, no provider history {len(nohist)}, rejected {len(rejected)}, "
                                                f"conflicts {len(conflicts)} ({recon_added} new review item(s))" if not complete else "")),
                                    observed_before=observed.isoformat(), observed_after=observed_after,
                                    provider_meta={"trigger": "BACKFILL", "job_ref": job_ref, "served_from": "ops.BackfillStaging"})
        if conflicts:
            msg += f"; {len(conflicts)} conflict(s) kept stored values" + ("" if dry_run else f" ({recon_added} new review item(s))")
        self._session_row(job_id, session, status, None if complete else ("REVISION_CONFLICT" if conflicts else "GAPS"), run_id, base,
                          inserted, unchanged, would, len(conflicts), miss_text, msg, evidence)
        return status

    def _session_row(self, job_id, session, status, code, run_id, base, inserted, unchanged, would, conflicts, missing_text, message,
                     evidence: str | None = None) -> None:
        if evidence:
            message = f"[calendar {evidence}] {message}"
        with connect(self.settings, self.ops_db, autocommit=False) as c:
            cur = c.cursor()
            # a session re-processed on resume keeps job semantics: Inserted = rows this job added (cumulative),
            # Unchanged = rows that were already stored before this job
            cur.execute("SELECT Inserted FROM ops.BackfillSession WITH (UPDLOCK) WHERE JobId=? AND SessionDate=?", job_id, session)
            prev = cur.fetchone()
            if prev and prev[0] and not status.startswith("DRY_RUN"):
                inserted, unchanged = inserted + prev[0], max(0, unchanged - prev[0])
            cur.execute("DELETE ops.BackfillSession WHERE JobId=? AND SessionDate=?", job_id, session)
            cur.execute("""INSERT ops.BackfillSession(JobId,SessionDate,Status,ErrorCode,EodRunId,Requested,Present,Inserted,Unchanged,WouldInsert,
                             Missing,NoHistory,Rejected,Conflicts,MissingTickers,Message) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        job_id, session, status, code, run_id, base["Requested"], base["Present"], inserted, unchanged, would,
                        base["Missing"], base["NoHistory"], base["Rejected"], conflicts, (missing_text or None) and missing_text[:400],
                        _safe(message, self.settings, 1000))
            c.commit()


# ---- read side (CLI status, web page, coverage report) ---------------------------------------------------------------
def jobs(settings: Settings, ops_db: str | None = None, limit: int = 20) -> list[dict]:
    with connect(settings, ops_db or settings.ops_database) as c:
        return query(c, """SELECT TOP (?) JobId,JobRef,DatasetId,StartDate,EndDate,EndDateSpec,UniverseSize,IsFullUniverse,IsDryRun,Status,ErrorCode,Message,
                             SessionsPlanned,SessionsProcessed,RowsInserted,RowsUnchanged,RowsWouldInsert,RowsMissing,RowsNoHistory,RowsRejected,
                             ConflictCount,FetchCalls,FetchRetries,ResumeCount,BackupFile,BackupVerifiedAtUtc,TriggerKind,CreatedAtUtc,HeartbeatAtUtc,FinishedAtUtc,
                             DATEDIFF(second,CreatedAtUtc,ISNULL(FinishedAtUtc,SYSUTCDATETIME())) AS DurationSec,
                             (SELECT COUNT(*) FROM OPENJSON(TickersJson)) AS TickerCount
                           FROM ops.BackfillJob WHERE DatabaseName=? ORDER BY JobId DESC""", (limit, settings.sql_database))


def job_detail(settings: Settings, job_id: int, ops_db: str | None = None) -> dict | None:
    with connect(settings, ops_db or settings.ops_database) as c:
        r = query(c, "SELECT * FROM ops.BackfillJob WHERE JobId=? AND DatabaseName=?", (job_id, settings.sql_database))
        if not r:
            return None
        job = r[0]
        job["ProviderMeta"] = json.loads(job["ProviderMeta"]) if job.get("ProviderMeta") else None
        job["fetch"] = query(c, """SELECT Ticker,IsReference,COUNT(*) AS Chunks,SUM(CASE WHEN Status='FETCHED' THEN 1 ELSE 0 END) AS ChunksOk,
                                     SUM(RowsReceived) AS RowsReceived,SUM(RowsStaged) AS RowsStaged,SUM(RowsRejected) AS RowsRejected,
                                     SUM(RowsOutOfWindow) AS RowsOutOfWindow,MIN(FirstDate) AS FirstDate,MAX(LastDate) AS LastDate,MAX(Attempts) AS MaxAttempts,
                                     MAX(ErrorCode) AS ErrorCode
                                   FROM ops.BackfillFetch WHERE JobId=? GROUP BY Ticker,IsReference ORDER BY IsReference DESC,Ticker""", (job_id,))
        job["sessions"] = query(c, """SELECT Status,ErrorCode,COUNT(*) AS n,MIN(SessionDate) AS FirstDate,MAX(SessionDate) AS LastDate,
                                        SUM(Inserted) AS Inserted,SUM(Unchanged) AS Unchanged,SUM(WouldInsert) AS WouldInsert,SUM(Missing) AS Missing,
                                        SUM(NoHistory) AS NoHistory,SUM(Rejected) AS Rejected,SUM(Conflicts) AS Conflicts
                                      FROM ops.BackfillSession WHERE JobId=? GROUP BY Status,ErrorCode ORDER BY Status""", (job_id,))
        job["problem_sessions"] = query(c, """SELECT TOP 40 SessionDate,Status,ErrorCode,Present,Requested,Missing,NoHistory,Rejected,Conflicts,MissingTickers,Message
                                              FROM ops.BackfillSession WHERE JobId=? AND (Missing>0 OR Rejected>0 OR Conflicts>0 OR Status IN ('FAILED','NOT_WRITTEN'))
                                              ORDER BY SessionDate DESC""", (job_id,))
        job["rejects"] = query(c, "SELECT TOP 40 Ticker,TradeDate,Code,Detail FROM ops.BackfillReject WHERE JobId=? ORDER BY Ticker,RowNo", (job_id,))
    return job
