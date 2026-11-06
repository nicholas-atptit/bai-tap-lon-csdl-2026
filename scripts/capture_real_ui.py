"""Drive the RUNNING REAL_PRIVATE dashboard with Microsoft Edge and save screenshots to the PRIVATE evidence folder
(gitignored: real market records must not be published). Optionally performs a UI dry run (real provider, rolled back).

uv run python scripts/capture_real_ui.py --base-url http://127.0.0.1:8001 --dry-run-date 2026-11-05
The ops token is read from .env (MARKETLAB_OPS_TOKEN) and never printed.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from marketlab_app.config import load_settings  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8001")
    ap.add_argument("--ticker", default="ACB")
    ap.add_argument("--dry-run-date")
    ap.add_argument("--out", type=Path, default=ROOT / "tests" / "product_evidence" / "private" / "screenshots")
    args = ap.parse_args()
    token = load_settings().ops_token
    args.out.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge", headless=True)
        page = b.new_context(bypass_csp=True, viewport={"width": 1366, "height": 900}).new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("dialog", lambda d: d.accept())
        page.goto(args.base_url + "/")
        page.wait_for_function("document.getElementById('modeBadge').textContent.includes('REAL_PRIVATE')")
        page.wait_for_selector("#latestTable tbody tr")
        page.screenshot(path=str(args.out / "real_01_overview.png"), full_page=True)
        page.click('.tabs button[data-tab="market"]')
        page.wait_for_selector("#chart svg path.line")
        page.fill("#mTicker", args.ticker)
        page.click("#marketForm button[type=submit]")
        page.wait_for_function(f"document.getElementById('chartTitle').textContent.startsWith('{args.ticker}')")
        box = page.locator("#chart svg").bounding_box()
        page.mouse.move(box["x"] + box["width"] * 0.8, box["y"] + 120)
        page.wait_for_selector("#tooltip:not([hidden])")
        page.screenshot(path=str(args.out / "real_02_market.png"), full_page=True)
        page.click('.tabs button[data-tab="forecast"]')
        page.wait_for_selector("#runTable .state, #runTable table")
        page.screenshot(path=str(args.out / "real_03_forecast.png"), full_page=True)
        page.click('.tabs button[data-tab="ops"]')
        page.wait_for_selector("#opsRuns tbody tr")
        if args.dry_run_date:
            page.fill("#oDate", args.dry_run_date)
            page.fill("#oToken", token)
            page.click("#oDry")
            page.wait_for_function("!document.querySelector('#opsJob .state.loading')", timeout=300000)
            print("UI dry run result:", page.inner_text("#opsJob").splitlines()[0][:200])
            page.fill("#oToken", "")
        page.screenshot(path=str(args.out / "real_04_operations.png"), full_page=True)
        text = page.inner_text("body")
        b.close()
    print("screenshots:", args.out, "| js errors:", errors, "| NaN in page:", "NaN" in text)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
