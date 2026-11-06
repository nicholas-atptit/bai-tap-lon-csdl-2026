"""Integration: EOD pipeline against an isolated REAL_PRIVATE test database with the FakeProvider (test-only adapter).
Scenarios run in file order and share state; every test checks DB row counts before/after."""
import datetime as dt
from decimal import Decimal

import pyodbc
import pytest

from conftest import CLOCK, TICKERS, counts, fake_candle, fake_series
from marketlab_app import queries
from marketlab_app.db import SqlError, connect, query
from marketlab_app.eod.opsstore import OpsStore
from marketlab_app.eod.providers import FakeProvider, ProviderError
from marketlab_app.eod.service import EodService

pytestmark = pytest.mark.integration
D1, D2 = dt.date(2026, 10, 2), dt.date(2026, 10, 5)


def svc(env, provider, clock=CLOCK):
    return EodService(env["settings"], provider=provider, trigger="TEST", clock=clock)


def run_row(env, run_id):
    with connect(env["settings"], env["ops_db"]) as c:
        return query(c, "SELECT * FROM ops.EodRun WHERE EodRunId=?", (run_id,))[0]


def test_extension_keeps_13_tables_and_guard(it_env):
    s = it_env["settings"]
    with connect(s) as c:
        st = queries.schema_status(c)
        assert st["user_tables"] == 13 and st["eod_extension"] and not st["missing"]
        cur = c.cursor()
        with pytest.raises(pyodbc.Error, match="51007"):   # no session context -> original rule
            cur.execute("UPDATE dbo.Dataset SET ObservedThrough='2026-10-03' WHERE DatasetId=1")
        with pytest.raises(pyodbc.Error, match="51007"):   # decrease refused even with context
            cur.execute("EXEC sys.sp_set_session_context N'MarketLab.EodRunRef','t'; UPDATE dbo.Dataset SET ObservedThrough='2026-09-01' WHERE DatasetId=1")
        cur.execute("EXEC sys.sp_set_session_context N'MarketLab.EodRunRef',NULL")
        with pytest.raises(pyodbc.Error, match="51007"):   # unit change refused even with context
            cur.execute("BEGIN TRAN; EXEC sys.sp_set_session_context N'MarketLab.EodRunRef','t'; UPDATE dbo.Dataset SET PriceUnit=N'x', ObservedThrough='2026-10-03' WHERE DatasetId=1")
        cur.execute("IF @@TRANCOUNT>0 ROLLBACK; EXEC sys.sp_set_session_context N'MarketLab.EodRunRef',NULL")
        assert query(c, "SELECT ObservedThrough FROM dbo.Dataset")[0]["ObservedThrough"] == "2026-10-01"


def test_weekend_future_and_cutoff_record_runs_without_writes(it_env):
    before = counts(it_env["settings"], it_env["db"])
    p = FakeProvider(fake_series())
    r = svc(it_env, p).sync_session(dt.date(2026, 10, 3))
    assert (r.status, r.error_code, r.exit_code) == ("NO_SESSION", "WEEKEND", 0)
    r = svc(it_env, p).sync_session(dt.date(2026, 11, 6))
    assert (r.status, r.error_code, r.exit_code) == ("SKIPPED", "FUTURE_DATE", 10)
    r = svc(it_env, p, clock=dt.datetime(2026, 11, 5, 9, 0, tzinfo=CLOCK.tzinfo)).sync_session(dt.date(2026, 11, 5))
    assert (r.status, r.error_code) == ("SKIPPED", "BEFORE_CUTOFF")
    assert p.calls == []  # nothing fetched for pre-checked dates
    assert counts(it_env["settings"], it_env["db"]) == before
    assert run_row(it_env, r.eod_run_id)["Status"] == "SKIPPED"


def test_provider_holiday_and_not_yet_available(it_env):
    before = counts(it_env["settings"], it_env["db"])
    hol = dt.date(2026, 10, 14)
    r = svc(it_env, FakeProvider(fake_series(holidays={hol}))).sync_session(hol)
    assert (r.status, r.error_code) == ("NO_SESSION", "PROVIDER_CALENDAR_GAP")
    r = svc(it_env, FakeProvider(fake_series(end=dt.date(2026, 11, 3)))).sync_session(dt.date(2026, 11, 4))
    assert (r.status, r.error_code, r.exit_code) == ("SKIPPED", "DATA_NOT_YET_AVAILABLE", 10)
    assert counts(it_env["settings"], it_env["db"]) == before


def test_calendar_mismatch_is_failed(it_env):
    # D1 is pre-registered in dbo.TradingDay; a provider claiming no session must not be silently accepted
    r = svc(it_env, FakeProvider(fake_series(holidays={D1}))).sync_session(D1)
    assert (r.status, r.error_code, r.exit_code) == ("FAILED", "CALENDAR_MISMATCH", 30)


def test_provider_errors_fail_cleanly(it_env):
    before = counts(it_env["settings"], it_env["db"])
    r = svc(it_env, FakeProvider(raise_error=ProviderError("PROVIDER_TIMEOUT", "bridge exceeded 180s"))).sync_session(D1)
    assert (r.status, r.error_code) == ("FAILED", "PROVIDER_TIMEOUT")
    r = svc(it_env, FakeProvider(fake_series(), fail_symbols={"VN30": "HTTPError 503"})).sync_session(D1)
    assert (r.status, r.error_code) == ("FAILED", "PROVIDER_ERROR")
    assert counts(it_env["settings"], it_env["db"]) == before


def test_missing_ticker_is_partial_and_writes_nothing(it_env):
    before = counts(it_env["settings"], it_env["db"])
    data = fake_series()
    data["TST03"] = [r for r in data["TST03"] if not r["time"].startswith(D1.isoformat())]
    r = svc(it_env, FakeProvider(data, fail_symbols={"TST04": "ConnectionError"})).sync_session(D1)
    assert (r.status, r.error_code, r.exit_code) == ("PARTIAL", "MISSING_TICKERS", 20)
    assert (r.requested, r.received, r.inserted) == (5, 3, 0)
    assert counts(it_env["settings"], it_env["db"]) == before
    detail = OpsStore(it_env["settings"]).run_detail(r.eod_run_id)
    assert {i["Ticker"]: i["Outcome"] for i in detail["items"]} == {
        "TST01": "NOT_WRITTEN", "TST02": "NOT_WRITTEN", "TST03": "MISSING", "TST04": "MISSING", "TST05": "NOT_WRITTEN"}


@pytest.mark.parametrize("patch,code", [({"high": "1"}, "OHLC_RANGE"), ({"volume": "-3"}, "BAD_VOLUME"), ({"close": "NaN"}, "NOT_FINITE")])
def test_invalid_candle_fails_whole_batch(it_env, patch, code):
    before = counts(it_env["settings"], it_env["db"])
    data = fake_series()
    data["TST02"] = [({**r, **patch} if r["time"].startswith(D1.isoformat()) else r) for r in data["TST02"]]
    r = svc(it_env, FakeProvider(data)).sync_session(D1)
    assert (r.status, r.error_code, r.rejected, r.inserted) == ("FAILED", "VALIDATION_FAILED", 1, 0)
    assert code in str(OpsStore(it_env["settings"]).run_detail(r.eod_run_id)["items"])
    assert counts(it_env["settings"], it_env["db"]) == before


def test_conflicting_source_duplicate_fails(it_env):
    data = fake_series()
    data["TST01"].append({**fake_candle("TST01", D1), "close": "999"})
    r = svc(it_env, FakeProvider(data)).sync_session(D1)
    assert (r.status, r.error_code) == ("FAILED", "VALIDATION_FAILED")


def test_dry_run_validates_in_sql_then_rolls_back(it_env):
    before = counts(it_env["settings"], it_env["db"])
    r = svc(it_env, FakeProvider(fake_series())).sync_session(D1, dry_run=True)
    assert (r.status, r.would_insert, r.inserted, r.exit_code) == ("DRY_RUN_OK", 5, 0, 0)
    assert counts(it_env["settings"], it_env["db"]) == before


def test_sql_all_or_nothing_when_a_row_breaks_mid_batch(it_env):
    """Bypass Python validation: the 4th row violates OHLC inside usp_InsertDailyPrice -> whole session rolled back."""
    s = it_env["settings"]
    before = counts(s, it_env["db"])
    rows = [fake_candle(t, D1) for t in TICKERS]
    payload = [{"StockId": i + 1, "Open": r["open"], "High": r["high"], "Low": r["low"], "Close": r["close"], "Volume": r["volume"]}
               for i, r in enumerate(rows)]
    payload[3]["High"] = "0.01"
    import json
    with connect(s) as c, pytest.raises(pyodbc.Error, match="51010"):
        c.cursor().execute("EXEC ops.usp_EodApplySession 1, ?, 'manual-test', ?, ?, 0", D1, json.dumps(payload), json.dumps([1, 2, 3, 4, 5]))
    assert counts(s, it_env["db"]) == before
    with connect(s) as c, pytest.raises(pyodbc.Error, match="51142"):   # incomplete universe refused by SQL as well
        c.cursor().execute("EXEC ops.usp_EodApplySession 1, ?, 'manual-test', ?, ?, 0", D1, json.dumps(payload[:4]), json.dumps([1, 2, 3, 4, 5]))
    assert counts(s, it_env["db"]) == before


def test_lock_busy_is_skipped(it_env):
    s = it_env["settings"]
    with connect(s, autocommit=False) as holder:
        holder.cursor().execute(f"EXEC sys.sp_getapplock @Resource=N'MarketLab.EOD.{it_env['db']}.1', @LockMode='Exclusive', @LockOwner='Transaction'")
        r = svc(it_env, FakeProvider(fake_series())).sync_session(D1)
        holder.rollback()
    assert (r.status, r.error_code, r.inserted) == ("SKIPPED", "LOCK_BUSY", 0)


def test_success_then_idempotent_rerun(it_env):
    s = it_env["settings"]
    before = counts(s, it_env["db"])
    r = svc(it_env, FakeProvider(fake_series())).sync_session(D1)
    assert (r.status, r.inserted, r.unchanged, r.exit_code) == ("SUCCESS", 5, 0, 0)
    after = counts(s, it_env["db"])
    assert after["prices"] == before["prices"] + 5 and after["days"] == before["days"]  # D1 was pre-registered
    assert (r.observed_through_before, r.observed_through_after, after["observed"]) == ("2026-10-01", "2026-10-02", "2026-10-02")
    with connect(s) as c:
        stored = query(c, "SELECT ClosePrice FROM dbo.DailyPrice WHERE DatasetId=1 AND StockId=1 AND TradeDate=?", (D1,))[0]["ClosePrice"]
    assert Decimal(str(stored)) == Decimal(fake_candle("TST01", D1)["close"])
    with connect(s, it_env["ops_db"]) as c:
        assert query(c, "SELECT COUNT(*) AS n FROM ops.PriceLoadLineage WHERE EodRunId=?", (r.eod_run_id,))[0]["n"] == 5
    # horizon-1 run 3 matured on D1: 4 eligible (TST05 lacks the origin price)
    ev = {e["RunId"]: e for e in r.evaluation}
    assert ev[3]["EvaluatedRows"] == 4 and ev[1]["EvaluatedRows"] == 0 and ev[1]["PendingNotMatured"] == 5
    again = svc(it_env, FakeProvider(fake_series())).sync_session(D1)
    assert (again.status, again.inserted, again.unchanged) == ("SUCCESS", 0, 5)
    assert "idempotent" in again.message
    assert counts(s, it_env["db"]) == after


def test_changed_closed_price_requires_reconciliation(it_env):
    s = it_env["settings"]
    before = counts(s, it_env["db"])
    data = fake_series()
    data["TST02"] = [({**r, "close": str(Decimal(r["close"]) + Decimal("0.01"))} if r["time"].startswith(D1.isoformat()) else r) for r in data["TST02"]]
    r = svc(it_env, FakeProvider(data)).sync_session(D1)
    assert (r.status, r.error_code, r.reconciliation_added) == ("FAILED", "CONFLICT_REQUIRES_RECONCILIATION", 1)
    assert counts(s, it_env["db"]) == before
    rec = OpsStore(s).reconciliation(1, "PENDING_REVIEW", 10)
    assert len(rec) == 1 and rec[0]["Ticker"] == "TST02" and rec[0]["DetectedBy"] == "SESSION_CONFLICT"


def test_next_session_matures_forecasts_and_drift_probe(it_env):
    s = it_env["settings"]
    data = fake_series()
    # provider retroactively changes TST04 on D1 (already stored) while delivering D2 normally
    data["TST04"] = [({**r, "close": str(Decimal(r["close"]) - Decimal("0.02"))} if r["time"].startswith(D1.isoformat()) else r) for r in data["TST04"]]
    r = svc(it_env, FakeProvider(data)).sync_session(D2)
    assert (r.status, r.inserted) == ("SUCCESS", 5)
    assert "basis drift" in r.message and r.reconciliation_added == 1
    ev = {e["RunId"]: e for e in r.evaluation}
    assert ev[1]["EvaluatedRows"] == 4 and ev[2]["EvaluatedRows"] == 4 and ev[1]["MissingEndpoint"] == 1
    with connect(s) as c:   # API/SQL agreement: same numbers as the view-equivalent and the procedure
        proc = query(c, "EXEC dbo.usp_GetModelPerformance 'it_model_a',1,2,'2026-10-01','2026-10-01',?", (D2,))
        assert proc[0]["EvaluatedRows"] == 4 and abs(proc[0]["Accuracy"] - ev[1]["Accuracy"]) < 1e-9
        assert abs(proc[0]["BrierScore"] - ev[1]["BrierScore"]) < 1e-12
        # as_of before TargetDate -> nothing eligible yet
        assert queries.performance(c, D1, 1, 1)[0]["EvaluatedRows"] == 0


def test_compare_runs_on_common_set_and_incompatible(it_env):
    s = it_env["settings"]
    with connect(s) as c:
        res = queries.compare_runs(c, [1, 2], dt.date(2026, 10, 1), dt.date(2026, 10, 1), D2)
        assert [r["CommonObservations"] for r in res["rows"]] == [4, 4]
        assert all(r["IntersectionRowsCheck"] == r["CommonObservations"] for r in res["rows"])
        with pytest.raises(SqlError) as e:
            queries.compare_runs(c, [1, 3], dt.date(2026, 10, 1), dt.date(2026, 10, 1), D2)
        assert e.value.number == 51020
        with pytest.raises(SqlError) as e:
            queries.compare_runs(c, [1, 2], dt.date(2026, 10, 1), dt.date(2026, 10, 1), D1)
        assert e.value.number == 51021


def test_backfill_dry_run_limits_and_real(it_env):
    s = it_env["settings"]
    before = counts(s, it_env["db"])
    with pytest.raises(ValueError):
        svc(it_env, FakeProvider(fake_series())).backfill(dt.date(2026, 10, 6), dt.date(2026, 10, 30), max_sessions=5)
    res = svc(it_env, FakeProvider(fake_series(holidays={dt.date(2026, 10, 8)}))).backfill(dt.date(2026, 10, 6), dt.date(2026, 10, 9), dry_run=True)
    assert res["status_counts"] == {"DRY_RUN_OK": 3, "NO_SESSION": 1} and counts(s, it_env["db"]) == before
    res = svc(it_env, FakeProvider(fake_series(holidays={dt.date(2026, 10, 8)}))).backfill(dt.date(2026, 10, 6), dt.date(2026, 10, 9))
    assert res["status_counts"] == {"SUCCESS": 3, "NO_SESSION": 1} and res["inserted_total"] == 15
    after = counts(s, it_env["db"])
    assert after["prices"] == before["prices"] + 15 and after["days"] == before["days"] + 3 and after["observed"] == "2026-10-09"


def test_backfill_stops_on_first_failure(it_env):
    data = fake_series()
    data["TST01"] = [r for r in data["TST01"] if not r["time"].startswith("2026-10-13")]
    res = svc(it_env, FakeProvider(data)).backfill(dt.date(2026, 10, 12), dt.date(2026, 10, 16))
    assert [x["status"] for x in res["runs"]] == ["SUCCESS", "PARTIAL"] and res["stopped_early"] and res["exit_code"] == 20


def test_ops_constraints_reject_false_success(it_env):
    s = it_env["settings"]
    with connect(s, it_env["ops_db"]) as c, pytest.raises(pyodbc.Error, match="CK_EodRun_Success"):
        c.cursor().execute("""INSERT ops.EodRun(RunRef,DatabaseName,DatasetId,SessionDate,SourceCode,TriggerKind,IsDryRun,Status,RequestedCount,ReceivedCount,InsertedCount,FinishedAtUtc)
                              VALUES('x-1','db',1,'2026-10-01','KBS_VNSTOCK','TEST',0,'SUCCESS',5,4,4,SYSUTCDATETIME())""")
    with connect(s, it_env["ops_db"]) as c, pytest.raises(pyodbc.Error, match="CK_EodRun_ErrorCode"):
        c.cursor().execute("""INSERT ops.EodRun(RunRef,DatabaseName,DatasetId,SessionDate,SourceCode,TriggerKind,IsDryRun,Status,FinishedAtUtc)
                              VALUES('x-2','db',1,'2026-10-01','KBS_VNSTOCK','TEST',0,'FAILED',SYSUTCDATETIME())""")


def test_demo_mode_refuses_eod(it_env):
    from conftest import it_settings
    demo = it_settings(it_env["db"], it_env["ops_db"], MARKETLAB_MODE="DEMO_OFFLINE")
    r = EodService(demo, trigger="TEST", clock=CLOCK).sync_session(D2)
    assert (r.status, r.error_code) == ("FAILED", "MODE_DEMO_OFFLINE")


def test_last_status_distinguishes_dates(it_env):
    st = OpsStore(it_env["settings"]).last_status(1)
    assert st["last_successful_trade_date"] == "2026-10-12"     # backfill stopped at the PARTIAL 2026-10-13
    assert st["last_requested_date"] == "2026-10-05"            # most recent run: the DEMO_OFFLINE refusal for D2
    assert st["last_run"]["Status"] == "FAILED"
    assert st["last_provider_candle_date"] >= "2026-10-13"
    assert st["pending_reconciliation"] == 2


class ExclusiveEndProvider(FakeProvider):
    """Mimics KBS after the Vietnam calendar day has passed `end`: candles dated `end` are not returned."""

    def fetch(self, symbols, start, end):
        res = super().fetch(symbols, start, end)
        res.rows = {s: [r for r in rows if r["time"][:10] < end.isoformat()] for s, rows in res.rows.items()}
        return res


def test_exclusive_end_provider_and_provisional_next_day_row(it_env):
    """Regression for the false PARTIAL seen on 2026-11-06 00:24 with real KBS data: the session must still be complete,
    and a malformed provisional candle dated after the session must be ignored, not validated."""
    s = it_env["settings"]
    data = fake_series()
    data["TST02"].append({**fake_candle("TST02", dt.date(2026, 10, 14)), "time": "2026-10-14T07:00:00", "high": "1"})
    before = counts(s, it_env["db"])
    r = svc(it_env, ExclusiveEndProvider(data)).sync_session(dt.date(2026, 10, 13))
    assert (r.status, r.inserted, r.received) == ("SUCCESS", 5, 5), r.message
    assert counts(s, it_env["db"])["prices"] == before["prices"] + 5
