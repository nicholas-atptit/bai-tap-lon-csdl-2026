"""Capture the OFFICIAL screenshots of the server-rendered web application from the RUNNING instances (Edge) + manifest.

uv run python scripts/capture_final_screenshots.py --demo http://127.0.0.1:8000 --real http://127.0.0.1:8001 --real-dry-run 2026-11-05
Output: report/final/assets/screens/*.png + screens_manifest.json (file, route, data mode, viewport, captured time,
classification, redaction). Previous screenshots in that folder are replaced (they showed the retired REST/Swagger UI).
REAL screenshots keep only counts/dates/statuses: price/volume cells and the price chart are blurred before capture
(third-party price records are not redistributed; see LICENSE.md). The optional REAL dry run goes through the real
server-side form (CSRF + token + confirmation dialog): validated in SQL Server and rolled back, no business row written,
one DRY_RUN_OK row (TriggerKind WEB) added to the ops log. The token is read from .env and never printed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from marketlab_app.config import load_settings  # noqa: E402

OUT = ROOT / "report" / "final" / "assets" / "screens"
REDACT_CSS = """
#latestTable td.num, #priceTable td.num, #chart svg, .tooltip { filter: blur(6px) !important; }
#chart { position: relative; }
#chart::after { content: "Biểu đồ giá thật đã được che trong ảnh báo cáo (dữ liệu bên thứ ba, quyền phân phối UNKNOWN)"; position: absolute;
  inset: 40% 10% auto 10%; text-align: center; background: #fff; border: 1px solid #ccc; padding: 8px; font-size: 13px; }
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", default="http://127.0.0.1:8000")
    ap.add_argument("--real", default="http://127.0.0.1:8001")
    ap.add_argument("--real-dry-run")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.png"):
        old.unlink()
    manifest = []
    from playwright.sync_api import sync_playwright

    def shot(page, name, route, mode, vp, classification, redaction="none", full=True, note=""):
        page.screenshot(path=str(OUT / name), full_page=full)
        manifest.append({"file": f"report/final/assets/screens/{name}", "route": route, "data_mode": mode, "viewport": vp,
                         "captured_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
                         "classification": classification, "redaction": redaction, "note": note})

    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge", headless=True)

        def open_(base, route, w=1440, h=900, redact=False):
            # bypass_csp only where the redaction stylesheet must be injected (REAL screenshots)
            pg = b.new_context(viewport={"width": w, "height": h}, bypass_csp=redact).new_page()
            pg.goto(base + route)
            return pg

        d = args.demo
        pg = open_(d, "/?ds=1")
        shot(pg, "01_demo_overview_1440.png", "/?ds=1", "DEMO_OFFLINE", "1440x900", "SYNTHETIC")
        pg = open_(d, "/market?ds=1&t=DEMO03")
        pg.wait_for_selector("#chart svg path.line")
        box = pg.locator("#chart svg").bounding_box()
        pg.mouse.move(box["x"] + box["width"] * 0.55, box["y"] + 130)
        pg.wait_for_selector("#tooltip:not([hidden])")
        shot(pg, "02_demo_market_chart_1440.png", "/market?ds=1&t=DEMO03", "DEMO_OFFLINE", "1440x900", "SYNTHETIC", full=False,
             note="chart + tooltip, viewport crop")
        pg = open_(d, "/market?ds=1&t=DEMO03&f=2025-02-01&to=2025-02-14&sort=close&order=asc")
        shot(pg, "03_demo_market_filtered_sorted_1440.png", "/market?t=DEMO03&f=2025-02-01&to=2025-02-14&sort=close&order=asc",
             "DEMO_OFFLINE", "1440x900", "SYNTHETIC")
        pg = open_(d, "/forecast?ds=1&run=1&as_of=2026-07-01")
        shot(pg, "04_demo_forecast_performance_1440.png", "/forecast?run=1&as_of=2026-07-01", "DEMO_OFFLINE", "1440x900", "SYNTHETIC",
             full=False, note="viewport crop (runs + first predictions)")
        pg = open_(d, "/compare?ds=1&runs=1&runs=2&f=2025-01-02&to=2025-02-17&as_of=2026-07-01")
        shot(pg, "05_demo_model_comparison_1440.png", "/compare?runs=1&runs=2&f=2025-01-02&to=2025-02-17&as_of=2026-07-01",
             "DEMO_OFFLINE", "1440x900", "SYNTHETIC")
        pg = open_(d, "/ops?ds=1")
        shot(pg, "06_demo_ops_disabled_1440.png", "/ops?ds=1", "DEMO_OFFLINE", "1440x900", "SYNTHETIC", full=False,
             note="EOD form disabled in DEMO_OFFLINE")
        pg = open_(d, "/market?ds=1&t=DEMO01&f=2025-02-10&to=2025-01-01")
        shot(pg, "07_demo_validation_error_1440.png", "/market?t=DEMO01&f=2025-02-10&to=2025-01-01 (HTTP 422)", "DEMO_OFFLINE",
             "1440x900", "SYNTHETIC", full=False, note="server-side validation message")
        for vp, (w, h), route, tag in (("768x1024", (768, 1024), "/market?ds=1&t=DEMO03", "market"),
                                        ("390x844", (390, 844), "/?ds=1", "overview"),
                                        ("390x844", (390, 844), "/market?ds=1&t=DEMO03", "market")):
            pg = open_(d, route, w, h)
            pg.wait_for_timeout(600)
            shot(pg, f"08_demo_{tag}_{vp}.png", route, "DEMO_OFFLINE", vp, "SYNTHETIC")
        pg = open_(d, "/api/docs")
        shot(pg, "09_api_docs_removed_404.png", "/api/docs (HTTP 404)", "DEMO_OFFLINE", "1440x900", "PROOF", full=False,
             note="Swagger/OpenAPI removed: the route returns the app's 404 page")

        if args.real:
            r = args.real
            pg = open_(r, "/?ds=1", redact=True)
            pg.add_style_tag(content=REDACT_CSS)
            shot(pg, "10_real_overview_redacted_1440.png", "/?ds=1", "REAL_PRIVATE", "1440x900", "REAL_PRIVATE",
                 redaction="price/volume cells blurred")
            pg = open_(r, "/market?ds=1&t=ACB", redact=True)
            pg.add_style_tag(content=REDACT_CSS)
            shot(pg, "11_real_market_redacted_1440.png", "/market?ds=1&t=ACB", "REAL_PRIVATE", "1440x900", "REAL_PRIVATE",
                 redaction="chart and price/volume cells blurred", full=False)
            if args.real_dry_run:
                pg = open_(r, "/ops?ds=1")
                pg.on("dialog", lambda dlg: dlg.accept())
                pg.fill("#oDate", args.real_dry_run)
                pg.fill("#oToken", load_settings().ops_token)
                pg.click("#oDry")
                pg.wait_for_selector("#jobState[data-status]", timeout=300000)
                shot(pg, "12_real_eod_job_result_1440.png", "/ops/jobs/<id> (server-side form result)", "REAL_PRIVATE", "1440x900",
                     "REAL_PRIVATE", redaction="none needed (counts and statuses only)", full=False,
                     note=f"UI dry run of session {args.real_dry_run} through the CSRF-protected form")
                pg.click("a.btn.primary")
                pg.wait_for_selector("#runDetail h3")
                pg.locator("#runDetail").scroll_into_view_if_needed()
                shot(pg, "13_real_ops_run_detail_1440.png", "/ops?run=<id>#runDetail", "REAL_PRIVATE", "1440x900", "REAL_PRIVATE",
                     redaction="none needed (per-ticker outcome only)", full=False)
            pg = open_(r, "/ops?ds=1")
            shot(pg, "14_real_ops_status_1440.png", "/ops?ds=1", "REAL_PRIVATE", "1440x900", "REAL_PRIVATE",
                 redaction="none needed (counts, dates, statuses only)")
            pg = open_(r, "/ops?ds=1", 390, 844)
            shot(pg, "15_real_ops_390.png", "/ops?ds=1", "REAL_PRIVATE", "390x844", "REAL_PRIVATE", redaction="none needed", full=False)
        b.close()
    (OUT / "screens_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(manifest)} screenshots -> {OUT}")
    for m in manifest:
        print(m["file"].split("/")[-1], m["data_mode"], m["viewport"], m["captured_at"], m["redaction"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
