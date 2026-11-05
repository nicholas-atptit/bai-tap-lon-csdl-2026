"""Capture the OFFICIAL screenshots of the polished UI from the RUNNING instances (Edge, headless) + manifest.

uv run python scripts/capture_final_screenshots.py --demo http://127.0.0.1:8000 --real http://127.0.0.1:8001 --real-dry-run 2026-11-05
Output: report/final/assets/screens/*.png + screens_manifest.json (filename, route, data mode, viewport, captured time,
classification, redaction). REAL screenshots keep only counts/dates/statuses: every price/volume cell and the price chart
are blurred in the page before capture (third-party price records are not redistributed; see LICENSE.md).
The optional REAL dry run validates inside SQL Server and rolls back (no business row is written; one DRY_RUN_OK row is
added to the ops log). The ops token is read from .env and never printed; the field is cleared by the UI.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from marketlab_app.config import load_settings  # noqa: E402

OUT = ROOT / "report" / "final" / "assets" / "screens"
REDACT_CSS = """
#latestTable td.num, #priceTable td.num, #predTable td.num, #chart svg, .tooltip { filter: blur(6px) !important; }
#chart::after { content: "Biểu đồ giá thật đã được che trong ảnh báo cáo (dữ liệu bên thứ ba, quyền phân phối UNKNOWN)"; display: block;
  position: absolute; inset: 40% 10% auto 10%; text-align: center; background: #fff; border: 1px solid #ccc; padding: 8px; font-size: 13px; }
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", default="http://127.0.0.1:8000")
    ap.add_argument("--real", default="http://127.0.0.1:8001")
    ap.add_argument("--real-dry-run")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []
    from playwright.sync_api import sync_playwright

    def shot(page, name, route, mode, vp, classification, redaction="none", full=True, note=""):
        path = OUT / name
        page.screenshot(path=str(path), full_page=full)
        manifest.append({"file": f"report/final/assets/screens/{name}", "route": route, "data_mode": mode, "viewport": vp,
                         "captured_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
                         "classification": classification, "redaction": redaction, "note": note})

    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge", headless=True)

        def page_at(base, w, h, hash_=""):
            pg = b.new_context(bypass_csp=True, viewport={"width": w, "height": h}).new_page()
            pg.goto(f"{base}/{hash_}")
            pg.wait_for_function("document.getElementById('modeBadge').className.startsWith('scope ')")
            return pg

        # ---- DEMO (synthetic) --------------------------------------------------------------------------
        pg = page_at(args.demo, 1440, 900)
        pg.wait_for_selector("#latestTable tbody tr >> nth=7")
        shot(pg, "01_demo_overview_1440.png", "/#tab=overview", "DEMO_OFFLINE", "1440x900", "SYNTHETIC")
        pg = page_at(args.demo, 1440, 900, "#tab=market&ds=1&t=DEMO03")
        pg.wait_for_selector("#chart svg path.line")
        pg.wait_for_selector("#priceTable tbody tr")
        box = pg.locator("#chart svg").bounding_box()
        pg.mouse.move(box["x"] + box["width"] * 0.55, box["y"] + 130)
        pg.wait_for_selector("#tooltip:not([hidden])")
        shot(pg, "02_demo_market_chart_table_1440.png", "/#tab=market&t=DEMO03", "DEMO_OFFLINE", "1440x900", "SYNTHETIC", full=False,
             note="chart + tooltip, viewport crop")
        shot(pg, "03_demo_market_full_1440.png", "/#tab=market&t=DEMO03", "DEMO_OFFLINE", "1440x900", "SYNTHETIC")
        pg = page_at(args.demo, 1440, 900, "#tab=forecast&ds=1&run=1&asof=2026-07-01")
        pg.wait_for_selector("#predTable tbody tr")
        shot(pg, "04_demo_forecast_performance_1440.png", "/#tab=forecast&run=1&asof=2026-07-01", "DEMO_OFFLINE", "1440x900", "SYNTHETIC")
        pg = page_at(args.demo, 1440, 900, "#tab=compare&ds=1")
        pg.wait_for_selector("#compareRuns input >> nth=1")
        pg.fill("#cAsOf", "2026-07-01")
        pg.click("#compareForm button[type=submit]")
        pg.wait_for_selector("#compareResult tbody tr >> nth=1")
        shot(pg, "05_demo_model_comparison_1440.png", "/#tab=compare (run 1,2; as_of 2026-07-01)", "DEMO_OFFLINE", "1440x900", "SYNTHETIC")
        pg = page_at(args.demo, 1440, 900, "#tab=ops&ds=1")
        pg.wait_for_selector("#calendarCheck tbody tr")
        shot(pg, "06_demo_ops_disabled_1440.png", "/#tab=ops", "DEMO_OFFLINE", "1440x900", "SYNTHETIC", note="write buttons disabled in DEMO_OFFLINE")
        for vp, (w, h), tab in (("768x1024", (768, 1024), "market"), ("390x844", (390, 844), "overview"), ("390x844", (390, 844), "market")):
            pg = page_at(args.demo, w, h, f"#tab={tab}&ds=1&t=DEMO03")
            pg.wait_for_timeout(1500)
            shot(pg, f"07_demo_{tab}_{vp}.png", f"/#tab={tab}", "DEMO_OFFLINE", vp, "SYNTHETIC")
        pg = b.new_context(viewport={"width": 1440, "height": 900}).new_page()
        pg.goto(args.demo + "/api/docs")
        pg.wait_for_selector(".opblock")
        shot(pg, "08_swagger_1440.png", "/api/docs", "DEMO_OFFLINE", "1440x900", "API_DOCS", full=False, note="no token/Authorization entered")
        pg.locator(".opblock-post").first.click()
        pg.wait_for_timeout(600)
        shot(pg, "09_swagger_ops_eod_1440.png", "/api/docs (POST /api/ops/eod expanded)", "DEMO_OFFLINE", "1440x900", "API_DOCS", full=False)

        # ---- REAL (counts/statuses only; prices blurred) --------------------------------------------------
        if args.real:
            pg = page_at(args.real, 1440, 900)
            pg.wait_for_selector("#latestTable tbody tr")
            pg.add_style_tag(content=REDACT_CSS)
            shot(pg, "10_real_overview_redacted_1440.png", "/#tab=overview", "REAL_PRIVATE", "1440x900", "REAL_PRIVATE",
                 redaction="price/volume cells blurred")
            pg = page_at(args.real, 1440, 900, "#tab=ops&ds=1")
            pg.wait_for_selector("#opsRuns tbody tr")
            if args.real_dry_run:
                pg.on("dialog", lambda d: d.accept())
                pg.fill("#oDate", args.real_dry_run)
                pg.fill("#oToken", load_settings().ops_token)
                pg.click("#oDry")
                pg.wait_for_function("!document.querySelector('#opsJob .state.loading')", timeout=300000)
                assert pg.input_value("#oToken") == ""
                pg.wait_for_selector("#opsRuns tbody tr")
                pg.wait_for_timeout(800)
            pg.add_style_tag(content=REDACT_CSS + " #opsJob pre { filter: blur(6px); }")
            shot(pg, "11_real_ops_status_1440.png", "/#tab=ops", "REAL_PRIVATE", "1440x900", "REAL_PRIVATE",
                 redaction="none needed (counts, dates, statuses only); JSON detail blurred",
                 note=f"UI dry run {args.real_dry_run} executed just before capture" if args.real_dry_run else "")
            pg.click("#opsRuns tbody tr >> nth=0")
            pg.wait_for_selector("#opsRunDetail h3")
            pg.locator("#opsRunDetail").scroll_into_view_if_needed()
            shot(pg, "12_real_ops_run_detail_1440.png", "/#tab=ops (run detail)", "REAL_PRIVATE", "1440x900", "REAL_PRIVATE",
                 redaction="none needed (per-ticker outcome only)", full=False)
            pg = page_at(args.real, 390, 844, "#tab=ops&ds=1")
            pg.wait_for_selector("#opsRuns tbody tr")
            shot(pg, "13_real_ops_390.png", "/#tab=ops", "REAL_PRIVATE", "390x844", "REAL_PRIVATE", redaction="none needed")
        b.close()
    (OUT / "screens_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(manifest)} screenshots -> {OUT}")
    for m in manifest:
        print(m["file"], m["data_mode"], m["viewport"], m["captured_at"], m["redaction"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
