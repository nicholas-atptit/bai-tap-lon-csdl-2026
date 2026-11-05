"""UI -> API -> SQL 1:1 journeys on the RUNNING DEMO instance (synthetic data only; safe to publish).

uv run python scripts/ui_api_sql_journeys.py --base-url http://127.0.0.1:8000 --out tests/product_evidence/ui_api_sql_journeys.json
Each journey reads the value rendered in Edge, the JSON from the API and a parameterized SELECT/EXEC, and compares them.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from marketlab_app.config import load_settings  # noqa: E402
from marketlab_app.db import connect, query  # noqa: E402


def vn_num(text: str) -> float:
    return float(text.strip().replace("%", "").replace(".", "").replace(",", "."))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    s = load_settings(env={"MARKETLAB_MODE": "DEMO_OFFLINE", "MARKETLAB_SQL_DATABASE": "MarketLabVN30_Demo"})
    api = httpx.Client(base_url=a.base_url, timeout=30)
    rows = []
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p, connect(s) as c:
        b = p.chromium.launch(channel="msedge", headless=True)
        pg = b.new_context(bypass_csp=True, viewport={"width": 1440, "height": 900}).new_page()

        # J1 overview: eligible predictions at today (VN)
        pg.goto(a.base_url + "/#tab=overview")
        pg.wait_for_selector("#overviewCards .card >> nth=3")
        ui = pg.locator("#overviewCards .card >> nth=3").locator(".v").inner_text()
        o = api.get("/api/overview", params={"dataset_id": 1}).json()
        sql = query(c, "SELECT COUNT_BIG(*) AS n FROM dbo.fn_EligiblePredictions(?) WHERE DatasetId=1", (o["as_of"],))[0]["n"]
        rows.append(("J1 overview eligible predictions", f"as_of={o['as_of']}", vn_num(ui), o["eligible_predictions"], sql))

        # J2 price table filtered by ticker + date range: row count and the max close in the window
        pg.goto(a.base_url + "/#tab=market&ds=1&t=DEMO03&f=2025-02-01&to=2025-02-14")
        pg.wait_for_function("document.querySelector('#pricePager span') !== null")
        ui_total = int(pg.locator("#pricePager span").inner_text().split("/")[-1].strip())
        api_p = api.get("/api/prices", params={"dataset_id": 1, "ticker": "DEMO03", "date_from": "2025-02-01", "date_to": "2025-02-14", "limit": 1}).json()
        sql_n = query(c, "SELECT COUNT(*) AS n FROM dbo.DailyPrice p JOIN dbo.Stock s ON s.StockId=p.StockId WHERE p.DatasetId=1 AND s.Ticker=? AND p.TradeDate BETWEEN ? AND ?",
                      ("DEMO03", "2025-02-01", "2025-02-14"))[0]["n"]
        rows.append(("J2 prices DEMO03 2025-02-01..14 row count", "ticker+date filter", ui_total, api_p["total"], sql_n))
        ui_first_close = vn_num(pg.locator("#priceTable tbody tr >> nth=0").locator("td >> nth=4").inner_text())
        sql_close = query(c, "SELECT TOP 1 ClosePrice FROM dbo.DailyPrice p JOIN dbo.Stock s ON s.StockId=p.StockId WHERE p.DatasetId=1 AND s.Ticker='DEMO03' AND p.TradeDate<='2025-02-14' ORDER BY p.TradeDate DESC")[0]["ClosePrice"]
        rows.append(("J3 latest close in window (table first row)", "2025-02-14", ui_first_close, api_p["items"][0]["ClosePrice"], round(sql_close, 4)))

        # J4 chart series = SQL rows for the ticker
        ser = api.get("/api/prices/series", params={"dataset_id": 1, "ticker": "DEMO03"}).json()
        n_bars = pg.locator("#chart svg path.bar").count()
        sql_rows = query(c, "SELECT COUNT(*) AS n FROM dbo.DailyPrice p JOIN dbo.Stock s ON s.StockId=p.StockId WHERE p.DatasetId=1 AND s.Ticker='DEMO03' AND p.TradeDate BETWEEN '2025-02-01' AND '2025-02-14'")[0]["n"]
        rows.append(("J4 chart volume bars in window", "2025-02-01..14", n_bars, len([x for x in ser["points"] if "2025-02-01" <= x["TradeDate"] <= "2025-02-14"]), sql_rows))

        # J5 performance of run 1 at as_of 2026-07-01 (UI accuracy %) vs API vs usp_GetModelPerformance
        pg.goto(a.base_url + "/#tab=forecast&ds=1&run=1&asof=2026-07-01")
        pg.wait_for_selector("#runTable tbody tr")
        ui_acc = vn_num(pg.locator("#runTable tbody tr >> nth=0").locator("td >> nth=9").inner_text()) / 100
        perf = api.get("/api/performance", params={"dataset_id": 1, "run_id": 1, "as_of": "2026-07-01"}).json()["items"][0]
        proc = query(c, "EXEC dbo.usp_GetModelPerformance 'demo_baseline',1,5,'20250101','20251231','20260701'")[0]
        rows.append(("J5 run 1 accuracy as_of 2026-07-01", "fn_EligiblePredictions vs usp_GetModelPerformance",
                     round(ui_acc, 6), round(perf["Accuracy"], 6), round(float(proc["Accuracy"]), 6)))
        rows.append(("J6 run 1 eligible rows as_of 2026-07-01", "", vn_num(pg.locator("#runTable tbody tr >> nth=0").locator("td >> nth=6").inner_text()),
                     perf["EvaluatedRows"], proc["EvaluatedRows"]))

        # J7 comparison of runs 1,2 on the common set
        pg.goto(a.base_url + "/#tab=compare&ds=1")
        pg.wait_for_selector("#compareRuns input >> nth=1")
        pg.fill("#cAsOf", "2026-07-01")
        pg.click("#compareForm button[type=submit]")
        pg.wait_for_selector("#compareResult tbody tr >> nth=1")
        ui_common = vn_num(pg.locator("#compareResult tbody tr >> nth=1").locator("td >> nth=1").inner_text())
        cmp_api = api.get("/api/models/compare", params={"run_ids": "1,2", "date_from": "2025-01-02", "date_to": "2025-02-17", "as_of": "2026-07-01"}).json()["rows"]
        cmp_sql = query(c, "EXEC dbo.usp_CompareModels '1,2','20250102','20250217','20260701'")
        rows.append(("J7 compare runs 1,2 common observations (run 2)", "usp_CompareModels", ui_common, cmp_api[1]["CommonObservations"], cmp_sql[1]["CommonObservations"]))
        ui_acc2 = vn_num(pg.locator("#compareResult tbody tr >> nth=1").locator("td >> nth=2").inner_text()) / 100
        rows.append(("J8 compare run 2 accuracy", "usp_CompareModels", round(ui_acc2, 6), round(cmp_api[1]["Accuracy"], 6), round(float(cmp_sql[1]["Accuracy"]), 6)))
        b.close()
    out = [{"journey": j, "scope": sc, "ui": u, "api": ap_, "sql": sq, "match": abs(float(u) - float(ap_)) < 1e-4 and abs(float(ap_) - float(sq)) < 1e-4}
           for j, sc, u, ap_, sq in rows]
    report = {"checked_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"), "base_url": a.base_url,
              "database": "MarketLabVN30_Demo (SYNTHETIC)", "passed": all(x["match"] for x in out), "journeys": out}
    a.out.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    for x in out:
        print("PASS" if x["match"] else "FAIL", x["journey"], "| UI", x["ui"], "| API", x["api"], "| SQL", x["sql"])
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
