"""Compare a RUNNING MarketLab API (HTTP) with direct SQL Server queries on the same database.

uv run python scripts/verify_api_vs_sql.py --base-url http://127.0.0.1:8000 --out <report.json>
Reads connection settings from .env / MARKETLAB_* (same as the server). Read-only. Exit 0 only if every check matches.
Reports for REAL_PRIVATE contain only counts/hashes, never price values (safe to keep with private evidence anyway).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from marketlab_app.config import load_settings  # noqa: E402
from marketlab_app.db import connect, query  # noqa: E402


def h(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    s = load_settings()
    api = httpx.Client(base_url=args.base_url, timeout=60)
    checks = []

    def check(name, api_value, sql_value):
        checks.append({"check": name, "api": api_value, "sql": sql_value, "match": api_value == sql_value})

    meta = api.get("/api/meta").json()
    check("mode", meta["mode"], s.mode)
    check("database", meta["database"], s.sql_database)
    datasets = api.get("/api/datasets").json()["items"]
    with connect(s) as c:
        sql_ds = query(c, "SELECT DatasetId, DataKind, ObservedThrough, (SELECT COUNT(*) FROM dbo.DailyPrice p WHERE p.DatasetId=d.DatasetId) AS n FROM dbo.Dataset d ORDER BY DatasetId")
        check("datasets (id, kind, observed, price rows)", [(d["DatasetId"], d["DataKind"], d["ObservedThrough"], d["PriceRows"]) for d in datasets],
              [(d["DatasetId"], d["DataKind"], d["ObservedThrough"], d["n"]) for d in sql_ds])
        for d in sql_ds:
            ds = d["DatasetId"]
            latest = api.get("/api/prices/latest", params={"dataset_id": ds}).json()["items"]
            sql_latest = query(c, "SELECT Ticker, TradeDate, ClosePrice, Volume FROM dbo.vw_LatestStockPrice WHERE DatasetId=? ORDER BY Ticker", (ds,))
            check(f"dataset {ds}: vw_LatestStockPrice hash", h([(x["Ticker"], x["TradeDate"], x["ClosePrice"], x["Volume"]) for x in latest]),
                  h([(x["Ticker"], x["TradeDate"], x["ClosePrice"], x["Volume"]) for x in sql_latest]))
            tick = sql_latest[0]["Ticker"] if sql_latest else None
            if tick:
                ser = api.get("/api/prices/series", params={"dataset_id": ds, "ticker": tick, "max_points": 5000}).json()["points"]
                sql_ser = query(c, "SELECT p.TradeDate, p.OpenPrice, p.HighPrice, p.LowPrice, p.ClosePrice, p.Volume FROM dbo.DailyPrice p JOIN dbo.Stock s ON s.StockId=p.StockId WHERE p.DatasetId=? AND s.Ticker=? ORDER BY p.TradeDate", (ds, tick))
                check(f"dataset {ds}: series {tick} rows", len(ser), len(sql_ser))
                check(f"dataset {ds}: series {tick} hash", h(ser), h(sql_ser))
            page = api.get("/api/prices", params={"dataset_id": ds, "limit": 1}).json()
            check(f"dataset {ds}: price total", page["total"], d["n"])
            today = meta["today_vn"]
            perf = api.get("/api/performance", params={"dataset_id": ds, "as_of": today}).json()["items"]
            sql_perf = query(c, "SELECT e.RunId, COUNT_BIG(*) AS n FROM dbo.fn_EligiblePredictions(?) e WHERE e.DatasetId=? GROUP BY e.RunId ORDER BY e.RunId", (today, ds))
            check(f"dataset {ds}: eligible rows per run at {today}", [(p["RunId"], p["EvaluatedRows"]) for p in perf if p["EvaluatedRows"]],
                  [(p["RunId"], p["n"]) for p in sql_perf])
            if d["n"] and today == dt.date.today().isoformat():
                view = query(c, "SELECT RunId, EvaluatedRows, Accuracy, BrierScore FROM dbo.vw_ModelPerformance WHERE DatasetId=? ORDER BY RunId", (ds,))
                check(f"dataset {ds}: vw_ModelPerformance (as_of today) accuracy", [(v["RunId"], round(v["Accuracy"], 10)) for v in view],
                      [(p["RunId"], round(p["Accuracy"], 10)) for p in perf if p["Accuracy"] is not None])
    if not s.is_demo:
        last = api.get("/api/ops/last-status", params={"dataset_id": sql_ds[0]["DatasetId"]})
        if last.status_code == 200:
            with connect(s, s.ops_database) as c:
                sql_last = query(c, "SELECT MAX(SessionDate) AS d FROM ops.EodRun WHERE DatabaseName=? AND Status='SUCCESS'", (s.sql_database,))[0]["d"]
                runs = query(c, "SELECT COUNT(*) AS n FROM ops.EodRun WHERE DatabaseName=?", (s.sql_database,))[0]["n"]
            check("ops: last successful trade date", last.json()["last_successful_trade_date"], sql_last)
            check("ops: run count", api.get("/api/ops/runs", params={"limit": 1}).json()["total"], runs)
    report = {"checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "base_url": args.base_url, "mode": s.mode,
              "database": s.sql_database, "passed": all(c["match"] for c in checks), "checks": checks}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    for c in checks:
        print(("PASS " if c["match"] else "FAIL ") + c["check"])
    print("RESULT", "PASS" if report["passed"] else "FAIL", "->", args.out)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
