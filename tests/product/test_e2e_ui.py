"""E2E: start the real server-rendered web application (uvicorn) and drive the installed Microsoft Edge (Playwright).
Covers navigation links + keyboard, dataset picker, filters/clear/validation, sort/pagination, chart tooltip, refresh
stability (state in the URL), the browser never fetching data itself (no XHR/fetch), 4 viewports without page
overflow, DEMO write lock-out, REAL wrong token / CSRF form / confirmation / job page / missing provider."""
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
PAGES = ["/", "/market", "/forecast", "/compare", "/ops"]


def start_server(port: int, env_extra: dict) -> subprocess.Popen:
    env = {**os.environ, "MARKETLAB_PORT": str(port), "MARKETLAB_OPS_TOKEN": TOKEN, "MARKETLAB_PROVIDER_PYTHON": "",
           "MARKETLAB_LOG_DIR": str(ROOT / "var" / "test_logs"), "MARKETLAB_PEERS": "", **env_extra}
    proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "marketlab_app.cli", "serve", "--port", str(port)], cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            if httpx.get(f"http://127.0.0.1:{port}/health", timeout=1).status_code == 200:
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
    # the app's CSP is kept (no bypass): Playwright waits below use selectors, not eval strings
    page = browser.new_context(viewport={"width": w, "height": h}).new_page()
    page.errors, page.fetches = [], []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.on("console", lambda m: page.errors.append(m.text) if m.type == "error" else None)
    # only requests to the app origin count; the local antivirus (Kaspersky) injects its own XHR to *.kaspersky-labs.com
    page.on("request", lambda r: page.fetches.append(r.url)
            if r.resource_type in ("xhr", "fetch") and r.url.startswith(("http://127.0.0.1", "http://localhost")) else None)
    return page


def no_nan(page):
    t = page.inner_text("body")
    assert "NaN" not in t and "undefined" not in t, "NaN/undefined rendered"


def test_demo_journey_end_to_end(demo_server, browser):
    page = new_page(browser)
    page.goto(demo_server + "/")
    assert "DEMO_OFFLINE" in page.inner_text("#modeBadge")
    assert "256" in page.inner_text("[data-metric=eligible_predictions]") and "Mô phỏng cố định" in page.inner_text(".grid.cards")
    assert page.locator("#latestTable tbody tr").count() == 8
    no_nan(page)
    page.click('a[data-tab="market"]')
    page.wait_for_selector("#chart svg path.line")
    page.fill("#mTicker", "DEMO03")
    page.click("form.filters button[type=submit]")
    page.wait_for_selector("#chartTitle:has-text('DEMO03 · SYNTHETIC_DEMO_V1')")
    assert page.locator("#priceTable tbody tr").count() == 35 and "t=DEMO03" in page.url
    box = page.locator("#chart svg").bounding_box()
    page.mouse.move(box["x"] + box["width"] * 0.6, box["y"] + 120)
    page.wait_for_selector("#tooltip:not([hidden])")
    tip = page.inner_text("#tooltip")
    assert "DEMO03" in tip and "SOURCE_CLOSE" in tip and "SYNTHETIC_DEMO_V1" in tip
    page.click("#priceTable th:has-text('Close') a")
    page.wait_for_selector("#priceTable th[aria-sort='descending']:has-text('Close')")
    page.click("#priceTable th:has-text('Close') a")
    page.wait_for_selector("#priceTable th[aria-sort='ascending']:has-text('Close')")
    closes = [float(x.replace(".", "").replace(",", ".")) for x in page.locator("#priceTable tbody tr td:nth-child(6)").all_inner_texts()]
    assert closes == sorted(closes)
    page.fill("#mFrom", "2025-02-01")
    page.click("form.filters button[type=submit]")
    page.wait_for_selector(".pager span:has-text('/ 13')")
    page.reload()                                          # refresh keeps the filter (state in the URL)
    page.wait_for_selector(".pager span:has-text('/ 13')")
    assert page.input_value("#mFrom") == "2025-02-01"
    page.click("#mClear")
    page.wait_for_selector(".pager span:has-text('/ 35')")
    page.fill("#mTicker", "A;B")
    page.click("form.filters button[type=submit]")
    page.wait_for_selector(".state.error:has-text('Mã chỉ gồm')")
    page.errors.clear()   # the 422 validation page is logged by the browser console on purpose
    no_nan(page)

    page.click('a[data-tab="forecast"]')
    page.wait_for_selector("#runTable tbody tr")
    assert "Chưa cấu hình mô hình tạo dự báo mới" in page.inner_text(".notice") and "as_of" in page.inner_text("#perfCaption")
    page.select_option("#fStatus", "pending")
    page.click("form.filters.compact button[type=submit]")
    page.wait_for_selector("#predTable tbody tr")
    assert page.locator("#predTable tbody tr").count() == 1 and "— (chưa chấm)" in page.inner_text("#predTable")
    page.click("#fClear")
    page.wait_for_selector(".pager span:has-text('1–50 / 129')")
    page.click(".pager a[rel=next]")
    page.wait_for_selector(".pager span:has-text('51–100 / 129')")

    page.click('a[data-tab="compare"]')
    page.wait_for_selector("text=Chọn run, khoảng ngày gốc")
    page.fill("#cAsOf", "2026-07-01")
    page.click("form.filters button[type=submit]")
    page.wait_for_selector("#compareTable tbody tr >> nth=1")
    assert page.inner_text("#compareTable").count("128") >= 2 and "quan sát chung" in page.inner_text("main")

    page.click('a[data-tab="ops"]')
    page.wait_for_selector("#calendarCheck tbody tr")
    assert page.is_disabled("#oSync") and page.is_disabled("#oDry") and "DEMO_OFFLINE" in page.inner_text("#opsScope")
    no_nan(page)
    assert page.errors == [], page.errors
    assert page.fetches == [], f"browser fetched data itself: {page.fetches}"


def test_keyboard_navigation_and_dataset_picker(demo_server, browser):
    page = new_page(browser)
    page.goto(demo_server + "/")
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.className") == "skip-link"
    page.focus('a[data-tab="forecast"]')
    page.keyboard.press("Enter")
    page.wait_for_selector('a[data-tab="forecast"][aria-current="page"]')
    page.select_option("#datasetSelect", "1")           # auto-submits the GET form, stays on the same page
    page.wait_for_selector('a[data-tab="forecast"][aria-current="page"]')
    assert "ds=1" in page.url
    assert page.errors == []


@pytest.mark.parametrize("vp", list(VIEWPORTS))
def test_no_horizontal_overflow_any_viewport(demo_server, browser, vp):
    w, h = VIEWPORTS[vp]
    page = new_page(browser, w, h)
    for p in PAGES:
        page.goto(demo_server + p + ("?t=DEMO03" if p == "/market" else ""))
        sw, cw = page.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
        assert sw <= cw + 1, f"{vp} {p}: page overflows horizontally ({sw} > {cw})"
        no_nan(page)
    assert page.errors == [], page.errors


def test_real_mode_ops_form_and_job_page(it_env, browser):
    """REAL_PRIVATE on the integration-test fixture: wrong token, missing confirmation, CSRF-protected form,
    job page that refreshes itself, missing provider reported, token never echoed."""
    SHOTS.mkdir(parents=True, exist_ok=True)
    srv = start_server(8766, {"MARKETLAB_MODE": "REAL_PRIVATE", "MARKETLAB_SQL_DATABASE": it_env["db"],
                              "MARKETLAB_OPS_DATABASE": it_env["ops_db"]})
    try:
        page = new_page(browser)
        page.on("dialog", lambda d: d.accept())
        page.goto("http://127.0.0.1:8766/ops?ds=1")
        assert "REAL_PRIVATE" in page.inner_text("#modeBadge") and "IT_FAKE_ADAPTER" in page.inner_text("#opsScope")
        page.fill("#oDate", "2026-10-02")
        page.fill("#oToken", "w" * 40)
        page.click("#oDry")
        page.wait_for_selector("#actionError:has-text('INVALID_OPS_TOKEN')")
        assert page.input_value("#oToken") == ""
        page.errors.clear()   # the 401 page load is logged by the browser on purpose
        page.fill("#oDate", "2026-10-02")
        page.fill("#oToken", TOKEN)
        page.click("#oDry")
        page.wait_for_selector("#jobState[data-status]", timeout=30000)
        assert page.get_attribute("#jobState", "data-status") == "FAILED" and "PROVIDER_NOT_CONFIGURED" in page.inner_text("main")
        assert TOKEN not in page.content()
        page.click("a.btn.primary")
        page.wait_for_selector("#runDetail h3")
        page.select_option("#oStatus", "SUCCESS")
        page.click("form.inline-group button[type=submit]")
        page.wait_for_selector("text=Không có lần chạy nào khớp bộ lọc")
        no_nan(page)
        page.screenshot(path=str(SHOTS / "it_fixture_ops_missing_provider.png"), full_page=True)
        assert page.errors == [], page.errors
        assert page.fetches == []
    finally:
        srv.terminate()
