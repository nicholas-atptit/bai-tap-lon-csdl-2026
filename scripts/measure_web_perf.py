"""Measure server response times of the RUNNING web application (no prices recorded, timings only).

uv run python scripts/measure_web_perf.py --base-url http://127.0.0.1:8001 --out tests/product_evidence/web_perf_real.json
For each scenario: N sequential requests; reports min / median / p90 / max of the wall time seen by the client and of the
app's own Server-Timing (server-side render incl. SQL). The first request of each scenario is reported separately
(cold: connection pool and SQL plan cache possibly empty).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import statistics
import time
from pathlib import Path

import httpx


def stats(xs: list[float]) -> dict:
    xs = sorted(xs)
    return {"min": round(xs[0], 1), "median": round(statistics.median(xs), 1), "p90": round(xs[int(0.9 * (len(xs) - 1))], 1),
            "max": round(xs[-1], 1)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8001")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--n", type=int, default=15)
    ap.add_argument("--tickers", default="FPT,ACB,VNM,VPL,HPG")
    a = ap.parse_args()
    tickers = a.tickers.split(",")
    scenarios = {
        "overview /": [("/", {})],
        "history default (12 months, chart + page 1)": [("/market", {"t": t}) for t in tickers],
        "history change ticker, all data 2023+": [("/market", {"t": t, "f": "2023-01-01", "to": "2026-12-31"}) for t in tickers],
        "history change date range (2 years)": [("/market", {"t": t, "f": "2024-01-01", "to": "2025-12-31"}) for t in tickers],
        "history page 10 sorted by close": [("/market", {"t": t, "f": "2023-01-01", "to": "2026-12-31", "sort": "close", "order": "asc", "page": "10"}) for t in tickers],
        "CSV export one ticker 2023+": [("/market/export.csv", {"t": t, "f": "2023-01-01", "to": "2026-12-31"}) for t in tickers],
        "backfill page": [("/backfill", {})],
        "EOD ops page": [("/ops", {})],
    }
    out = {"measured_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"), "base_url": a.base_url, "n_per_scenario": a.n,
           "scenarios": {}}
    with httpx.Client(base_url=a.base_url, timeout=60) as c:
        for name, reqs in scenarios.items():
            wall, app, sizes, cold = [], [], [], None
            for i in range(a.n):
                path, params = reqs[i % len(reqs)]
                t0 = time.perf_counter()
                r = c.get(path, params={"ds": "1", **params})
                ms = (time.perf_counter() - t0) * 1000
                if r.status_code != 200:
                    raise SystemExit(f"{name}: HTTP {r.status_code}")
                m = re.search(r"app;dur=([\d.]+)", r.headers.get("server-timing", ""))
                if cold is None:
                    cold = round(ms, 1)
                wall.append(ms)
                app.append(float(m.group(1)) if m else ms)
                sizes.append(len(r.content))
            out["scenarios"][name] = {"first_request_ms": cold, "wall_ms": stats(wall), "server_ms": stats(app),
                                      "html_kb_median": round(statistics.median(sizes) / 1024, 1)}
            print(f"{name:48s} first {cold:7.1f} ms | median {stats(wall)['median']:7.1f} ms | p90 {stats(wall)['p90']:7.1f} ms | "
                  f"{round(statistics.median(sizes) / 1024, 1)} KB")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
