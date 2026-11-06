"""Shared fixtures. Integration tests create isolated MarketLabVN30_IT_* databases tagged MarketLabPurpose=INTEGRATION_TEST
and drop ONLY those (set MARKETLAB_KEEP_IT_DB=1 to keep them). The public demo and research databases are never written."""
from __future__ import annotations

import datetime as dt
import os
import sys
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from marketlab_app import deploy  # noqa: E402
from marketlab_app.config import load_settings  # noqa: E402
from marketlab_app.db import connect, query  # noqa: E402
from marketlab_app.eod.normalize import VN_TZ  # noqa: E402

STAMP = dt.datetime.now().strftime("%Y%m%d%H%M%S")
TICKERS = ["TST01", "TST02", "TST03", "TST04", "TST05"]
CLOCK = dt.datetime(2026, 11, 5, 20, 0, tzinfo=VN_TZ)


def sql_available() -> bool:
    try:
        with connect(load_settings(env={"MARKETLAB_SQL_DATABASE": "master"}), "master") as c:
            query(c, "SELECT 1 AS x")
        return True
    except Exception:  # noqa: BLE001
        return False


def it_settings(db: str, ops_db: str, **extra) -> object:
    env = {"MARKETLAB_MODE": "REAL_PRIVATE", "MARKETLAB_SQL_DATABASE": db, "MARKETLAB_OPS_DATABASE": ops_db,
           "MARKETLAB_OPS_TOKEN": "t" * 40, "MARKETLAB_LOG_DIR": str(ROOT / "var" / "test_logs")}
    env.update(extra)
    return load_settings(env=env)


def drop_it_database(name: str) -> None:
    assert name.startswith("MarketLabVN30_IT_"), name
    s = load_settings(env={"MARKETLAB_SQL_DATABASE": "master"})
    with connect(s, "master") as c:
        if not query(c, "SELECT 1 AS x FROM sys.databases WHERE name=?", (name,)):
            return
    with connect(s, name) as d:
        tag = query(d, "SELECT CONVERT(nvarchar(50),value) AS v FROM sys.extended_properties WHERE class=0 AND name=N'MarketLabPurpose'")
    if not tag or tag[0]["v"] not in ("INTEGRATION_TEST", "OPS"):
        raise RuntimeError(f"{name} is not tagged as an integration-test database; not dropping")
    with connect(s, "master") as c:
        c.cursor().execute(f"ALTER DATABASE [{name}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [{name}];")


def weekdays(a: dt.date, b: dt.date):
    d = a
    while d <= b:
        if d.weekday() < 5:
            yield d
        d += dt.timedelta(days=1)


def fake_candle(ticker: str, d: dt.date, bump: Decimal = Decimal(0)) -> dict:
    base = Decimal(10 + TICKERS.index(ticker) * 5 if ticker in TICKERS else 1000) + Decimal(d.toordinal() % 17) / 10 + bump
    return {"time": f"{d.isoformat()}T07:00:00", "open": str(base), "high": str(base + Decimal("0.5")),
            "low": str(base - Decimal("0.4")), "close": str(base + Decimal("0.1")), "volume": str(1000 + d.day * 10)}


def fake_series(start=dt.date(2026, 9, 1), end=dt.date(2026, 11, 5), holidays=(), tickers=TICKERS, ref="VN30") -> dict:
    data = {t: [fake_candle(t, d) for d in weekdays(start, end) if d not in holidays] for t in tickers}
    data[ref] = [fake_candle(ref, d) for d in weekdays(start, end) if d not in holidays]
    return data


def seed_it_business(settings, db: str) -> int:
    """REAL_PRIVATE test fixture: 5 TST stocks, VN30-tagged snapshot, run with pre-registered future calendar."""
    with connect(settings, db, autocommit=False) as c:
        cur = c.cursor()
        cur.execute("INSERT dbo.Market VALUES(1,'TSTMKT',N'Integration test market (not real)','VND')")
        cur.execute("INSERT dbo.StockIndex VALUES(1,1,'VN30',N'Test index fixture')")
        for i, t in enumerate(TICKERS, start=1):
            cur.execute("INSERT dbo.Stock(StockId,MarketId,Ticker,IsSynthetic) VALUES(?,1,?,0)", i, t)
            cur.execute("INSERT dbo.IndexMembership VALUES(1,?,'2026-06-01','2026-06-30',N'test fixture')", i)
        cur.execute("""INSERT dbo.Dataset VALUES(1,'IT_FAKE_ADAPTER',1,'REAL_PRIVATE','SOURCE_CLOSE',N'test unit','2026-10-01',
                       N'tests/product','INTEGRATION TEST FIXTURE: FakeProvider values, not market data')""")
        for d in ("2026-10-01", "2026-10-02", "2026-10-05"):
            cur.execute("INSERT dbo.TradingDay VALUES(1,?)", d)
        for i, t in enumerate(TICKERS, start=1):
            if t == "TST05":
                continue  # missing origin endpoint -> never eligible
            cd = fake_candle(t, dt.date(2026, 10, 1))
            cur.execute("EXEC dbo.usp_InsertDailyPrice 1,?,'2026-10-01',?,?,?,?,?", i, cd["open"], cd["high"], cd["low"], cd["close"], int(cd["volume"]))
        cur.execute("INSERT dbo.ForecastModel VALUES(1,'it_model_a',N'Test model A',N'fixture')")
        cur.execute("INSERT dbo.ForecastModel VALUES(2,'it_model_b',N'Test model B',N'fixture')")
        cur.execute("INSERT dbo.TargetDefinition VALUES(1,'CLOSE_UP_2',2,'PROBABILITY_CLOSE_UP','CLOSE_TARGET_GT_CLOSE_ORIGIN_ELSE_ZERO')")
        cur.execute("INSERT dbo.TargetDefinition VALUES(2,'CLOSE_UP_1',1,'PROBABILITY_CLOSE_UP','CLOSE_TARGET_GT_CLOSE_ORIGIN_ELSE_ZERO')")
        for run, model, target in ((1, 1, 1), (2, 2, 1), (3, 1, 2)):
            cur.execute("INSERT dbo.ModelRun(RunId,RunCode,ModelId,DatasetId,TargetId,TrainStart,TrainEnd,ValidationEnd,Threshold,EvaluationClass,SourceRun) "
                        "VALUES(?,?,?,1,?,'2026-01-01','2026-06-30','2026-09-30',0.5,'RETROSPECTIVE_OOS','test fixture')",
                        run, f"IT_RUN_{run}", model, target)
        for i, t in enumerate(TICKERS, start=1):
            cur.execute("EXEC dbo.usp_AddPrediction 1,?,'2026-10-01','2026-10-05',?", i, Decimal("0.6") if i % 2 else Decimal("0.4"))
            cur.execute("EXEC dbo.usp_AddPrediction 2,?,'2026-10-01','2026-10-05',?", i, Decimal("0.7"))
            cur.execute("EXEC dbo.usp_AddPrediction 3,?,'2026-10-01','2026-10-02',?", i, Decimal("0.55"))
        c.commit()
    return 1


@pytest.fixture(scope="session")
def require_sql():
    if not sql_available():
        pytest.skip("SQL Server not reachable (BLOCKED: integration tests need a local instance)")


@pytest.fixture(scope="module")
def it_env(require_sql, tmp_path_factory):
    """Fresh business DB (schema 00-06 + 13 extension, test fixture rows) + fresh ops DB."""
    suffix = os.environ.get("PYTEST_XDIST_WORKER", "") + tmp_path_factory.getbasetemp().name[-6:].replace("-", "")
    db = f"MarketLabVN30_IT_{STAMP}_{suffix}_Eod"[:100]
    ops_db = f"MarketLabVN30_IT_{STAMP}_{suffix}_Ops"[:100]
    s = it_settings(db, ops_db)
    work = ROOT / "var" / "test_deploy" / STAMP
    deploy.create_database(s, db, "INTEGRATION_TEST")
    deploy.deploy_business_schema(s, db, work)
    deploy.apply_eod_extension(s, db, work)
    seed_it_business(s, db)
    deploy.create_database(s, ops_db, "INTEGRATION_TEST")
    deploy.run_sqlcmd(s, ROOT / "sql" / "14_ops_database.sql", ops_db, log=work / f"{ops_db}.log")
    deploy.run_sqlcmd(s, ROOT / "sql" / "15_ops_schema_v2.sql", ops_db, log=work / f"{ops_db}_v2.log")
    deploy.run_sqlcmd(s, ROOT / "sql" / "16_ops_schema_v3_backfill.sql", ops_db, log=work / f"{ops_db}_v3.log")
    deploy.register_eod_config(s, ops_db, db, 1, "VN30", dt.date(2026, 6, 30), "VN30", "test fixture")
    yield {"settings": s, "db": db, "ops_db": ops_db}
    if os.environ.get("MARKETLAB_KEEP_IT_DB") != "1":
        drop_it_database(db)
        drop_it_database(ops_db)


def counts(settings, db: str) -> dict:
    with connect(settings, db) as c:
        return query(c, """SELECT (SELECT COUNT(*) FROM dbo.DailyPrice) AS prices, (SELECT COUNT(*) FROM dbo.TradingDay) AS days,
                                  (SELECT ObservedThrough FROM dbo.Dataset WHERE DatasetId=1) AS observed,
                                  (SELECT COUNT(*) FROM dbo.Prediction) AS preds""")[0]
