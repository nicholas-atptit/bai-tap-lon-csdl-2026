"""Server-side web application tests (replace the former REST API tests).

Pages are rendered by the Python server; tests read the HTML (data-metric / data-v attributes) and compare with
parameterized SQL on the same database. Covers: no API/Swagger surface, input validation, Host/Origin/CSP,
CSRF + ops token + lockout + confirmation on the only write form, EOD job flow, DB downtime and mode guard.
Demo DB is only read; writes go to an isolated MarketLabVN30_IT_* database with the test-only FakeProvider."""
import datetime as dt
import html
import re
import time

import pytest
from fastapi.testclient import TestClient

from conftest import CLOCK, fake_series, it_settings
from marketlab_app.config import load_settings
from marketlab_app.db import connect, query
from marketlab_app.eod.providers import FakeProvider
from marketlab_app.eod.service import EodService
from marketlab_app.web_app import create_app, fmt_num

pytestmark = pytest.mark.integration
TOKEN = "t" * 40


@pytest.fixture(scope="module")
def demo(require_sql):
    s = load_settings(env={"MARKETLAB_MODE": "DEMO_OFFLINE", "MARKETLAB_SQL_DATABASE": "MarketLabVN30_Demo", "MARKETLAB_OPS_TOKEN": TOKEN})
    return s, TestClient(create_app(s))


@pytest.fixture(scope="module")
def real(it_env):
    s = it_env["settings"]
    app = create_app(s, service_factory=lambda: EodService(s, provider=FakeProvider(fake_series()), trigger="WEB", clock=CLOCK))
    return s, TestClient(app)


def text(r) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", r.text)))


def metric(r, name: str) -> str:
    m = re.search(rf'data-metric="{name}"><div class="k">[^<]*</div><div class="v">([^<]*)</div>', r.text)
    assert m, name
    return html.unescape(m.group(1))


def data_v(r, table_id: str) -> list[list[str]]:
    body = re.search(rf'<table id="{table_id}">.*?<tbody>(.*?)</tbody>', r.text, re.S).group(1)
    return [re.findall(r'data-v="([^"]*)"', row) for row in re.findall(r"<tr.*?</tr>", body, re.S)]


def csrf_of(r) -> str:
    return re.search(r'name="csrf" value="([^"]+)"', r.text).group(1)


# ---- surface ---------------------------------------------------------------------------------------------------
def test_pages_render_and_no_api_or_swagger_surface(demo):
    _, c = demo
    for p in ("/", "/market", "/forecast", "/compare", "/ops"):
        r = c.get(p)
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/html"), p
        assert "DEMO_OFFLINE" in r.text and "NaN" not in text(r) and "None" not in text(r)
    for p in ("/api/docs", "/api/openapi.json", "/api/health", "/api/prices", "/docs", "/openapi.json", "/redoc"):
        assert c.get(p).status_code == 404, p
    assert c.get("/health").text.startswith("ok DEMO_OFFLINE")
    assert "/static/enhance.js" in c.get("/").text and c.get("/static/enhance.js").status_code == 200


@pytest.mark.parametrize("url,status,needle", [
    ("/market?t=A;B", 422, "Mã chỉ gồm"),
    ("/market?t=ZZZ", 422, "không thuộc dataset"),
    ("/market?t=DEMO01&f=2025-02-10&to=2025-01-01", 422, "Từ ngày phải nhỏ hơn"),
    ("/market?t=DEMO01&f=2025-13-01", 422, "YYYY-MM-DD"),
    ("/market?t=DEMO01&sort=price;drop", 422, "sắp xếp không hợp lệ"),
    ("/market?t=DEMO01&page=0", 422, "INVALID_NUMBER"),
    ("/forecast?run=99", 404, "RUN_NOT_FOUND"),
    ("/forecast?as_of=2026-13-01", 422, "YYYY-MM-DD"),
    ("/forecast?run=1&status=bogus", 422, "Trạng thái không hợp lệ"),
    ("/compare?runs=1&f=2025-01-02&to=2025-02-17&as_of=2026-07-01", 422, "2 đến 8"),
    ("/compare?runs=1&runs=1&f=2025-01-02&to=2025-02-17&as_of=2026-07-01", 422, "trùng"),
    ("/compare?runs=1&runs=77&f=2025-01-02&to=2025-02-17&as_of=2026-07-01", 422, "RUNS_NOT_FOUND_OR_COUNT"),
    ("/compare?runs=1&runs=2&f=2025-01-02&to=2025-02-17&as_of=2025-01-03", 422, "NO_COMMON_MATURED_OBSERVATIONS"),
    ("/?ds=9", 404, "DATASET_NOT_FOUND"),
    ("/ops?status=X", 422, "INVALID_STATUS"),
    ("/ops?run=1", 200, "Không áp dụng"),
])
def test_invalid_inputs_render_explained_pages(demo, url, status, needle):
    r = demo[1].get(url)
    assert r.status_code == status and needle in text(r), (url, r.status_code, text(r)[:400])


# ---- data parity HTML <-> SQL ----------------------------------------------------------------------------------
def test_overview_matches_sql(demo):
    s, c = demo
    r = c.get("/?ds=1")
    with connect(s) as cn:
        n_prices = query(cn, "SELECT COUNT(*) AS n FROM dbo.DailyPrice WHERE DatasetId=1")[0]["n"]
        n_stocks = query(cn, "SELECT COUNT(DISTINCT StockId) AS n FROM dbo.DailyPrice WHERE DatasetId=1")[0]["n"]
        today = query(cn, "SELECT CONVERT(date, SYSDATETIMEOFFSET() AT TIME ZONE 'SE Asia Standard Time') AS d")[0]["d"]
        eligible = query(cn, "SELECT COUNT_BIG(*) AS n FROM dbo.fn_EligiblePredictions(?) WHERE DatasetId=1", (today,))[0]["n"]
        latest = query(cn, "SELECT ClosePrice, Volume FROM dbo.vw_LatestStockPrice WHERE DatasetId=1 ORDER BY Ticker")
    assert metric(r, "price_rows") == fmt_num(n_prices, 0) == "280"
    assert metric(r, "stocks_with_prices") == fmt_num(n_stocks, 0)
    assert metric(r, "eligible_predictions") == fmt_num(eligible, 0) == "256"
    assert [[float(a), int(b)] for a, b in data_v(r, "latestTable")] == [[x["ClosePrice"], x["Volume"]] for x in latest]
    assert "Mô phỏng cố định" in text(r)


def test_market_table_chart_paging_sort_match_sql(demo):
    s, c = demo
    r = c.get("/market?ds=1&t=DEMO03&f=2025-02-01&to=2025-02-14&sort=close&order=asc")
    with connect(s) as cn:
        rows = query(cn, """SELECT p.ClosePrice, p.Volume FROM dbo.DailyPrice p JOIN dbo.Stock s ON s.StockId=p.StockId
                            WHERE p.DatasetId=1 AND s.Ticker='DEMO03' AND p.TradeDate BETWEEN '2025-02-01' AND '2025-02-14' ORDER BY p.ClosePrice, p.TradeDate""")
    assert [[float(a), int(b)] for a, b in data_v(r, "priceTable")] == [[x["ClosePrice"], x["Volume"]] for x in rows]
    assert f"1–{len(rows)} / {len(rows)}" in text(r)
    chart = re.search(r'<script type="application/json" id="chartData">(.*?)</script>', r.text, re.S).group(1)
    import json
    pts = json.loads(chart)["points"]
    assert len(pts) == len(rows) and json.loads(chart)["basis"] == "SOURCE_CLOSE"
    assert 'aria-sort="ascending"' in r.text
    full = c.get("/market?ds=1&t=DEMO03")
    assert "1–35 / 35" in text(full)
    p2 = c.get("/market?ds=1&t=DEMO01&page=1")
    assert len(data_v(p2, "priceTable")) == 35


def test_forecast_metrics_match_view_and_procedure(demo):
    s, c = demo
    r = c.get("/forecast?ds=1&run=1&as_of=2026-07-01")
    rows = {re.search(r'data-run="(\d+)"', tr).group(1): re.findall(r'data-v="([^"]*)"', tr)
            for tr in re.findall(r"<tr data-run=.*?</tr>", r.text, re.S)}
    with connect(s) as cn:
        proc = query(cn, "EXEC dbo.usp_GetModelPerformance 'demo_baseline',1,5,'20250101','20251231','20260701'")[0]
    evaluated, acc, brier, logloss = rows["1"]
    assert int(evaluated) == proc["EvaluatedRows"] == 128
    assert abs(float(acc) - float(proc["Accuracy"])) < 1e-9 and abs(float(brier) - proc["BrierScore"]) < 1e-12
    pending = c.get("/forecast?ds=1&run=1&as_of=2026-07-01&status=pending")
    assert text(pending).count("— (chưa chấm)") == 1
    assert "1–50 / 129" in text(c.get("/forecast?ds=1&run=1&as_of=2026-07-01")) and "51–100 / 129" in text(c.get("/forecast?ds=1&run=1&as_of=2026-07-01&page=2"))


def test_compare_matches_usp_compare_models(demo):
    s, c = demo
    r = c.get("/compare?ds=1&runs=1&runs=2&f=2025-01-02&to=2025-02-17&as_of=2026-07-01")
    with connect(s) as cn:
        proc = query(cn, "EXEC dbo.usp_CompareModels '1,2','20250102','20250217','20260701'")
    got = data_v(r, "compareTable")
    assert [int(x[0]) for x in got] == [p["CommonObservations"] for p in proc] == [128, 128]
    assert all(abs(float(g[1]) - float(p["Accuracy"])) < 1e-9 for g, p in zip(got, proc))
    assert "quan sát chung" in text(r)
    assert "Chọn run, khoảng ngày gốc" in text(c.get("/compare?ds=1"))     # empty state before submitting


# ---- security -------------------------------------------------------------------------------------------------
def test_security_headers_host_and_origin(demo):
    _, c = demo
    assert c.get("/", headers={"Host": "evil.example:8000"}).status_code == 421
    csp = c.get("/").headers["content-security-policy"]
    assert "script-src 'self'" in csp and "connect-src 'none'" in csp and "form-action 'self'" in csp
    assert c.post("/ops/eod", data={"x": 1}, headers={"Origin": "http://evil.example"}).status_code == 403
    assert c.post("/ops/eod", data={"x": 1}, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403


def test_demo_refuses_eod_even_with_valid_csrf_and_token(demo):
    _, c = demo
    page = c.get("/ops?ds=1")
    assert 'disabled' in page.text and "Đồng bộ bị tắt" in text(page)
    r = c.post("/ops/eod", data={"csrf": c.cookies.get("ml_csrf") or "x" * 43, "ds": "1", "session_date": "2026-10-02",
                                 "ops_token": TOKEN, "action": "DRY_RUN"}, follow_redirects=False)
    assert r.status_code in (403, 409)


def test_real_ops_form_csrf_token_confirmation_and_job(real, it_env):
    s, c = real
    page = c.get("/ops?ds=1")
    assert page.status_code == 200 and "REAL_PRIVATE" in page.text and c.cookies.get("ml_csrf")
    csrf = csrf_of(page)
    base = {"csrf": csrf, "ds": "1", "session_date": "2026-10-02", "ops_token": TOKEN}
    r = c.post("/ops/eod", data={**base, "csrf": "forged" * 8, "action": "DRY_RUN"}, follow_redirects=False)
    assert r.status_code == 403 and "CSRF_FAILED" in text(r)
    r = c.post("/ops/eod", data={**base, "ops_token": "w" * 40, "action": "DRY_RUN"}, follow_redirects=False)
    assert r.status_code == 401 and "INVALID_OPS_TOKEN" in text(r) and "w" * 40 not in r.text
    r = c.post("/ops/eod", data={**base, "action": "SYNC"}, follow_redirects=False)
    assert r.status_code == 422 and "CONFIRMATION_REQUIRED" in text(r)
    r = c.post("/ops/eod", data={**base, "action": "SYNC", "confirm_sync": "yes"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/ops/jobs/")
    job_url = r.headers["location"]
    for _ in range(60):
        j = c.get(job_url)
        if "Đang chạy" not in j.text:
            break
        assert 'http-equiv="refresh"' in j.text
        time.sleep(0.25)
    status = re.search(r'id="jobState" data-status="(\w+)" data-run="(\d+)"', j.text)
    assert status and status.group(1) == "SUCCESS", text(j)[:500]
    assert TOKEN not in j.text and TOKEN not in c.get("/ops?ds=1").text
    with connect(s) as cn:
        assert query(cn, "SELECT COUNT(*) AS n FROM dbo.DailyPrice WHERE TradeDate='2026-10-02'")[0]["n"] == 5
    with connect(s, it_env["ops_db"]) as cn:
        assert query(cn, "SELECT TriggerKind FROM ops.EodRun WHERE EodRunId=?", (int(status.group(2)),))[0]["TriggerKind"] == "WEB"
    detail = c.get(f"/ops?ds=1&run={status.group(2)}")
    assert text(detail).count("INSERTED") >= 5 and metric(detail, "last_success") == "2026-10-02"
    time.sleep(5.1)   # rate limit between jobs
    # rerun of the same session through the form is idempotent
    r = c.post("/ops/eod", data={**base, "csrf": csrf_of(c.get("/ops?ds=1")), "action": "DRY_RUN"}, follow_redirects=False)
    assert r.status_code == 303
    for _ in range(60):
        j = c.get(r.headers["location"])
        if "Đang chạy" not in j.text:
            break
        time.sleep(0.25)
    assert 'data-status="DRY_RUN_OK"' in j.text and "không đổi 5" in text(j)
    # lockout: 5 failures within 10 minutes (one above) -> refused even with the right token
    for _ in range(4):
        c.post("/ops/eod", data={**base, "csrf": csrf, "ops_token": "x" * 40, "action": "DRY_RUN"}, follow_redirects=False)
    r = c.post("/ops/eod", data={**base, "csrf": csrf, "action": "DRY_RUN"}, follow_redirects=False)
    assert r.status_code == 429 and "TOO_MANY_AUTH_FAILURES" in text(r)


def test_real_without_provider_shows_failed_job(it_env):
    s = it_settings(it_env["db"], it_env["ops_db"])
    c = TestClient(create_app(s))
    csrf = csrf_of(c.get("/ops?ds=1"))
    r = c.post("/ops/eod", data={"csrf": csrf, "ds": "1", "session_date": "2026-10-05", "ops_token": TOKEN, "action": "DRY_RUN"},
               follow_redirects=False)
    assert r.status_code == 303
    for _ in range(40):
        j = c.get(r.headers["location"])
        if "Đang chạy" not in j.text:
            break
        time.sleep(0.25)
    assert 'data-status="FAILED"' in j.text and "PROVIDER_NOT_CONFIGURED" in j.text


# ---- availability, mode guard, scope labels ------------------------------------------------------------------
def test_sql_downtime_renders_503_page():
    s = load_settings(env={"MARKETLAB_SQL_SERVER": "tcp:127.0.0.1,1", "MARKETLAB_SQL_LOGIN_TIMEOUT": "2"})
    c = TestClient(create_app(s))
    assert c.get("/health").status_code == 200
    r = c.get("/")
    assert r.status_code == 503 and "DB_UNAVAILABLE" in text(r) and "Thử lại" in text(r)


def test_mode_mismatch_is_refused(require_sql):
    s = load_settings(env={"MARKETLAB_MODE": "REAL_PRIVATE", "MARKETLAB_SQL_DATABASE": "MarketLabVN30_Demo"})
    r = TestClient(create_app(s)).get("/market")
    assert r.status_code == 503 and "MODE_DATASET_MISMATCH" in text(r)


def test_scope_labels_and_freshness(demo, real):
    assert "DEMO_OFFLINE · DỮ LIỆU MÔ PHỎNG" in demo[1].get("/").text
    r = real[1].get("/?ds=1")
    assert "REAL_PRIVATE · DỮ LIỆU THẬT" in r.text and ("Đã cập nhật" in r.text or "Có thể chậm" in r.text)


def test_research_read_only_scope(require_sql):
    s = load_settings(env={"MARKETLAB_MODE": "REAL_PRIVATE", "MARKETLAB_SQL_DATABASE": "MarketLabVN30_Research_20261027",
                           "MARKETLAB_OPS_DATABASE": "MarketLabVN30_Ops"})
    r = TestClient(create_app(s)).get("/ops")
    if r.status_code == 503 and "DB_UNAVAILABLE" in r.text:
        pytest.skip("research database not present on this machine")
    assert r.status_code == 200 and "RESEARCH_READ_ONLY" in r.text and "Đồng bộ bị tắt" in text(r)


def test_peers_accept_only_loopback():
    from marketlab_app.config import ConfigError
    s = load_settings(env={"MARKETLAB_PEERS": "DEMO_OFFLINE=http://127.0.0.1:8000,REAL_PRIVATE=http://localhost:8001/"})
    assert s.peers == (("DEMO_OFFLINE", "http://127.0.0.1:8000"), ("REAL_PRIVATE", "http://localhost:8001"))
    for bad in ("X=http://evil.example:8000", "REAL=https://127.0.0.1:8001", "REAL=http://192.168.1.5:8001", "nolabel"):
        with pytest.raises(ConfigError):
            load_settings(env={"MARKETLAB_PEERS": bad})


def test_chart_breaks_on_calendar_session_without_price(real, it_env):
    s, c = real
    svc = EodService(s, provider=FakeProvider(fake_series()), trigger="TEST", clock=CLOCK)
    assert svc.sync_session(dt.date(2026, 10, 5)).status == "SUCCESS"
    with connect(s) as cn:   # isolated integration-test database only
        assert cn.getinfo(16).startswith("MarketLabVN30_IT_")
        cn.cursor().execute("DELETE dbo.DailyPrice WHERE DatasetId=1 AND StockId=3 AND TradeDate='2026-10-02'")
    r = c.get("/market?ds=1&t=TST03")
    import json
    pts = json.loads(re.search(r'id="chartData">(.*?)</script>', r.text, re.S).group(1))["points"]
    assert [p["TradeDate"] for p in pts] == ["2026-10-01", "2026-10-02", "2026-10-05"] and pts[1]["ClosePrice"] is None
    assert "1 phiên thiếu giá" in text(r) and "2026-10-02" in text(r)
    assert r.headers["server-timing"].startswith("app;dur=")
