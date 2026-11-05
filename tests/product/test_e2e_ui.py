"""E2E UI: start the real server (uvicorn) and drive the installed Microsoft Edge (Playwright, headless).
Screenshots are taken after rendering and saved to tests/product_evidence/screenshots/ (synthetic demo and the
integration-test fixture only; real-data screenshots are produced separately into the private evidence folder)."""
import os
import subprocess
import sys
import time

import httpx
import pytest

from conftest import ROOT

pytestmark = [pytest.mark.e2e, pytest.mark.integration]
SHOTS = ROOT / "tests" / "product_evidence" / "screenshots"
TOKEN = "t" * 40


def start_server(port: int, env_extra: dict) -> subprocess.Popen:
    env = {**os.environ, "MARKETLAB_PORT": str(port), "MARKETLAB_OPS_TOKEN": TOKEN, "MARKETLAB_PROVIDER_PYTHON": "",
           "MARKETLAB_LOG_DIR": str(ROOT / "var" / "test_logs"), **env_extra}
    proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "marketlab_app.cli", "serve", "--port", str(port)], cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            if httpx.get(f"http://127.0.0.1:{port}/api/health", timeout=1).status_code == 200:
                return proc
        except httpx.HTTPError:
            pass
        time.sleep(0.25)
    proc.kill()
    raise RuntimeError("server did not start")


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="msedge", headless=True)
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"Microsoft Edge not available for Playwright: {exc}")
        yield b
        b.close()


def no_nan(page):
    text = page.inner_text("body")
    assert "NaN" not in text and "undefined" not in text, "NaN/undefined rendered"


def tab(page, name):
    page.click(f'.tabs button[data-tab="{name}"]')


def test_demo_dashboard_end_to_end(require_sql, browser):
    SHOTS.mkdir(parents=True, exist_ok=True)
    srv = start_server(8765, {"MARKETLAB_MODE": "DEMO_OFFLINE", "MARKETLAB_SQL_DATABASE": "MarketLabVN30_Demo"})
    try:
        page = browser.new_context(bypass_csp=True, viewport={"width": 1366, "height": 900}).new_page()  # CSP blocks Playwright's eval-based waits; CSP header itself is asserted in test_api
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto("http://127.0.0.1:8765/")
        page.wait_for_function("document.getElementById('modeBadge').textContent.includes('DEMO_OFFLINE')")
        page.wait_for_selector("#overviewCards .card >> nth=7")
        page.wait_for_selector("#latestTable tbody tr >> nth=7")
        assert "SYNTHETIC_DEMO_V1" in page.inner_text("#overviewCards")
        assert "256" in page.inner_text("#overviewCards")        # eligible predictions, same as 10_preflight_live.sql
        no_nan(page)
        page.screenshot(path=str(SHOTS / "01_overview_demo.png"), full_page=True)

        tab(page, "market")
        page.wait_for_selector("#chart svg path.line")
        page.fill("#mTicker", "DEMO03")
        page.click("#marketForm button[type=submit]")
        page.wait_for_function("document.getElementById('chartTitle').textContent.startsWith('DEMO03')")
        page.wait_for_selector("#priceTable tbody tr")
        assert page.locator("#priceTable tbody tr").count() == 35
        box = page.locator("#chart svg").bounding_box()
        page.mouse.move(box["x"] + box["width"] * 0.6, box["y"] + 120)
        page.wait_for_selector("#tooltip:not([hidden])")
        assert "DEMO03" in page.inner_text("#tooltip") and "Đơn vị" in page.inner_text("#tooltip")
        no_nan(page)
        page.screenshot(path=str(SHOTS / "02_market_explorer_demo.png"), full_page=True)
        page.click("#priceTable th:has-text('Close')")
        page.wait_for_selector("#priceTable th:has-text('▼')")

        tab(page, "forecast")
        page.wait_for_selector("#runTable tbody tr >> nth=1")
        page.wait_for_selector("#predTable tbody tr")
        assert "%" in page.inner_text("#runTable") and "Chưa cấu hình mô hình tạo dự báo mới" in page.inner_text("#inferenceNotice")
        page.select_option("#fStatus", "pending")
        page.click("#fApply")
        page.wait_for_function("document.querySelectorAll('#predTable tbody tr').length === 1")
        no_nan(page)
        page.screenshot(path=str(SHOTS / "03_forecast_analysis_demo.png"), full_page=True)

        tab(page, "compare")
        page.wait_for_selector("#compareRuns input >> nth=1")
        page.click("#compareForm button[type=submit]")
        page.wait_for_selector("#compareResult tbody tr >> nth=1")
        assert page.inner_text("#compareResult").count("128") >= 2
        page.screenshot(path=str(SHOTS / "04_model_comparison_demo.png"), full_page=True)

        tab(page, "ops")
        page.wait_for_selector("#calendarCheck tbody tr")
        assert page.is_disabled("#oSync") and "DEMO_OFFLINE" in page.inner_text("#opsJob")
        no_nan(page)
        page.screenshot(path=str(SHOTS / "05_data_operations_demo.png"), full_page=True)

        page.set_viewport_size({"width": 420, "height": 900})   # responsive layout
        tab(page, "overview")
        page.screenshot(path=str(SHOTS / "06_overview_mobile_demo.png"), full_page=True)
        assert errors == [], errors
    finally:
        srv.terminate()


def test_real_mode_ops_errors_are_visible(it_env, browser):
    """REAL_PRIVATE on the integration-test fixture: wrong token and missing provider are shown, nothing written."""
    s = it_env["settings"]
    srv = start_server(8766, {"MARKETLAB_MODE": "REAL_PRIVATE", "MARKETLAB_SQL_DATABASE": it_env["db"],
                              "MARKETLAB_OPS_DATABASE": it_env["ops_db"]})
    try:
        page = browser.new_context(bypass_csp=True, viewport={"width": 1366, "height": 900}).new_page()  # CSP blocks Playwright's eval-based waits; CSP header itself is asserted in test_api
        page.on("dialog", lambda d: d.accept())
        page.goto("http://127.0.0.1:8766/")
        page.wait_for_function("document.getElementById('modeBadge').textContent.includes('REAL_PRIVATE')")
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        tab(page, "ops")
        try:
            page.wait_for_selector("#calendarCheck tbody tr", timeout=10000)
        except Exception:
            raise AssertionError(f"ops tab: {page.inner_text('#tab-ops')[:800]} | js errors: {errs}")
        page.fill("#oDate", "2026-10-02")
        page.fill("#oToken", "w" * 40)
        page.click("#oDry")
        page.wait_for_selector("#opsJob .state.error")
        assert "INVALID_OPS_TOKEN" in page.inner_text("#opsJob")
        page.fill("#oToken", TOKEN)
        page.click("#oDry")
        page.wait_for_function("document.getElementById('opsJob').textContent.includes('PROVIDER_NOT_CONFIGURED')", timeout=30000)
        assert "FAILED" in page.inner_text("#opsJob")
        page.wait_for_selector("#opsRuns tbody tr")
        page.click("#opsRuns tbody tr >> nth=0")
        page.wait_for_selector("#opsRunDetail h3")
        assert page.input_value("#oToken") == TOKEN and "t" * 40 not in page.content().replace(f'value="{TOKEN}"', "")
        no_nan(page)
        page.screenshot(path=str(SHOTS / "07_ops_missing_provider_it_fixture.png"), full_page=True)
    finally:
        srv.terminate()
