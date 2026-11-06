"""Integration: historical backfill against an isolated REAL_PRIVATE test database (FakeProvider, test-only adapter).
Each scenario uses its own date window; every test checks rows in SQL Server before/after."""
import datetime as dt
from decimal import Decimal

import pytest

from conftest import CLOCK, TICKERS, counts, fake_candle, weekdays
from marketlab_app.config import ConfigError, load_settings
from marketlab_app.db import SqlError, connect, query
from marketlab_app.eod import backfill as bf
from marketlab_app.eod.coverage import coverage, table_hash
from marketlab_app.eod.providers import FakeProvider, FetchResult, ProviderError

pytestmark = pytest.mark.integration
REF = "VN30"


def series(start, end, holidays=(), listed=None, gaps=(), bump=None, tickers=TICKERS) -> dict:
    listed, bump = listed or {}, bump or {}
    days = [d for d in weekdays(start, end) if d not in holidays]
    data = {REF: [fake_candle(REF, d) for d in days]}
    for t in tickers:
        data[t] = [fake_candle(t, d, bump.get((t, d), Decimal(0))) for d in days
                   if d >= listed.get(t, start) and (t, d) not in gaps]
    return data


def svc(env, provider, **kw):
    return bf.BackfillService(env["settings"], provider=provider, clock=kw.pop("clock", CLOCK), trigger="TEST",
                              sleep=kw.pop("sleep", lambda s: None), **kw)


def window_rows(env, a, b) -> int:
    with connect(env["settings"]) as c:
        return query(c, "SELECT COUNT(*) AS n FROM dbo.DailyPrice WHERE TradeDate BETWEEN ? AND ?", (a, b))[0]["n"]


def ops(env, sql, params=()):
    with connect(env["settings"], env["ops_db"]) as c:
        return query(c, sql, params)


W1 = (dt.date(2026, 9, 1), dt.date(2026, 9, 30))
HOL = dt.date(2026, 9, 2)
LISTED = {"TST05": dt.date(2026, 9, 15)}
GAP = ("TST03", dt.date(2026, 9, 22))   # after TST05 listing, so it is a separate PARTIAL session


def w1_data(**kw):
    return series(*W1, holidays={HOL}, listed=LISTED, gaps={GAP}, **kw)


def expected_w1():
    days = [d for d in weekdays(*W1) if d != HOL]
    nohist = sum(1 for d in days if d < LISTED["TST05"])
    return len(days), nohist, len(days) * 5 - nohist - 1


def test_history_floor_is_enforced(it_env):
    with pytest.raises(bf.BackfillError) as e:
        svc(it_env, FakeProvider(w1_data())).run(dt.date(2022, 12, 31), "2023-01-06")
    assert e.value.code == "BEFORE_HISTORY_START"
    with pytest.raises(ConfigError):
        load_settings(env={"MARKETLAB_MODE": "REAL_PRIVATE", "MARKETLAB_SQL_DATABASE": "x", "MARKETLAB_HISTORY_START": "2022-06-01"})
    assert not ops(it_env, "SELECT 1 AS x FROM ops.BackfillJob")   # refused before any job row


def test_demo_mode_refused(it_env):
    demo = load_settings(env={"MARKETLAB_MODE": "DEMO_OFFLINE", "MARKETLAB_SQL_DATABASE": it_env["db"], "MARKETLAB_OPS_DATABASE": it_env["ops_db"]})
    with pytest.raises(bf.BackfillError) as e:
        bf.BackfillService(demo, provider=FakeProvider({}), trigger="TEST").run(W1[0], "2026-09-30")
    assert e.value.code == "MODE_DEMO_OFFLINE"


def test_dry_run_reports_expected_counts_and_writes_nothing(it_env):
    before = counts(it_env["settings"], it_env["db"])
    r = svc(it_env, FakeProvider(w1_data())).run(W1[0], W1[1].isoformat(), dry_run=True)
    sessions, nohist, present = expected_w1()
    assert (r["status"], r["exit_code"], r["dry_run"]) == ("DRY_RUN_OK", 0, True)
    assert (r["sessions_planned"], r["rows_would_insert"], r["rows_inserted"]) == (sessions, present, 0)
    assert (r["rows_no_history"], r["rows_missing"]) == (nohist, 1)
    assert counts(it_env["settings"], it_env["db"]) == before
    assert not ops(it_env, "SELECT 1 AS x FROM ops.EodRun WHERE TriggerKind='BACKFILL'")   # dry run: no EodRun rows


def test_real_run_writes_partial_sessions_honestly(it_env):
    s = it_env["settings"]
    before = counts(s, it_env["db"])
    r = svc(it_env, FakeProvider(w1_data())).run(W1[0], W1[1].isoformat())
    sessions, nohist, present = expected_w1()
    assert (r["status"], r["exit_code"], r["rows_inserted"]) == ("COMPLETED_WITH_GAPS", 20, present)
    after = counts(s, it_env["db"])
    assert after["prices"] - before["prices"] == present and after["days"] - before["days"] == sessions
    assert after["observed"] == before["observed"]          # historical sessions never move ObservedThrough
    runs = {x["Status"]: x["n"] for x in ops(it_env, "SELECT Status, COUNT(*) AS n FROM ops.EodRun WHERE BatchRef=? GROUP BY Status", (r["job_ref"],))}
    assert runs == {"SUCCESS": sessions - nohist - 1, "PARTIAL": nohist + 1}
    codes = {x["ErrorCode"] for x in ops(it_env, "SELECT DISTINCT ErrorCode FROM ops.EodRun WHERE BatchRef=? AND Status='PARTIAL'", (r["job_ref"],))}
    assert codes == {"NO_PROVIDER_HISTORY", "MISSING_TICKERS"}
    item = ops(it_env, """SELECT i.Outcome FROM ops.EodRunItem i JOIN ops.EodRun e ON e.EodRunId=i.EodRunId
                          WHERE e.BatchRef=? AND e.SessionDate=? AND i.Ticker=?""", (r["job_ref"], GAP[1], GAP[0]))
    assert item[0]["Outcome"] == "MISSING"
    lineage = ops(it_env, "SELECT COUNT(*) AS n FROM ops.PriceLoadLineage l JOIN ops.EodRun e ON e.EodRunId=l.EodRunId WHERE e.BatchRef=?", (r["job_ref"],))
    assert lineage[0]["n"] == present
    cov = coverage(s, W1[0], W1[1], job_id=r["job_id"])
    t5 = next(x for x in cov["per_ticker"] if x["ticker"] == "TST05")
    t3 = next(x for x in cov["per_ticker"] if x["ticker"] == "TST03")
    assert (t5["no_history_sessions"], t5["missing_sessions"], t3["missing_sessions"]) == (nohist, 0, 1)
    assert cov["coverage_status"] == "PARTIAL_COVERAGE" and cov["totals"]["rows_before_floor"] == 0


def test_rerun_same_window_is_idempotent(it_env):
    s = it_env["settings"]
    h1 = table_hash(s, 1, *W1)
    before = counts(s, it_env["db"])
    r = svc(it_env, FakeProvider(w1_data())).run(W1[0], W1[1].isoformat())
    assert (r["rows_inserted"], r["rows_unchanged"], r["conflicts"]) == (0, expected_w1()[2], 0)
    assert counts(s, it_env["db"]) == before
    assert table_hash(s, 1, *W1) == h1                     # values and LoadedAt untouched


def test_revision_conflict_is_queued_never_overwritten(it_env):
    s = it_env["settings"]
    d = dt.date(2026, 9, 16)   # all five tickers listed: 4 unchanged + 1 conflict
    with connect(s) as c:
        stored = query(c, "SELECT ClosePrice FROM dbo.DailyPrice WHERE StockId=1 AND TradeDate=?", (d,))[0]["ClosePrice"]
    before = counts(s, it_env["db"])
    r = svc(it_env, FakeProvider(w1_data(bump={("TST01", d): Decimal("0.7")}))).run(W1[0], W1[1].isoformat())
    assert (r["rows_inserted"], r["conflicts"], r["status"]) == (0, 1, "COMPLETED_WITH_GAPS")
    with connect(s) as c:
        assert query(c, "SELECT ClosePrice FROM dbo.DailyPrice WHERE StockId=1 AND TradeDate=?", (d,))[0]["ClosePrice"] == stored
    assert counts(s, it_env["db"]) == before
    rec = ops(it_env, "SELECT Ticker, TradeDate, DetectedBy, Status FROM ops.PriceReconciliation WHERE TradeDate=?", (d,))
    assert rec == [{"Ticker": "TST01", "TradeDate": d.isoformat(), "DetectedBy": "SESSION_CONFLICT", "Status": "PENDING_REVIEW"}]
    sess = ops(it_env, "SELECT Status, ErrorCode, Unchanged, Conflicts FROM ops.BackfillSession WHERE JobId=? AND SessionDate=?", (r["job_id"], d))[0]
    assert (sess["Status"], sess["ErrorCode"], sess["Unchanged"], sess["Conflicts"]) == ("PARTIAL", "REVISION_CONFLICT", 4, 1)
    # same revision again: no duplicate review item
    svc(it_env, FakeProvider(w1_data(bump={("TST01", d): Decimal("0.7")}))).run(W1[0], W1[1].isoformat())
    assert len(ops(it_env, "SELECT 1 AS x FROM ops.PriceReconciliation WHERE TradeDate=?", (d,))) == 1


W2 = (dt.date(2026, 8, 3), dt.date(2026, 8, 31))


def test_interrupted_job_resumes_without_refetch_or_duplicates(it_env, monkeypatch):
    s = it_env["settings"]
    service = svc(it_env, FakeProvider(series(*W2)))
    real = service._apply_session
    calls = {"n": 0}

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 6:
            raise KeyboardInterrupt
        return real(*a, **k)
    monkeypatch.setattr(service, "_apply_session", flaky)
    with pytest.raises(KeyboardInterrupt):
        service.run(W2[0], W2[1].isoformat())
    job = ops(it_env, "SELECT TOP 1 JobId, Status FROM ops.BackfillJob ORDER BY JobId DESC")[0]
    assert job["Status"] == "INTERRUPTED"
    assert window_rows(it_env, *W2) == 5 * 5
    fresh = FakeProvider(series(*W2))
    r = svc(it_env, fresh).run(None, "latest", resume=True)
    n = len(list(weekdays(*W2)))
    assert (r["job_id"], r["status"], r["exit_code"]) == (job["JobId"], "COMPLETED", 0)
    assert fresh.calls == []                                # staged provider data reused, nothing re-downloaded
    assert window_rows(it_env, *W2) == n * 5
    assert ops(it_env, "SELECT ResumeCount FROM ops.BackfillJob WHERE JobId=?", (job["JobId"],))[0]["ResumeCount"] == 1
    assert ops(it_env, "SELECT COUNT(*) AS n FROM ops.BackfillSession WHERE JobId=?", (job["JobId"],))[0]["n"] == n


W3 = (dt.date(2026, 7, 1), dt.date(2026, 7, 31))


def test_source_down_for_one_ticker_retries_then_resume_refetches_only_it(it_env):
    waits = []
    r = svc(it_env, FakeProvider(series(*W3), fail_symbols={"TST04": "ConnectionError: reset by peer"}), sleep=waits.append).run(W3[0], W3[1].isoformat())
    n = len(list(weekdays(*W3)))
    assert (r["status"], r["fetch_failed_chunks"], r["rows_missing"], r["rows_inserted"]) == ("COMPLETED_WITH_GAPS", 1, n, n * 4)
    assert waits == [5.0, 15.0] and r["fetch_retries"] == 2   # finite retries with exponential backoff
    healthy = FakeProvider(series(*W3))
    r2 = svc(it_env, healthy).run(None, "latest", resume=True, job_ref=r["job_ref"])
    assert [c[0] for c in healthy.calls] == [("TST04",)]
    assert (r2["status"], r2["rows_inserted"]) == ("COMPLETED", n * 5)
    assert window_rows(it_env, *W3) == n * 5


def test_provider_down_fails_cleanly_without_writes(it_env):
    before = counts(it_env["settings"], it_env["db"])
    with pytest.raises(bf.BackfillError) as e:
        svc(it_env, FakeProvider(raise_error=ProviderError("PROVIDER_TIMEOUT", "bridge exceeded 180s"))).run(dt.date(2026, 4, 1), "2026-04-30")
    assert e.value.code == "REFERENCE_UNAVAILABLE"
    assert counts(it_env["settings"], it_env["db"]) == before
    assert ops(it_env, "SELECT TOP 1 Status, ErrorCode FROM ops.BackfillJob ORDER BY JobId DESC")[0] == {"Status": "FAILED", "ErrorCode": "REFERENCE_UNAVAILABLE"}


W4 = (dt.date(2026, 6, 1), dt.date(2026, 6, 30))


def test_sql_failure_rolls_back_only_that_session_and_resume_repairs(it_env, monkeypatch):
    bad = dt.date(2026, 6, 10)
    service = svc(it_env, FakeProvider(series(*W4)))
    real = service._proc

    def proc(dataset_id, session, *a):
        if session == bad:
            raise SqlError(50000, "simulated deadlock victim")
        return real(dataset_id, session, *a)
    monkeypatch.setattr(service, "_proc", proc)
    r = service.run(W4[0], W4[1].isoformat())
    n = len(list(weekdays(*W4)))
    assert (r["status"], r["session_status_counts"]) == ("FAILED", {"COMPLETE": n - 1, "FAILED": 1})
    assert window_rows(it_env, bad, bad) == 0 and window_rows(it_env, *W4) == (n - 1) * 5
    run = ops(it_env, "SELECT Status, ErrorCode, InsertedCount FROM ops.EodRun WHERE BatchRef=? AND SessionDate=?", (r["job_ref"], bad))[0]
    assert run == {"Status": "FAILED", "ErrorCode": "SQL_50000", "InsertedCount": 0}
    r2 = svc(it_env, FakeProvider(series(*W4))).run(None, "latest", resume=True, job_ref=r["job_ref"])
    assert (r2["status"], window_rows(it_env, *W4)) == ("COMPLETED", n * 5)


def test_ticker_subset_is_partial_never_success(it_env):
    W5 = (dt.date(2026, 5, 4), dt.date(2026, 5, 8))
    r = svc(it_env, FakeProvider(series(*W5))).run(W5[0], W5[1].isoformat(), tickers=["tst01", "TST02"])
    assert (r["status"], r["rows_inserted"], r["tickers"]) == ("COMPLETED_WITH_GAPS", 10, 2)
    assert {x["ErrorCode"] for x in ops(it_env, "SELECT ErrorCode FROM ops.EodRun WHERE BatchRef=?", (r["job_ref"],))} == {"SUBSET_JOB"}
    with pytest.raises(bf.BackfillError) as e:
        svc(it_env, FakeProvider(series(*W5))).run(W5[0], W5[1].isoformat(), tickers=["NOPE"])
    assert e.value.code == "TICKER_NOT_IN_UNIVERSE"


def test_tail_sessions_are_all_or_nothing_and_never_jump_observed_through(it_env):
    s = it_env["settings"]
    W6 = (dt.date(2026, 10, 1), dt.date(2026, 10, 9))
    data = series(*W6)
    data["TST02"] = [({**x, "high": "1"} if x["time"].startswith("2026-10-06") else x) for x in data["TST02"]]
    r = svc(it_env, FakeProvider(data)).run(W6[0], W6[1].isoformat())
    sess = {x["SessionDate"]: (x["Status"], x["ErrorCode"]) for x in ops(it_env, "SELECT SessionDate, Status, ErrorCode FROM ops.BackfillSession WHERE JobId=?", (r["job_id"],))}
    assert sess["2026-10-01"][0] == "COMPLETE" and sess["2026-10-05"][0] == "COMPLETE"
    assert sess["2026-10-06"] == ("NOT_WRITTEN", "TAIL_REQUIRES_COMPLETE_UNIVERSE")
    assert {sess[d] for d in ("2026-10-07", "2026-10-08", "2026-10-09")} == {("NOT_WRITTEN", "TAIL_BLOCKED_BY_EARLIER_GAP")}
    assert counts(s, it_env["db"])["observed"] == "2026-10-05"
    assert ops(it_env, "SELECT Code FROM ops.BackfillReject WHERE JobId=?", (r["job_id"],)) == [{"Code": "OHLC_RANGE"}]
    r2 = svc(it_env, FakeProvider(series(*W6))).run(W6[0], W6[1].isoformat())
    assert r2["status"] == "COMPLETED" and counts(s, it_env["db"])["observed"] == "2026-10-09"


class OldRowProvider(FakeProvider):
    """Adds a 2022 candle to every response (as a provider might) to prove the floor holds at staging time."""
    def fetch(self, symbols, start, end):
        res = super().fetch(symbols, start, end)
        for sym in symbols:
            res.rows.setdefault(sym, []).insert(0, fake_candle(sym if sym in TICKERS else "VN30", dt.date(2022, 12, 30)))
        return FetchResult(res.rows, res.errors, res.meta)


def test_rows_before_2023_are_never_staged_or_written(it_env):
    W7 = (dt.date(2023, 1, 1), dt.date(2023, 1, 6))
    r = svc(it_env, OldRowProvider(series(dt.date(2023, 1, 2), W7[1], holidays={dt.date(2023, 1, 2)}))).run(W7[0], W7[1].isoformat())
    assert (r["status"], r["sessions_planned"], r["rows_inserted"]) == ("COMPLETED", 4, 20)
    assert ops(it_env, "SELECT MIN(RowsOutOfWindow) AS m FROM ops.BackfillFetch WHERE JobId=?", (r["job_id"],))[0]["m"] == 1
    assert ops(it_env, "SELECT COUNT(*) AS n FROM ops.BackfillStaging WHERE TradeDate<'2023-01-01'")[0]["n"] == 0
    with connect(it_env["settings"]) as c:
        assert query(c, "SELECT COUNT(*) AS n FROM dbo.DailyPrice WHERE TradeDate<'2023-01-01'")[0]["n"] == 0
        assert query(c, "SELECT COUNT(*) AS n FROM dbo.TradingDay WHERE TradeDate<'2023-01-01'")[0]["n"] == 0


def test_year_chunks_checkpoint_per_ticker_and_year(it_env):
    W8 = (dt.date(2025, 12, 29), dt.date(2026, 1, 6))
    r = svc(it_env, FakeProvider(series(*W8))).run(W8[0], W8[1].isoformat())
    rows = ops(it_env, "SELECT Ticker, ChunkStart, ChunkEnd FROM ops.BackfillFetch WHERE JobId=? ORDER BY Ticker, ChunkStart", (r["job_id"],))
    assert len(rows) == 2 * (len(TICKERS) + 1)
    assert {(x["ChunkStart"], x["ChunkEnd"]) for x in rows} == {("2025-12-29", "2025-12-31"), ("2026-01-01", "2026-01-06")}


def test_concurrent_job_is_refused_by_lock(it_env):
    import pyodbc
    from marketlab_app.db import connection_string
    s = it_env["settings"]
    holder = pyodbc.connect(connection_string(s, it_env["ops_db"]), autocommit=True)
    try:
        holder.cursor().execute("EXEC sys.sp_getapplock @Resource=?, @LockMode='Exclusive', @LockOwner='Session'", f"MarketLab.Backfill.{it_env['db']}.1")
        jobs_before = len(ops(it_env, "SELECT JobId FROM ops.BackfillJob"))
        with pytest.raises(bf.BackfillError) as e:
            svc(it_env, FakeProvider(series(*W1))).run(W1[0], W1[1].isoformat())
        assert (e.value.code, e.value.exit_code) == ("LOCK_BUSY", 10)
        assert len(ops(it_env, "SELECT JobId FROM ops.BackfillJob")) == jobs_before
    finally:
        holder.close()


def test_real_job_requires_verified_backup_unless_test_trigger(it_env):
    service = bf.BackfillService(it_env["settings"], provider=FakeProvider(series(*W1)), clock=CLOCK, trigger="CLI", backup_fn=lambda: {"verified": False, "backups": []})
    with pytest.raises(bf.BackfillError) as e:
        service.run(W1[0], W1[1].isoformat())
    assert e.value.code == "BACKUP_REQUIRED"
    job = ops(it_env, "SELECT TOP 1 Status, ErrorCode, BackupVerifiedAtUtc FROM ops.BackfillJob ORDER BY JobId DESC")[0]
    assert job == {"Status": "FAILED", "ErrorCode": "BACKUP_REQUIRED", "BackupVerifiedAtUtc": None}


def test_calendar_uses_stock_majority_when_reference_omits_a_session(it_env):
    """Observed on KBS: the VN30 index series omitted 2025-04-04 in one call while every stock had a candle."""
    W9 = (dt.date(2026, 3, 2), dt.date(2026, 3, 13))
    data = series(*W9)
    data[REF] = [x for x in data[REF] if not x["time"].startswith("2026-03-04")]
    # a lone candle on a date nobody else traded (below the 50% threshold, no reference): not a session
    data[REF] = [x for x in data[REF] if not x["time"].startswith("2026-03-11")]
    for t in TICKERS[1:]:
        data[t] = [x for x in data[t] if not x["time"].startswith("2026-03-11")]
    r = svc(it_env, FakeProvider(data)).run(W9[0], W9[1].isoformat())
    assert r["calendar_evidence"] == {"REFERENCE+TICKERS": 8, "TICKERS_ONLY": 1}
    assert r["tickers_only_dates"] == ["2026-03-04"] and r["extra_provider_dates"] == 1
    assert window_rows(it_env, dt.date(2026, 3, 4), dt.date(2026, 3, 4)) == 5
    assert window_rows(it_env, dt.date(2026, 3, 11), dt.date(2026, 3, 11)) == 0
    msg = ops(it_env, "SELECT Message FROM ops.BackfillSession WHERE JobId=? AND SessionDate='2026-03-04'", (r["job_id"],))[0]["Message"]
    assert msg.startswith("[calendar TICKERS_ONLY]")
    cov = coverage(it_env["settings"], W9[0], W9[1], job_id=r["job_id"])
    assert cov["calendar"]["sessions"] == 9 and cov["calendar"]["evidence"] == {"REFERENCE+TICKERS": 8, "TICKERS_ONLY": 1}
