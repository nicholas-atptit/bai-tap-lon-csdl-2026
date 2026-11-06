"""EOD orchestration.

Status meanings (ops.EodRun.Status):
  SUCCESS     real write committed; full universe received, validated and applied (inserted + unchanged = requested).
              A rerun of the same data is SUCCESS with inserted=0, unchanged=N (idempotent; no new rows claimed).
  DRY_RUN_OK  dry run: everything validated AND applied inside SQL Server, then rolled back. Nothing written.
  NO_SESSION  not a trading session: weekend, or provider reference series has later candles but none on that date.
  SKIPPED     nothing attempted: future date, before cutoff, data not yet available, or another job holds the lock.
  PARTIAL     provider returned an incomplete universe; policy requires all tickers, so NOTHING was written.
  FAILED      provider/config/validation/SQL error or conflicting closed price; full rollback, nothing written.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import traceback
import uuid
from dataclasses import asdict, dataclass, field

from .. import queries
from ..config import Settings
from ..db import DatabaseUnavailable, SqlError, connect, query, query_sets
from .calendar import Decision, classify, default_session_date, now_vn, precheck
from .normalize import Candle, ValidationIssue, normalize_series, parse_trade_date
from .opsstore import OpsStore
from .providers import FetchResult, Provider, ProviderError, build_provider

log = logging.getLogger("marketlab.eod")
EXIT_CODES = {"SUCCESS": 0, "DRY_RUN_OK": 0, "NO_SESSION": 0, "SKIPPED": 10, "PARTIAL": 20, "FAILED": 30}
DRIFT_WINDOW_DAYS = 10
REFERENCE_LOOKBACK_DAYS = 14
REFERENCE_LOOKAHEAD_DAYS = 10


def rows_up_to(raw_rows: list[dict], session: dt.date) -> list[dict]:
    """Drop candles dated after the session (e.g. today's provisional row); unparseable rows are kept so validation rejects them."""
    kept = []
    for r in raw_rows:
        try:
            if parse_trade_date(r.get("time")) > session:
                continue
        except ValidationIssue:
            pass
        kept.append(r)
    return kept


class EodSetupError(RuntimeError):
    """Cannot even record a run (ops DB / config missing). Reported to the caller, exit code 2."""


@dataclass
class RunOutcome:
    eod_run_id: int | None
    run_ref: str | None
    dataset_id: int | None
    session_date: str
    status: str
    error_code: str | None = None
    message: str = ""
    dry_run: bool = False
    requested: int = 0
    received: int = 0
    inserted: int = 0
    unchanged: int = 0
    rejected: int = 0
    would_insert: int | None = None
    provider_last_candle_date: str | None = None
    observed_through_before: str | None = None
    observed_through_after: str | None = None
    reconciliation_added: int = 0
    evaluation: list = field(default_factory=list)
    provider_is_real: bool | None = None

    @property
    def exit_code(self) -> int:
        return EXIT_CODES.get(self.status, 30)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["exit_code"] = self.exit_code
        return d


class CachingProvider:
    """Serves sub-windows of a wider prefetched window (backfill) to avoid repeated vendor calls."""

    def __init__(self, inner: Provider):
        self.inner = inner
        self.source_code = inner.source_code
        self.is_real = inner.is_real
        self._windows: dict[str, tuple[dt.date, dt.date, list[dict], str | None]] = {}
        self.meta: dict = {}

    def prefetch(self, symbols: list[str], start: dt.date, end: dt.date) -> None:
        res = self.inner.fetch(symbols, start, end)
        self.meta = res.meta
        for s in symbols:
            self._windows[s] = (start, end, res.rows.get(s, []), res.errors.get(s))

    def fetch(self, symbols: list[str], start: dt.date, end: dt.date) -> FetchResult:
        if all(s in self._windows and self._windows[s][0] <= start and self._windows[s][1] >= end for s in symbols):
            rows, errors = {}, {}
            for s in symbols:
                _, _, raw, err = self._windows[s]
                if err:
                    errors[s] = err
                kept = []
                for r in raw:
                    try:
                        d = parse_trade_date(r.get("time"))
                    except ValidationIssue:
                        kept.append(r)       # keep: validation will reject it explicitly
                        continue
                    if start <= d <= end:
                        kept.append(r)
                rows[s] = kept
            return FetchResult(rows, errors, {**self.meta, "served_from_prefetch": True,
                                              "window": [start.isoformat(), end.isoformat()]})
        res = self.inner.fetch(symbols, start, end)
        self.meta = res.meta
        return res


class EodService:
    def __init__(self, settings: Settings, provider: Provider | None = None, trigger: str = "CLI",
                 clock: dt.datetime | None = None, ops: OpsStore | None = None):
        self.settings = settings
        self.trigger = trigger
        self.clock = clock
        self.ops = ops or OpsStore(settings)
        self._provider = provider
        self._provider_error: ProviderError | None = None

    # ------------------------------------------------------------------------------------------------
    def provider(self) -> Provider:
        if self._provider is None:
            if self.settings.is_demo:
                raise ProviderError("MODE_DEMO_OFFLINE", "EOD sync is disabled in DEMO_OFFLINE (synthetic database)")
            self._provider = CachingProvider(build_provider(self.settings))
        return self._provider

    def resolve_config(self, dataset_id: int | None) -> dict:
        ok, why = self.ops.available()
        if not ok:
            raise EodSetupError(why)
        cfgs = self.ops.config(dataset_id)
        if not cfgs:
            raise EodSetupError(f"no enabled ops.EodConfig for database {self.settings.sql_database}"
                                + (f" dataset {dataset_id}" if dataset_id else "") + " (python -m marketlab_app.deploy live-db ...)")
        if len(cfgs) > 1:
            raise EodSetupError("several EOD datasets configured; pass --dataset-id explicitly")
        return cfgs[0]

    def already_succeeded(self, dataset_id: int, session: dt.date) -> int | None:
        with connect(self.settings, self.ops.db) as c:
            r = query(c, "SELECT TOP 1 EodRunId FROM ops.EodRun WHERE DatabaseName=? AND DatasetId=? AND SessionDate=? AND Status='SUCCESS' ORDER BY EodRunId DESC",
                      (self.settings.sql_database, dataset_id, session))
        return r[0]["EodRunId"] if r else None

    # ------------------------------------------------------------------------------------------------
    def sync_session(self, session: dt.date | None = None, dataset_id: int | None = None, dry_run: bool = False,
                     batch_ref: str | None = None) -> RunOutcome:
        cfg = self.resolve_config(dataset_id)
        dataset_id = cfg["DatasetId"]
        session = session or default_session_date(self.clock)
        run_id, ref = self.ops.start_run(dataset_id, session, cfg["SourceCode"], self.trigger, dry_run, batch_ref)
        out = RunOutcome(run_id, ref, dataset_id, session.isoformat(), "RUNNING", dry_run=dry_run)
        meta: dict = {"trigger": self.trigger, "now_vn": now_vn(self.clock).isoformat(timespec="seconds"),
                      "cutoff": str(cfg["CutoffLocalTime"])[:5], "universe_index": cfg["IndexCode"],
                      "universe_as_of": cfg["UniverseAsOf"]}
        log.info("EOD run %s start dataset=%s session=%s dry_run=%s trigger=%s", run_id, dataset_id, session, dry_run, self.trigger)
        try:
            self._run(cfg, session, out, meta)
        except Exception as exc:  # noqa: BLE001 - every failure must be recorded, never swallowed silently
            log.error("EOD run %s internal error: %s", run_id, traceback.format_exc())
            if isinstance(exc, (DatabaseUnavailable,)):
                out.status, out.error_code, out.message = "FAILED", "DB_UNAVAILABLE", str(exc)
            elif isinstance(exc, SqlError):
                out.status, out.error_code, out.message = "FAILED", f"SQL_{exc.number}", exc.message
            else:
                out.status, out.error_code, out.message = "FAILED", "INTERNAL_ERROR", f"{type(exc).__name__}: {str(exc)[:300]}"
            out.inserted = 0
        if out.status == "RUNNING":  # defensive: never leave a non-terminal state
            out.status, out.error_code = "FAILED", "INTERNAL_NO_DECISION"
        try:
            self.ops.finish_run(run_id, out.status, requested=out.requested, received=out.received, inserted=out.inserted,
                                unchanged=out.unchanged, rejected=out.rejected, would_insert=out.would_insert,
                                error_code=out.error_code, message=out.message, provider_last=out.provider_last_candle_date,
                                observed_before=out.observed_through_before, observed_after=out.observed_through_after,
                                provider_meta=meta)
        except Exception:  # noqa: BLE001
            log.critical("EOD run %s: could not record terminal status %s: %s", run_id, out.status, traceback.format_exc())
            raise
        log.info("EOD run %s end status=%s code=%s inserted=%s unchanged=%s requested=%s msg=%s", run_id, out.status,
                 out.error_code, out.inserted, out.unchanged, out.requested, out.message[:300])
        return out

    def _finish(self, out: RunOutcome, status: str, code: str | None, message: str) -> None:
        out.status, out.error_code, out.message = status, code, message

    def _run(self, cfg: dict, session: dt.date, out: RunOutcome, meta: dict) -> None:
        dataset_id = cfg["DatasetId"]
        with connect(self.settings) as c:
            ds = queries.dataset_exists(c, dataset_id)
            status = queries.schema_status(c)
            if ds is None or ds["DataKind"] != "REAL_PRIVATE":
                return self._finish(out, "FAILED", "DATASET_NOT_REAL_PRIVATE", "EOD writes only into REAL_PRIVATE datasets")
            if not status["eod_extension"]:
                return self._finish(out, "FAILED", "EOD_EXTENSION_MISSING",
                                    "sql/13_eod_extension.sql not applied to this database (backup + approval required)")
            out.observed_through_before = ds["ObservedThrough"]
            uni = queries.universe(c, dataset_id, cfg["IndexCode"], dt.date.fromisoformat(str(cfg["UniverseAsOf"])))
            day_exists = bool(query(c, "SELECT 1 AS x FROM dbo.TradingDay WHERE DatasetId=? AND TradeDate=?", (dataset_id, session)))
        out.requested = len(uni)
        meta["universe_size"] = len(uni)

        pre = precheck(session, self.clock, str(cfg["CutoffLocalTime"])[:5])
        if pre:
            return self._finish(out, pre.kind, pre.code, pre.message)
        if not uni:
            return self._finish(out, "FAILED", "UNIVERSE_EMPTY", f"no {cfg['IndexCode']} members valid at {cfg['UniverseAsOf']} in this dataset")

        try:
            provider = self.provider()
        except ProviderError as exc:
            return self._finish(out, "FAILED", exc.code, exc.message)
        out.provider_is_real = provider.is_real
        meta["provider_is_real"] = provider.is_real

        today = now_vn(self.clock).date()
        ref_symbol = cfg["CalendarReferenceSymbol"]
        try:
            ref = provider.fetch([ref_symbol], session - dt.timedelta(days=REFERENCE_LOOKBACK_DAYS),
                                 min(session + dt.timedelta(days=REFERENCE_LOOKAHEAD_DAYS), today))
        except ProviderError as exc:
            return self._finish(out, "FAILED", exc.code, exc.message)
        if ref.errors.get(ref_symbol):
            return self._finish(out, "FAILED", "PROVIDER_ERROR", f"reference {ref_symbol}: {ref.errors[ref_symbol][:300]}")
        ref_dates = set()
        for r in ref.rows.get(ref_symbol, []):
            try:
                ref_dates.add(parse_trade_date(r.get("time")))
            except ValidationIssue as exc:
                return self._finish(out, "FAILED", "PROVIDER_BAD_TIME", f"reference {ref_symbol}: {exc.detail}")
        meta["provider"] = ref.meta
        decision: Decision = classify(session, ref_dates, ref_symbol)
        meta["calendar"] = {"decision": decision.code, **decision.evidence}
        if ref_dates:
            out.provider_last_candle_date = max(ref_dates).isoformat()
        if decision.kind != "SESSION":
            if decision.kind == "NO_SESSION" and day_exists:
                return self._finish(out, "FAILED", "CALENDAR_MISMATCH",
                                    f"{session} is in dbo.TradingDay but provider shows no session; manual review needed")
            return self._finish(out, decision.kind, decision.code, decision.message)

        tickers = [u["Ticker"] for u in uni]
        stock_ids = {u["Ticker"]: u["StockId"] for u in uni}
        try:
            # KBS treats `end` as exclusive once the Vietnam calendar day has moved past it (observed 2026-11-06 00:24):
            # ask one day beyond the session (never beyond today) and drop later candles below.
            res = provider.fetch(tickers, session - dt.timedelta(days=DRIFT_WINDOW_DAYS), min(session + dt.timedelta(days=1), today))
        except ProviderError as exc:
            return self._finish(out, "FAILED", exc.code, exc.message)

        candles: dict[str, Candle] = {}
        history: dict[str, dict[dt.date, Candle]] = {}
        items: list[dict] = []
        notes: list[str] = []
        rejected, missing = [], []
        for t in tickers:
            if res.errors.get(t):
                missing.append(t)
                items.append({"ticker": t, "stock_id": stock_ids[t], "outcome": "MISSING", "detail": f"provider error: {res.errors[t][:300]}"})
                continue
            try:
                series, n = normalize_series(t, rows_up_to(res.rows.get(t, []), session))
                notes += n
            except ValidationIssue as exc:
                rejected.append(t)
                items.append({"ticker": t, "stock_id": stock_ids[t], "outcome": "REJECTED", "detail": f"{exc.code}: {exc.detail}"[:400]})
                continue
            history[t] = series
            if session not in series:
                missing.append(t)
                items.append({"ticker": t, "stock_id": stock_ids[t], "outcome": "MISSING",
                              "detail": f"no candle on {session}; provider last candle {max(series).isoformat() if series else 'none'}"})
                continue
            candles[t] = series[session]
        all_dates = [d for s in history.values() for d in s] + list(ref_dates)
        if all_dates:
            out.provider_last_candle_date = max(all_dates).isoformat()
        out.received = len(candles)
        out.rejected = len(rejected)
        if notes:
            meta["normalization_notes"] = notes[:20]

        def not_written(detail: str):
            for t in candles:
                items.append({"ticker": t, "stock_id": stock_ids[t], "outcome": "NOT_WRITTEN", "detail": detail})

        if rejected:
            not_written("batch rejected: another ticker failed validation")
            self.ops.add_items(out.eod_run_id, items)
            return self._finish(out, "FAILED", "VALIDATION_FAILED",
                                f"{len(rejected)} ticker(s) failed validation ({', '.join(rejected[:10])}); nothing written")
        if missing:
            not_written("batch not written: universe incomplete")
            self.ops.add_items(out.eod_run_id, items)
            return self._finish(out, "PARTIAL", "MISSING_TICKERS",
                                f"{len(missing)}/{len(tickers)} ticker(s) without a valid candle on {session} ({', '.join(missing[:10])}); "
                                "complete universe required, nothing written")

        payload = json.dumps([candles[t].as_payload(stock_ids[t]) for t in tickers])
        expected = json.dumps(sorted(stock_ids.values()))
        try:
            with connect(self.settings) as c:
                sets = query_sets(c, "EXEC ops.usp_EodApplySession @DatasetId=?, @SessionDate=?, @EodRunRef=?, @PricesJson=?, @ExpectedStockIdsJson=?, @DryRun=?",
                                  (dataset_id, session, out.run_ref, payload, expected, 1 if out.dry_run else 0), self.settings)
        except SqlError as exc:
            if exc.number == 51144:
                return self._finish(out, "SKIPPED", "LOCK_BUSY", exc.message)
            if exc.number == 51145:
                conflicts = self._conflicts(dataset_id, session, candles, stock_ids)
                out.reconciliation_added = self.ops.add_reconciliation(out.eod_run_id, dataset_id, conflicts, "SESSION_CONFLICT")
                for cf in conflicts:
                    items.append({"ticker": cf["ticker"], "stock_id": cf["stock_id"], "outcome": "CONFLICT",
                                  "detail": f"stored close {cf['stored'][3]} vs provider {cf['provider'][3]}; pending review"})
                done = {i["ticker"] for i in items}
                for t in candles:
                    if t not in done:
                        items.append({"ticker": t, "stock_id": stock_ids[t], "outcome": "NOT_WRITTEN", "detail": "batch rolled back"})
                self.ops.add_items(out.eod_run_id, items)
                return self._finish(out, "FAILED", "CONFLICT_REQUIRES_RECONCILIATION",
                                    f"{len(conflicts)} stored closed price(s) differ from provider; full rollback; "
                                    f"{out.reconciliation_added} reconciliation item(s) pending human review")
            not_written(f"rolled back: SQL {exc.number}")
            self.ops.add_items(out.eod_run_id, items)
            return self._finish(out, "FAILED", f"SQL_{exc.number}", exc.message)

        outcomes, summary = sets[0], sets[1][0]
        for o in outcomes:
            items.append({"ticker": o["Ticker"], "stock_id": o["StockId"], "outcome": o["Outcome"], "detail": None})
        self.ops.add_items(out.eod_run_id, items)
        out.inserted, out.unchanged = summary["InsertedCount"], summary["UnchangedCount"]
        out.observed_through_after = summary["ObservedThroughAfter"]
        if out.dry_run:
            out.would_insert = summary["WouldInsertCount"]
            meta["observed_through_would_be"] = summary["ObservedThroughWouldBe"]
            return self._finish(out, "DRY_RUN_OK", None,
                                f"dry run validated in SQL Server and rolled back: would insert {out.would_insert}, unchanged {out.unchanged}")
        inserted_keys = [(o["StockId"], session) for o in outcomes if o["Outcome"] == "INSERTED"]
        self.ops.add_lineage(out.eod_run_id, dataset_id, cfg["SourceCode"], inserted_keys)
        drift = self._drift(dataset_id, session, history, stock_ids)
        if drift:
            out.reconciliation_added = self.ops.add_reconciliation(out.eod_run_id, dataset_id, drift, "HISTORY_DRIFT_PROBE")
        with connect(self.settings) as c:
            out.evaluation = queries.performance(c, session, dataset_id)
        self.ops.add_eval_snapshot(out.eod_run_id, out.evaluation)
        msg = (f"committed {session}: inserted {out.inserted}, unchanged {out.unchanged} of {out.requested}"
               + (" (idempotent rerun: no new rows)" if out.inserted == 0 else ""))
        if drift:
            msg += f"; WARNING provider changed {len(drift)} earlier stored price(s) (basis drift) -> {out.reconciliation_added} new review item(s)"
        if not out.evaluation:
            msg += "; no model runs in dataset (no inference configured)"
        return self._finish(out, "SUCCESS", None, msg)

    def _stored(self, dataset_id: int, dates: list[dt.date], stock_ids: list[int]) -> dict:
        if not dates or not stock_ids:
            return {}
        with connect(self.settings) as c:
            rows = query(c, f"""SELECT StockId, TradeDate, OpenPrice, HighPrice, LowPrice, ClosePrice, Volume FROM dbo.DailyPrice
                                WHERE DatasetId=? AND TradeDate BETWEEN ? AND ? AND StockId IN ({','.join('?' for _ in stock_ids)})""",
                         [dataset_id, min(dates), max(dates)] + stock_ids)
        return {(r["StockId"], r["TradeDate"]): r for r in rows}

    @staticmethod
    def _diff(stored: dict, candle: Candle) -> bool:
        from decimal import Decimal
        s = (Decimal(str(stored["OpenPrice"])), Decimal(str(stored["HighPrice"])), Decimal(str(stored["LowPrice"])),
             Decimal(str(stored["ClosePrice"])), int(stored["Volume"]))
        return s != candle.values()

    def _recon_row(self, t: str, sid: int, d: dt.date, stored: dict, candle: Candle) -> dict:
        return {"ticker": t, "stock_id": sid, "trade_date": d,
                "stored": (stored["OpenPrice"], stored["HighPrice"], stored["LowPrice"], stored["ClosePrice"], stored["Volume"]),
                "provider": (candle.open, candle.high, candle.low, candle.close, candle.volume)}

    def _conflicts(self, dataset_id: int, session: dt.date, candles: dict[str, Candle], stock_ids: dict) -> list[dict]:
        stored = self._stored(dataset_id, [session], list(stock_ids.values()))
        out = []
        for t, cd in candles.items():
            s = stored.get((stock_ids[t], session.isoformat()))
            if s and self._diff(s, cd):
                out.append(self._recon_row(t, stock_ids[t], session, s, cd))
        return out

    def _drift(self, dataset_id: int, session: dt.date, history: dict[str, dict[dt.date, Candle]], stock_ids: dict) -> list[dict]:
        dates = sorted({d for s in history.values() for d in s if d < session})
        stored = self._stored(dataset_id, dates, list(stock_ids.values()))
        out = []
        for t, series in history.items():
            for d, cd in series.items():
                if d >= session:
                    continue
                s = stored.get((stock_ids[t], d.isoformat()))
                if s and self._diff(s, cd):
                    out.append(self._recon_row(t, stock_ids[t], d, s, cd))
        return out

    # ------------------------------------------------------------------------------------------------
    def backfill(self, date_from: dt.date, date_to: dt.date, dataset_id: int | None = None, dry_run: bool = False,
                 max_sessions: int | None = None, stop_on_error: bool = True) -> dict:
        if date_from > date_to:
            raise ValueError("--from must be <= --to")
        cfg = self.resolve_config(dataset_id)
        limit = max_sessions or self.settings.max_backfill_sessions
        weekdays = [date_from + dt.timedelta(days=i) for i in range((date_to - date_from).days + 1)]
        weekdays = [d for d in weekdays if d.weekday() < 5]
        if len(weekdays) > limit:
            raise ValueError(f"{len(weekdays)} weekday(s) requested > limit {limit} (--max-sessions)")
        batch = str(uuid.uuid4())
        today = now_vn(self.clock).date()
        try:
            prov = self.provider()
            if isinstance(prov, CachingProvider):
                with connect(self.settings) as c:
                    uni = queries.universe(c, cfg["DatasetId"], cfg["IndexCode"], dt.date.fromisoformat(str(cfg["UniverseAsOf"])))
                prov.prefetch([cfg["CalendarReferenceSymbol"]], date_from - dt.timedelta(days=REFERENCE_LOOKBACK_DAYS),
                              min(date_to + dt.timedelta(days=REFERENCE_LOOKAHEAD_DAYS), today))
                prov.prefetch([u["Ticker"] for u in uni], date_from - dt.timedelta(days=DRIFT_WINDOW_DAYS), min(date_to + dt.timedelta(days=1), today))
        except ProviderError as exc:
            log.warning("prefetch failed (%s); each session will record the provider error", exc.code)
        results = []
        for d in weekdays:
            r = self.sync_session(d, cfg["DatasetId"], dry_run, batch)
            results.append(r.to_dict())
            if stop_on_error and r.status in ("FAILED", "PARTIAL", "SKIPPED"):
                break
        summary: dict = {}
        for r in results:
            summary[r["status"]] = summary.get(r["status"], 0) + 1
        worst = max((r["exit_code"] for r in results), default=0)
        return {"batch_ref": batch, "dataset_id": cfg["DatasetId"], "from": date_from.isoformat(), "to": date_to.isoformat(),
                "dry_run": dry_run, "weekdays_requested": len(weekdays), "processed": len(results),
                "stopped_early": len(results) < len(weekdays), "status_counts": summary, "exit_code": worst,
                "inserted_total": sum(r["inserted"] for r in results), "runs": results}
