"""Screenshots of the FINAL web UI from the RUNNING instances (Microsoft Edge, Playwright) + manifest.

uv run python scripts/capture_web_final.py --demo http://127.0.0.1:8000 --real http://127.0.0.1:8001
Output: report/final/assets/web_final/*.png + manifest.json (route, data mode, viewport, capture time, redaction).
LIVE (REAL_PRIVATE) screenshots blur every price/volume cell, the price chart and its tooltip before capture: third-party
price records are not redistributed (LICENSE.md). Counts, dates, statuses and tickers stay readable. Read-only: no form is
submitted. Earlier report screenshots (report/final/assets/screens) are left untouched.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "report" / "final" / "assets" / "web_final"
REDACT_CSS = """
#latestTable td.num, #priceTable td.num, #chart svg, .tooltip { filter: blur(7px) !important; }
#chart { position: relative; }
#chart::after { content: "Biểu đồ giá thật được che trong ảnh (dữ liệu bên thứ ba, quyền phân phối UNKNOWN)"; position: absolute;
  inset: 38% 12% auto 12%; text-align: center; background: #fff; border: 1px solid #ccc; padding: 8px; font-size: 13px; }
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", default="http://127.0.0.1:8000")
    ap.add_argument("--real", default="http://127.0.0.1:8001")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.png"):
        old.unlink()
    manifest = []
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge", headless=True)

        def snap(name, base, route, mode, w=1440, h=900, full=True, prep=None, note=""):
            live = mode == "REAL_PRIVATE"
            ctx = b.new_context(viewport={"width": w, "height": h}, bypass_csp=live)   # bypass only to inject the redaction CSS
            pg = ctx.new_page()
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            r = pg.goto(base + route)
            if live:
                pg.add_style_tag(content=REDACT_CSS)
            pg.wait_for_timeout(500)
            if prep:
                prep(pg)
            pg.screenshot(path=str(OUT / name), full_page=full)
            manifest.append({"file": f"report/final/assets/web_final/{name}", "route": route, "http_status": r.status if r else None,
                             "data_mode": mode, "viewport": f"{w}x{h}", "full_page": full,
                             "captured_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
                             "redaction": "price/volume cells, chart and tooltip blurred" if live else "none (synthetic data)",
                             "page_errors": errors, "note": note})
            ctx.close()

        def hover_chart(pg):
            box = pg.locator("#chart svg").bounding_box()
            pg.mouse.move(box["x"] + box["width"] * 0.62, box["y"] + 130)
            pg.wait_for_selector("#tooltip:not([hidden])")

        def zoom_chart(pg):
            box = pg.locator("#chart svg").bounding_box()
            pg.mouse.move(box["x"] + box["width"] * 0.30, box["y"] + 120)
            pg.mouse.down()
            pg.mouse.move(box["x"] + box["width"] * 0.70, box["y"] + 120, steps=8)
            pg.mouse.up()
            pg.wait_for_selector("#zoomReset:not([hidden])")
            hover_chart(pg)

        d, r = a.demo, a.real
        snap("01_live_dashboard_1440.png", r, "/?ds=1", "REAL_PRIVATE", note="KPI: mã, phiên, phạm vi ngày, số OHLCV, EOD, tình trạng dữ liệu")
        snap("02_demo_dashboard_1440.png", d, "/?ds=1", "DEMO_OFFLINE", full=False, note="nhãn DEMO, dữ liệu mô phỏng")
        snap("03_live_ohlcv_2023_all_1440.png", r, "/market?ds=1&t=FPT&f=2023-01-01&to=2026-11-05", "REAL_PRIVATE", full=False,
             note="FPT toàn bộ 2023-01-03 → 2026-11-05, preset Tất cả")
        snap("04_live_ohlcv_default_12m_1440.png", r, "/market?ds=1&t=VPL", "REAL_PRIVATE", note="mặc định 12 tháng, bảng phân trang, xuất CSV")
        snap("05_demo_ohlcv_zoom_tooltip_1440.png", d, "/market?ds=1&t=DEMO03", "DEMO_OFFLINE", full=False, prep=zoom_chart,
             note="kéo chuột để phóng to + tooltip OHLCV, chú giải đơn vị")
        snap("06_live_history_floor_422_1440.png", r, "/market?ds=1&t=FPT&f=2022-06-01&to=2026-11-05", "REAL_PRIVATE", full=False,
             note="Từ ngày < 2023-01-01 bị từ chối (HTTP 422), không truy vấn giá")
        snap("07_live_backfill_1440.png", r, "/backfill?ds=1", "REAL_PRIVATE", note="job backfill, tiến độ, checkpoint mã × năm, độ phủ theo mã")
        snap("08_live_eod_ops_1440.png", r, "/ops?ds=1", "REAL_PRIVATE", note="EOD hằng ngày (không lẫn phiên backfill), lịch phiên, đối soát")
        snap("09_live_forecast_empty_1440.png", r, "/forecast?ds=1", "REAL_PRIVATE", full=False, note="chưa có ModelRun: trạng thái rỗng trung thực")
        snap("10_live_compare_empty_1440.png", r, "/compare?ds=1", "REAL_PRIVATE", full=False, note="không có run để so sánh")
        snap("11_demo_compare_1440.png", d, "/compare?ds=1&runs=1&runs=2&f=2025-01-02&to=2025-02-17&as_of=2026-07-01", "DEMO_OFFLINE",
             full=False, note="so sánh trên tập quan sát chung (usp_CompareModels)")
        snap("12_demo_forecast_1440.png", d, "/forecast?ds=1&run=1&as_of=2026-07-01", "DEMO_OFFLINE", full=False)
        snap("13_live_ohlcv_390.png", r, "/market?ds=1&t=FPT", "REAL_PRIVATE", 390, 844, full=False, note="mobile")
        snap("14_live_backfill_390.png", r, "/backfill?ds=1", "REAL_PRIVATE", 390, 844, full=False, note="mobile")
        snap("15_live_dashboard_768.png", r, "/?ds=1", "REAL_PRIVATE", 768, 1024, full=False, note="tablet")
        snap("16_api_docs_404.png", r, "/api/docs", "REAL_PRIVATE", full=False, note="không còn Swagger/REST gateway")
        b.close()
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    for m in manifest:
        print(m["file"].split("/")[-1], m["http_status"], m["data_mode"], m["viewport"], "errors" if m["page_errors"] else "ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
