"""Compare the pages of a RUNNING MarketLab web application (server-rendered HTML) with direct SQL on the same database.

uv run python scripts/verify_web_vs_sql.py --base-url http://127.0.0.1:8000 --out tests/product_evidence/web_vs_sql_demo.json
Reads connection settings from .env / MARKETLAB_* (same as the server). Read-only. Values are taken from the machine-readable
data-metric / data-v attributes the templates emit next to every formatted number. Exit 0 only if every check matches.
For REAL_PRIVATE the report stores counts and hashes only, never price values.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import re
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from marketlab_app.config import load_settings  # noqa: E402
from marketlab_app.db import connect, query  # noqa: E402
from marketlab_app.web_app import fmt_num  # noqa: E402


def h(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def metric(page: str, name: str) -> str:
    m = re.search(rf'data-metric="{name}"><div class="k">[^<]*</div><div class="v">([^<]*)</div>', page)
    return html.unescape(m.group(1)) if m else "<missing>"


def table_v(page: str, table_id: str) -> list[list[str]]:
    m = re.search(rf'<table id="{table_id}">.*?<tbody>(.*?)</tbody>', page, re.S)
    return [re.findall(r'data-v="([^"]*)"', r) for r in re.findall(r"<tr.*?</tr>", m.group(1), re.S)] if m else []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    s = load_settings()
    web = httpx.Client(base_url=args.base_url, timeout=60)
    checks = []

    def check(name, ui, sql):
        checks.append({"check": name, "ui": ui, "sql": sql, "match": ui == sql})

    with connect(s) as c:
        ds = query(c, "SELECT TOP 1 DatasetId FROM dbo.Dataset ORDER BY DatasetId")[0]["DatasetId"]
        home = web.get("/", params={"ds": ds}).text
        check("mode label", s.mode in home, True)
        check("overview: price rows", metric(home, "price_rows"), fmt_num(query(c, "SELECT COUNT(*) AS n FROM dbo.DailyPrice WHERE DatasetId=?", (ds,))[0]["n"], 0))
        check("overview: stocks with prices", metric(home, "stocks_with_prices"),
              fmt_num(query(c, "SELECT COUNT(DISTINCT StockId) AS n FROM dbo.DailyPrice WHERE DatasetId=?", (ds,))[0]["n"], 0))
        check("overview: last price date", metric(home, "last_price_date"), str(query(c, "SELECT MAX(TradeDate) AS d FROM dbo.DailyPrice WHERE DatasetId=?", (ds,))[0]["d"])[:10])
        latest = query(c, "SELECT Ticker, ClosePrice, Volume FROM dbo.vw_LatestStockPrice WHERE DatasetId=? ORDER BY Ticker", (ds,))
        check("overview: vw_LatestStockPrice (hash of close, volume)", h([[float(a), int(b)] for a, b in table_v(home, "latestTable")]),
              h([[x["ClosePrice"], x["Volume"]] for x in latest]))
        tick = latest[0]["Ticker"] if latest else None
        if tick:
            mk = web.get("/market", params={"ds": ds, "t": tick, "sort": "date", "order": "asc"}).text
            sql_rows = query(c, """SELECT TOP 50 p.ClosePrice, p.Volume FROM dbo.DailyPrice p JOIN dbo.Stock s ON s.StockId=p.StockId
                                   WHERE p.DatasetId=? AND s.Ticker=? ORDER BY p.TradeDate""", (ds, tick))
            check(f"market {tick}: first page rows (hash)", h([[float(a), int(b)] for a, b in table_v(mk, "priceTable")]),
                  h([[x["ClosePrice"], x["Volume"]] for x in sql_rows]))
            n = query(c, "SELECT COUNT(*) AS n FROM dbo.DailyPrice p JOIN dbo.Stock s ON s.StockId=p.StockId WHERE p.DatasetId=? AND s.Ticker=?", (ds, tick))[0]["n"]
            check(f"market {tick}: total rows in pager", bool(re.search(rf"/ {fmt_num(n, 0)}</span>", mk)), True)
            pts = json.loads(re.search(r'id="chartData">(.*?)</script>', mk, re.S).group(1))["points"]
            check(f"market {tick}: chart sessions with price", len([p for p in pts if p["ClosePrice"] is not None]), n)
        today = query(c, "SELECT CONVERT(date, SYSDATETIMEOFFSET() AT TIME ZONE 'SE Asia Standard Time') AS d")[0]["d"]
        fc = web.get("/forecast", params={"ds": ds, "as_of": str(today)}).text
        perf = query(c, "SELECT e.RunId, COUNT_BIG(*) AS n FROM dbo.fn_EligiblePredictions(?) e WHERE e.DatasetId=? GROUP BY e.RunId ORDER BY e.RunId", (today, ds))
        ui_runs = {m.group(1): re.findall(r'data-v="([^"]*)"', m.group(0)) for m in re.finditer(r'<tr data-run="(\d+)".*?</tr>', fc, re.S)}
        check(f"forecast: eligible rows per run at {today}", [[int(k), int(v[0])] for k, v in ui_runs.items() if v and v[0] not in ("", "0")],
              [[p["RunId"], p["n"]] for p in perf])
        if not s.is_demo:
            ops = web.get("/ops", params={"ds": ds}).text
            with connect(s, s.ops_database) as o:
                last = query(o, "SELECT MAX(SessionDate) AS d FROM ops.EodRun WHERE DatabaseName=? AND Status='SUCCESS'", (s.sql_database,))[0]["d"]
                runs = query(o, "SELECT COUNT(*) AS n FROM ops.EodRun WHERE DatabaseName=?", (s.sql_database,))[0]["n"]
            if last:
                check("ops: last successful trade date", metric(ops, "last_success"), str(last)[:10])
                check("ops: run count in pager", bool(re.search(rf"/ {fmt_num(runs, 0)}</span>", ops)), True)
    report = {"checked_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"), "base_url": args.base_url, "mode": s.mode,
              "database": s.sql_database, "passed": all(x["match"] for x in checks), "checks": checks}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    for x in checks:
        print(("PASS " if x["match"] else "FAIL ") + x["check"])
    print("RESULT", "PASS" if report["passed"] else "FAIL", "->", args.out)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
