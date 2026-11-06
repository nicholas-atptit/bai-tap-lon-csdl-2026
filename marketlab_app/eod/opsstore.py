"""Audit trail in the ops database. Every write is its own autocommit transaction, independent of the
business-data transaction, so FAILED/PARTIAL outcomes are recorded even after a full rollback."""
from __future__ import annotations

import datetime as dt
import json
import socket
import uuid

from ..config import Settings
from ..db import DatabaseUnavailable, SqlError, connect, query

TERMINAL = ("SUCCESS", "FAILED", "SKIPPED", "NO_SESSION", "PARTIAL", "DRY_RUN_OK")


def _safe(text: str | None, settings: Settings, limit: int = 2000) -> str | None:
    if text is None:
        return None
    for secret in (settings.ops_token, settings.sql_password):
        if secret:
            text = text.replace(secret, "***")
    return text[:limit]


class OpsStore:
    def __init__(self, settings: Settings, ops_database: str | None = None, business_database: str | None = None):
        self.settings = settings
        self.db = ops_database or settings.ops_database
        self.business_db = business_database or settings.sql_database

    # ---- availability / configuration -------------------------------------------------------------
    def available(self) -> tuple[bool, str]:
        try:
            with connect(self.settings, self.db) as c:
                v = query(c, "SELECT MAX(Version) AS v FROM ops.SchemaVersion")[0]["v"]
            return (v is not None and v >= 1), f"ops schema version {v}"
        except DatabaseUnavailable as exc:
            return False, f"ops database '{self.db}' not reachable: {exc}"
        except SqlError as exc:
            return False, f"ops database '{self.db}' not initialised (python -m marketlab_app.deploy ops-db): SQL {exc.number}"

    def config(self, dataset_id: int | None = None) -> list[dict]:
        with connect(self.settings, self.db) as c:
            if dataset_id is None:
                return query(c, "SELECT * FROM ops.EodConfig WHERE DatabaseName=? AND Enabled=1 ORDER BY DatasetId", (self.business_db,))
            return query(c, "SELECT * FROM ops.EodConfig WHERE DatabaseName=? AND DatasetId=? AND Enabled=1", (self.business_db, dataset_id))

    # ---- run lifecycle -----------------------------------------------------------------------------
    def start_run(self, dataset_id: int, session: dt.date, source: str, trigger: str, dry_run: bool,
                  batch_ref: str | None = None) -> tuple[int, str]:
        ref = str(uuid.uuid4())
        with connect(self.settings, self.db) as c:
            cur = c.cursor()
            cur.execute("""INSERT ops.EodRun(RunRef,BatchRef,DatabaseName,DatasetId,SessionDate,SourceCode,TriggerKind,IsDryRun,Status,HostName)
                           OUTPUT INSERTED.EodRunId VALUES(?,?,?,?,?,?,?,?,'RUNNING',?)""",
                        ref, batch_ref, self.business_db, dataset_id, session, source, trigger, 1 if dry_run else 0, socket.gethostname()[:128])
            run_id = int(cur.fetchone()[0])
        return run_id, ref

    def finish_run(self, run_id: int, status: str, *, requested=0, received=0, inserted=0, unchanged=0, rejected=0,
                   would_insert=None, error_code=None, message=None, provider_last=None, observed_before=None,
                   observed_after=None, provider_meta: dict | None = None) -> None:
        assert status in TERMINAL, status
        with connect(self.settings, self.db) as c:
            c.cursor().execute(
                """UPDATE ops.EodRun SET Status=?,RequestedCount=?,ReceivedCount=?,InsertedCount=?,UnchangedCount=?,RejectedCount=?,
                       WouldInsertCount=?,ErrorCode=?,Message=?,ProviderLastCandleDate=?,ObservedThroughBefore=?,ObservedThroughAfter=?,
                       ProviderMeta=?,FinishedAtUtc=SYSUTCDATETIME() WHERE EodRunId=? AND Status='RUNNING'""",
                status, requested, received, inserted, unchanged, rejected, would_insert, error_code,
                _safe(message, self.settings), provider_last, observed_before, observed_after,
                _safe(json.dumps(provider_meta, ensure_ascii=False, default=str), self.settings, 4000) if provider_meta else None,
                run_id)

    def add_items(self, run_id: int, items: list[dict]) -> None:
        if not items:
            return
        with connect(self.settings, self.db) as c:
            cur = c.cursor()
            cur.fast_executemany = False
            cur.executemany("INSERT ops.EodRunItem(EodRunId,Ticker,StockId,Outcome,Detail) VALUES(?,?,?,?,?)",
                            [(run_id, i["ticker"], i.get("stock_id"), i["outcome"], _safe(i.get("detail"), self.settings, 400)) for i in items])

    def add_reconciliation(self, run_id: int, dataset_id: int, rows: list[dict], detected_by: str) -> int:
        added = 0
        with connect(self.settings, self.db) as c:
            cur = c.cursor()
            for r in rows:
                cur.execute("""SELECT 1 FROM ops.PriceReconciliation WHERE DatabaseName=? AND DatasetId=? AND StockId=? AND TradeDate=?
                               AND Status='PENDING_REVIEW' AND ProviderOpen=? AND ProviderHigh=? AND ProviderLow=? AND ProviderClose=? AND ProviderVolume=?""",
                            self.business_db, dataset_id, r["stock_id"], r["trade_date"], *r["provider"])
                if cur.fetchone():
                    continue
                cur.execute("""INSERT ops.PriceReconciliation(EodRunId,DatabaseName,DatasetId,StockId,Ticker,TradeDate,
                               StoredOpen,StoredHigh,StoredLow,StoredClose,StoredVolume,ProviderOpen,ProviderHigh,ProviderLow,ProviderClose,ProviderVolume,DetectedBy)
                               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            run_id, self.business_db, dataset_id, r["stock_id"], r["ticker"], r["trade_date"], *r["stored"], *r["provider"], detected_by)
                added += 1
        return added

    def add_lineage(self, run_id: int, dataset_id: int, source: str, keys: list[tuple[int, dt.date]]) -> None:
        if not keys:
            return
        with connect(self.settings, self.db) as c:
            c.cursor().executemany(
                """INSERT ops.PriceLoadLineage(DatabaseName,DatasetId,StockId,TradeDate,EodRunId,SourceCode)
                   SELECT ?,?,?,?,?,? WHERE NOT EXISTS(SELECT 1 FROM ops.PriceLoadLineage WHERE DatabaseName=? AND DatasetId=? AND StockId=? AND TradeDate=?)""",
                [(self.business_db, dataset_id, sid, d, run_id, source, self.business_db, dataset_id, sid, d) for sid, d in keys])

    def add_eval_snapshot(self, run_id: int, rows: list[dict]) -> None:
        if not rows:
            return
        with connect(self.settings, self.db) as c:
            c.cursor().executemany(
                """INSERT ops.EvaluationSnapshot(EodRunId,RunId,RunCode,AsOfDate,TotalPredictions,EligibleRows,Accuracy,BrierScore,NaturalLogLoss)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                [(run_id, r["RunId"], r["RunCode"], r["AsOfDate"], r["TotalPredictions"], r["EvaluatedRows"],
                  r["Accuracy"], r["BrierScore"], r["NaturalLogLoss"]) for r in rows])

    def mark_abandoned(self, older_than_minutes: int = 120) -> int:
        with connect(self.settings, self.db) as c:
            cur = c.cursor()
            cur.execute("""UPDATE ops.EodRun SET Status='FAILED',ErrorCode='ABANDONED',FinishedAtUtc=SYSUTCDATETIME(),
                           Message=CONCAT(N'Run left RUNNING for more than ',?,N' minutes (process ended?); no completion recorded.')
                           WHERE DatabaseName=? AND Status='RUNNING' AND StartedAtUtc<DATEADD(minute,-?,SYSUTCDATETIME())""",
                        older_than_minutes, self.business_db, older_than_minutes)
            return cur.rowcount

    # ---- reads ---------------------------------------------------------------------------------------
    def runs(self, dataset_id: int | None, limit: int, offset: int, status: str | None = None,
             include_backfill: bool = False) -> tuple[list[dict], int]:
        where, params = ["DatabaseName=?"], [self.business_db]
        if not include_backfill:
            where.append("TriggerKind<>'BACKFILL'")
        if dataset_id is not None:
            where.append("DatasetId=?")
            params.append(dataset_id)
        if status:
            where.append("Status=?")
            params.append(status)
        w = " AND ".join(where)
        with connect(self.settings, self.db) as c:
            total = query(c, f"SELECT COUNT(*) AS n FROM ops.EodRun WHERE {w}", params)[0]["n"]
            items = query(c, f"""SELECT EodRunId,RunRef,BatchRef,DatasetId,SessionDate,SourceCode,TriggerKind,IsDryRun,Status,
                                  RequestedCount,ReceivedCount,InsertedCount,UnchangedCount,RejectedCount,WouldInsertCount,
                                  StartedAtUtc,FinishedAtUtc,DATEDIFF(millisecond,StartedAtUtc,ISNULL(FinishedAtUtc,SYSUTCDATETIME())) AS DurationMs,
                                  ErrorCode,Message,ProviderLastCandleDate,ObservedThroughBefore,ObservedThroughAfter
                                 FROM ops.EodRun WHERE {w} ORDER BY EodRunId DESC OFFSET ? ROWS FETCH NEXT ? ROWS ONLY""",
                          params + [offset, limit])
        return items, total

    def run_detail(self, run_id: int) -> dict | None:
        with connect(self.settings, self.db) as c:
            r = query(c, "SELECT * FROM ops.EodRun WHERE EodRunId=? AND DatabaseName=?", (run_id, self.business_db))
            if not r:
                return None
            run = r[0]
            run["ProviderMeta"] = json.loads(run["ProviderMeta"]) if run.get("ProviderMeta") else None
            run["items"] = query(c, "SELECT Ticker,StockId,Outcome,Detail FROM ops.EodRunItem WHERE EodRunId=? ORDER BY Ticker", (run_id,))
            run["reconciliation"] = query(c, "SELECT ReconId,Ticker,TradeDate,StoredClose,ProviderClose,StoredVolume,ProviderVolume,DetectedBy,Status FROM ops.PriceReconciliation WHERE EodRunId=? ORDER BY Ticker,TradeDate", (run_id,))
            run["evaluation"] = query(c, "SELECT RunId,RunCode,AsOfDate,TotalPredictions,EligibleRows,Accuracy,BrierScore,NaturalLogLoss FROM ops.EvaluationSnapshot WHERE EodRunId=? ORDER BY RunId", (run_id,))
        return run

    def last_status(self, dataset_id: int) -> dict:
        with connect(self.settings, self.db) as c:
            q = lambda sql: (query(c, sql, (self.business_db, dataset_id)) or [{}])[0]  # noqa: E731
            # daily EOD runs only: historical backfill sessions (TriggerKind BACKFILL) are reported on the backfill page
            last = q("SELECT TOP 1 EodRunId,SessionDate,Status,IsDryRun,ErrorCode,Message,StartedAtUtc,FinishedAtUtc,InsertedCount,UnchangedCount,RequestedCount FROM ops.EodRun WHERE DatabaseName=? AND DatasetId=? AND TriggerKind<>'BACKFILL' ORDER BY EodRunId DESC")
            last_real = q("SELECT TOP 1 EodRunId,SessionDate,Status,StartedAtUtc FROM ops.EodRun WHERE DatabaseName=? AND DatasetId=? AND IsDryRun=0 AND TriggerKind<>'BACKFILL' ORDER BY EodRunId DESC")
            success = q("SELECT MAX(SessionDate) AS d FROM ops.EodRun WHERE DatabaseName=? AND DatasetId=? AND Status='SUCCESS'")
            provider = q("SELECT MAX(ProviderLastCandleDate) AS d FROM ops.EodRun WHERE DatabaseName=? AND DatasetId=?")
            pending = q("SELECT COUNT(*) AS n FROM ops.PriceReconciliation WHERE DatabaseName=? AND DatasetId=? AND Status='PENDING_REVIEW'")
        return {"last_run": last or None, "last_real_run": last_real or None,
                "last_requested_date": (last or {}).get("SessionDate"),
                "last_successful_trade_date": success.get("d"),
                "last_provider_candle_date": provider.get("d"),
                "pending_reconciliation": pending.get("n", 0)}

    def reconciliation(self, dataset_id: int, status: str | None, limit: int) -> list[dict]:
        where, params = ["DatabaseName=?", "DatasetId=?"], [self.business_db, dataset_id]
        if status:
            where.append("Status=?")
            params.append(status)
        with connect(self.settings, self.db) as c:
            return query(c, f"""SELECT TOP (?) ReconId,EodRunId,Ticker,StockId,TradeDate,StoredOpen,StoredHigh,StoredLow,StoredClose,StoredVolume,
                                ProviderOpen,ProviderHigh,ProviderLow,ProviderClose,ProviderVolume,DetectedBy,Status,DetectedAtUtc,ReviewedBy,ReviewedAtUtc,ReviewNote
                                FROM ops.PriceReconciliation WHERE {' AND '.join(where)} ORDER BY ReconId DESC""", [limit] + params)

    def review(self, recon_id: int, status: str, reviewer: str, note: str) -> dict | None:
        assert status in ("APPROVED_UPDATE", "REJECTED")
        with connect(self.settings, self.db) as c:
            cur = c.cursor()
            cur.execute("""UPDATE ops.PriceReconciliation SET Status=?,ReviewedBy=?,ReviewedAtUtc=SYSUTCDATETIME(),ReviewNote=?
                           OUTPUT INSERTED.* WHERE ReconId=? AND DatabaseName=? AND Status='PENDING_REVIEW'""",
                        status, reviewer[:128], note[:1000], recon_id, self.business_db)
            cols = [d[0] for d in cur.description] if cur.description else []
            row = cur.fetchone()
            return dict(zip(cols, row)) if row else None
