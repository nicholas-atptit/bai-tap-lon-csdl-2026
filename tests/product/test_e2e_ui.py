"""E2E UI: start the real server (uvicorn) and drive the installed Microsoft Edge (Playwright, headless).
Covers navigation (mouse + keyboard), URL state across reload, filters/clear/validation, sort/pagination, chart tooltip,
retry after an injected API failure, Swagger rendering, 4 viewports without page overflow, DEMO write lock-out,
REAL wrong token / missing provider / token cleared. Screenshots of the synthetic demo and the integration-test fixture
are saved to tests/product_evidence/screenshots/ (never real market records)."""
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
VIEWPORTS = {"1440x900": (1440, 900), "1366x768": (1366, 768), "768x1024": (768, 1024), "390x844": (390, 844)}


def start_server(port: int, env_extra: dict) -> subprocess.Popen:
    env = {**os.environ, "MARKETLAB_PORT": str(port), "MARKETLAB_OPS_TOKEN": TOKEN, "MARKETLAB_PROVIDER_PYTHON": "",
           "MARKETLAB_LOG_DIR": str(ROOT / "var" / "test_logs"), "MARKETLAB_PEERS": "", **env_extra}
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


@pytest.fixture(scope="module")
def demo_server(require_sql):
    srv = start_server(8765, {"MARKETLAB_MODE": "DEMO_OFFLINE", "MARKETLAB_SQL_DATABASE": "MarketLabVN30_Demo"})
    yield "http://127.0.0.1:8765"
    srv.terminate()


def new_page(browser, w=1366, h=900):
    # CSP blocks Playwright's eval-based waits; the CSP header itself is asserted in test_api.
    page = browser.new_context(bypass_csp=True, viewport={"width": w, "height": h}).new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.on("console", lambda m: page.errors.append(m.text) if m.type == "error" else None)
    return page


def no_nan(page):
    text = page.inner_text("body")
    assert "NaN" not in text and "undefined" not in text, "NaN/undefined rendered"


def tab(page, name):
    page.click(f'.tabs [data-tab="{name}"]')


def test_demo_dashboard_end_to_end(demo_server, browser):
    SHOTS.mkdir(parents=True, exist_ok=True)
    page = new_page(browser)
    page.goto(demo_server + "/")
    page.wait_for_function("document.getElementById('modeBadge').textContent.includes('DEMO_OFFLINE')")
    page.wait_for_selector("#overviewCards .card >> nth=4")
    page.wait_for_selector("#latestTable tbody tr >> nth=7")
    assert "SYNTHETIC_DEMO_V1" in page.inner_text("#provenance")
    assert "256" in page.inner_text("#overviewCards")        # eligible predictions, same as 10_preflight_live.sql
    assert "Mô phỏng cố định" in page.inner_text("#overviewCards")
    no_nan(page)

    tab(page, "market")
    page.wait_for_selector("#chart svg path.line")
    page.fill("#mTicker", "DEMO03")
    page.click("#marketForm button[type=submit]")
    page.wait_for_function("document.getElementById('chartTitle').textContent.startsWith('DEMO03 · SYNTHETIC_DEMO_V1')")
    page.wait_for_selector("#priceTable tbody tr")
    assert page.locator("#priceTable tbody tr").count() == 35
    box = page.locator("#chart svg").bounding_box()
    page.mouse.move(box["x"] + box["width"] * 0.6, box["y"] + 120)
    page.wait_for_selector("#tooltip:not([hidden])")
    tip = page.inner_text("#tooltip")
    assert "DEMO03" in tip and "SOURCE_CLOSE" in tip and "SYNTHETIC_DEMO_V1" in tip
    # sort by Close: first click descending, second ascending; verify the rendered order
    page.click("#priceTable th:has-text('Close') button")
    page.wait_for_selector("#priceTable th[aria-sort='descending']:has-text('Close')")
    page.click("#priceTable th:has-text('Close') button")
    page.wait_for_selector("#priceTable th[aria-sort='ascending']:has-text('Close')")
    closes = [float(x.replace(".", "").replace(",", ".")) for x in page.locator("#priceTable tbody tr td:nth-child(6)").all_inner_texts()]
    assert closes == sorted(closes)
    # filter changes the data, clear restores it
    page.fill("#mFrom", "2025-02-01")
    page.click("#marketForm button[type=submit]")
    page.wait_for_function("document.querySelector('#pricePager span') && document.querySelector('#pricePager span').textContent.endsWith('/ 13')")
    page.click("#mClear")
    page.wait_for_function("document.querySelector('#pricePager span').textContent.endsWith('/ 35')")
    assert page.input_value("#mFrom") == ""
    # client-side validation: no request for an invalid ticker
    page.fill("#mTicker", "A;B")
    page.click("#marketForm button[type=submit]")
    assert "chữ cái" in page.inner_text("#marketMsg")
    page.fill("#mTicker", "DEMO03")
    page.click("#marketForm button[type=submit]")
    page.wait_for_function("document.getElementById('marketMsg').textContent === ''")
    no_nan(page)

    tab(page, "forecast")
    page.wait_for_selector("#runTable tbody tr >> nth=1")
    page.wait_for_selector("#predTable tbody tr")
    assert "as_of" in page.inner_text("#perfCaption") and "SYNTHETIC_DEMO_V1" in page.inner_text("#perfCaption")
    assert "%" in page.inner_text("#runTable") and "Chưa cấu hình mô hình tạo dự báo mới" in page.inner_text("#inferenceNotice")
    page.select_option("#fStatus", "pending")
    page.click("#predForm button[type=submit]")
    page.wait_for_function("document.querySelectorAll('#predTable tbody tr').length === 1")
    assert "— (chưa chấm)" in page.inner_text("#predTable")
    page.click("#fClear")
    page.wait_for_function("document.querySelectorAll('#predTable tbody tr').length === 50")
    page.click("#predPager button:has-text('Sau')")
    page.wait_for_function("document.querySelector('#predPager span').textContent.startsWith('51–100')")

    tab(page, "compare")
    page.wait_for_selector("#compareRuns input >> nth=1")
    assert "usp_CompareModels" in page.inner_text("#compareResult")    # empty state before the first run
    page.click("#compareForm button[type=submit]")
    page.wait_for_selector("#compareResult tbody tr >> nth=1")
    assert page.inner_text("#compareResult").count("128") >= 2 and "quan sát chung" in page.inner_text("#compareResult")

    tab(page, "ops")
    page.wait_for_selector("#calendarCheck tbody tr")
    assert page.is_disabled("#oSync") and page.is_disabled("#oDry") and "DEMO_OFFLINE" in page.inner_text("#opsScope")
    no_nan(page)
    assert page.errors == [], page.errors


def test_url_state_survives_reload_and_keyboard_tabs(demo_server, browser):
    page = new_page(browser)
    page.goto(demo_server + "/")
    page.wait_for_selector("#latestTable tbody tr")
    page.focus('.tabs [data-tab="overview"]')
    page.keyboard.press("ArrowRight")
    page.wait_for_selector('.tabs [data-tab="market"][aria-selected="true"]')
    assert page.evaluate("document.activeElement.dataset.tab") == "market"
    page.wait_for_selector("#chart svg path.line")
    page.fill("#mTicker", "DEMO05")
    page.fill("#mFrom", "2025-01-15")
    page.click("#marketForm button[type=submit]")
    page.wait_for_function("document.getElementById('chartTitle').textContent.startsWith('DEMO05')")
    assert "t=DEMO05" in page.url and "tab=market" in page.url
    page.reload()
    page.wait_for_function("document.getElementById('chartTitle').textContent.startsWith('DEMO05')")
    assert page.input_value("#mFrom") == "2025-01-15"
    assert page.get_attribute('.tabs [data-tab="market"]', "aria-selected") == "true"
    page.focus('.tabs [data-tab="market"]')
    page.keyboard.press("End")
    page.wait_for_selector('.tabs [data-tab="ops"][aria-selected="true"]')
    # a deep link pasted into the same tab (hash-only navigation) is applied
    page.goto(demo_server + "/#tab=market&ds=1&t=DEMO07&f=2025-02-01")
    page.wait_for_function("document.getElementById('chartTitle').textContent.startsWith('DEMO07')")
    assert page.input_value("#mFrom") == "2025-02-01"


def test_retry_after_injected_api_failure(demo_server, browser):
    page = new_page(browser)
    state = {"fail": True}

    def handler(route):
        if state["fail"]:
            state["fail"] = False
            return route.fulfill(status=503, content_type="application/json",
                                 body='{"error":{"code":"DB_UNAVAILABLE","message":"injected by test"}}')
        return route.continue_()
    page.route("**/api/prices/latest*", handler)
    page.goto(demo_server + "/")
    page.wait_for_selector("#latestTable .state.error")
    assert "DB_UNAVAILABLE" in page.inner_text("#latestTable") and "Thử lại" in page.inner_text("#latestTable")
    page.errors.clear()   # the injected 503 is logged by the browser console on purpose
    page.click("#latestTable button.retry")
    page.wait_for_selector("#latestTable tbody tr >> nth=7")


def test_swagger_renders_all_operations(demo_server, browser):
    page = new_page(browser, 1440, 900)
    page.goto(demo_server + "/api/docs")
    page.wait_for_selector(".opblock", timeout=15000)
    assert page.locator(".opblock").count() >= 18
    assert "Unable to render" not in page.inner_text("body")


@pytest.mark.parametrize("vp", list(VIEWPORTS))
def test_no_horizontal_overflow_any_viewport(demo_server, browser, vp):
    w, h = VIEWPORTS[vp]
    page = new_page(browser, w, h)
    page.goto(demo_server + "/")
    page.wait_for_selector("#latestTable tbody tr")
    for name in ("overview", "market", "forecast", "compare", "ops"):
        tab(page, name)
        page.wait_for_timeout(700)
        sw, cw = page.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
        assert sw <= cw + 1, f"{vp} {name}: page overflows horizontally ({sw} > {cw})"
        no_nan(page)
    assert page.errors == [], page.errors


def test_real_mode_ops_errors_are_visible(it_env, browser):
    """REAL_PRIVATE on the integration-test fixture: wrong token and missing provider are shown, nothing written,
    token field cleared after every request."""
    SHOTS.mkdir(parents=True, exist_ok=True)
    srv = start_server(8766, {"MARKETLAB_MODE": "REAL_PRIVATE", "MARKETLAB_SQL_DATABASE": it_env["db"],
                              "MARKETLAB_OPS_DATABASE": it_env["ops_db"]})
    try:
        page = new_page(browser)
        page.on("dialog", lambda d: d.accept())
        page.goto("http://127.0.0.1:8766/")
        page.wait_for_function("document.getElementById('modeBadge').textContent.includes('REAL_PRIVATE')")
        tab(page, "ops")
        try:
            page.wait_for_selector("#calendarCheck tbody tr", timeout=15000)
        except Exception as exc:  # noqa: BLE001 - surface the real UI state
            raise AssertionError(f"ops tab: {page.inner_text('#tab-ops')[:600]} | errors: {page.errors}") from exc
        assert "IT_FAKE_ADAPTER" in page.inner_text("#opsScope")
        page.fill("#oDate", "2026-10-02")
        page.fill("#oToken", "w" * 40)
        page.click("#oDry")
        page.wait_for_selector("#opsJob .state.error")
        assert "INVALID_OPS_TOKEN" in page.inner_text("#opsJob") and page.input_value("#oToken") == ""
        page.errors.clear()   # the 401 above is an expected browser console entry
        page.fill("#oToken", TOKEN)
        page.click("#oDry")
        page.wait_for_function("document.getElementById('opsJob').textContent.includes('PROVIDER_NOT_CONFIGURED')", timeout=30000)
        assert "FAILED" in page.inner_text("#opsJob") and page.input_value("#oToken") == ""
        assert TOKEN not in page.content()
        page.wait_for_selector("#opsRuns tbody tr")
        page.click("#opsRuns tbody tr >> nth=0")
        page.wait_for_selector("#opsRunDetail h3")
        page.select_option("#oStatus", "SUCCESS")
        page.wait_for_function("document.getElementById('opsRuns').textContent.includes('Không có lần chạy nào')")
        no_nan(page)
        page.screenshot(path=str(SHOTS / "it_fixture_ops_missing_provider.png"), full_page=True)
        assert page.errors == [], page.errors
    finally:
        srv.terminate()
