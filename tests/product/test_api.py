"""API tests: valid/invalid input, paging, security (Host/Origin/token/lockout), SQL downtime, mode guard,
and API-vs-SQL agreement. Demo DB is only read; writes go to an isolated IT database with the test-only FakeProvider."""
import datetime as dt
import time

import pytest
from fastapi.testclient import TestClient

from conftest import CLOCK, fake_series, it_settings
from marketlab_app.api import create_app
from marketlab_app.config import load_settings
from marketlab_app.db import connect, query
from marketlab_app.eod.providers import FakeProvider
from marketlab_app.eod.service import EodService

pytestmark = pytest.mark.integration
TOKEN = "t" * 40


@pytest.fixture(scope="module")
def demo(require_sql):
    s = load_settings(env={"MARKETLAB_MODE": "DEMO_OFFLINE", "MARKETLAB_SQL_DATABASE": "MarketLabVN30_Demo", "MARKETLAB_OPS_TOKEN": TOKEN})
    return s, TestClient(create_app(s))


@pytest.fixture(scope="module")
def real(it_env):
    s = it_env["settings"]
    app = create_app(s, service_factory=lambda: EodService(s, provider=FakeProvider(fake_series()), trigger="API", clock=CLOCK))
    return s, TestClient(app)


def err(r):
    return r.json()["error"]["code"]


def test_health_ready_docs(demo):
    _, c = demo
    assert c.get("/api/health").json()["status"] == "ok"
    rd = c.get("/api/ready").json()
    assert rd["ready"] and rd["checks"]["schema"]["user_tables"] == 13 and rd["checks"]["mode"]["dataset_kinds"] == ["SYNTHETIC"]
    html = c.get("/api/docs").text
    assert "/api/docs-assets/swagger-ui-bundle.js" in html and "cdn" not in html.lower()
    assert c.get("/api/docs-assets/swagger-ui-bundle.js").status_code == 200
    paths = c.get("/api/openapi.json").json()["paths"]
    for p in ["/api/health", "/api/ready", "/api/datasets", "/api/stocks", "/api/prices", "/api/prices/latest", "/api/models",
              "/api/predictions", "/api/performance", "/api/models/compare", "/api/ops/runs", "/api/ops/last-status", "/api/ops/eod"]:
        assert p in paths, p


@pytest.mark.parametrize("url,status,code", [
    ("/api/prices?dataset_id=0", 422, "INVALID_INPUT"),
    ("/api/prices?dataset_id=999", 404, "DATASET_NOT_FOUND"),
    ("/api/prices?dataset_id=1&ticker=A;B", 422, "INVALID_TICKER"),
    ("/api/prices?dataset_id=1&ticker=ZZZ", 404, "TICKER_NOT_FOUND"),
    ("/api/prices?dataset_id=1&date_from=2025-02-10&date_to=2025-01-01", 422, "INVALID_DATE_RANGE"),
    ("/api/prices?dataset_id=1&limit=1000", 422, "INVALID_INPUT"),
    ("/api/prices?dataset_id=1&sort=price;drop", 422, "INVALID_INPUT"),
    ("/api/predictions?run_id=99", 404, "RUN_NOT_FOUND"),
    ("/api/predictions?run_id=1&as_of=2026-13-01", 422, "INVALID_INPUT"),
    ("/api/predictions?run_id=1&status=bogus", 422, "INVALID_INPUT"),
    ("/api/models/compare?run_ids=1&date_from=2025-01-01&date_to=2025-12-31", 422, "INVALID_INPUT"),
    ("/api/models/compare?run_ids=1,1&date_from=2025-01-01&date_to=2025-12-31", 422, "DUPLICATE_RUN_IDS"),
    ("/api/models/compare?run_ids=1,77&date_from=2025-01-01&date_to=2025-12-31", 422, "RUNS_NOT_FOUND_OR_COUNT"),
    ("/api/models/compare?run_ids=1,2&date_from=2025-01-01&date_to=2025-12-31&as_of=2025-01-03", 422, "NO_COMMON_MATURED_OBSERVATIONS"),
    ("/api/stocks?dataset_id=1&q=%25", 422, "INVALID_TICKER"),
    ("/api/ops/runs", 409, "MODE_DEMO_OFFLINE"),
])
def test_invalid_inputs(demo, url, status, code):
    r = demo[1].get(url)
    assert r.status_code == status and err(r) == code, r.text


def test_paging_and_sql_agreement(demo):
    s, c = demo
    page = c.get("/api/prices?dataset_id=1&limit=10&offset=275&sort=date&order=asc").json()
    with connect(s) as cn:
        total = query(cn, "SELECT COUNT(*) AS n FROM dbo.DailyPrice WHERE DatasetId=1")[0]["n"]
        view = query(cn, "SELECT RunId,EvaluatedRows,Accuracy,BrierScore,NaturalLogLoss FROM dbo.vw_ModelPerformance ORDER BY RunId")
        latest = query(cn, "SELECT Ticker,TradeDate,ClosePrice FROM dbo.vw_LatestStockPrice WHERE DatasetId=1 ORDER BY Ticker")
        proc = query(cn, "EXEC dbo.usp_CompareModels '1,2','20250101','20260101','20260701'")
        today = query(cn, "SELECT CONVERT(date,SYSUTCDATETIME()) AS d")[0]["d"]
    assert page["total"] == total == 280 and len(page["items"]) == 5
    perf = c.get(f"/api/performance?as_of={today}").json()["items"]
    for v, p in zip(view, perf):
        assert v["RunId"] == p["RunId"] and v["EvaluatedRows"] == p["EvaluatedRows"]
        for k in ("Accuracy", "BrierScore", "NaturalLogLoss"):
            assert abs(v[k] - p[k]) < 1e-12
    api_latest = c.get("/api/prices/latest?dataset_id=1").json()["items"]
    assert [(x["Ticker"], x["TradeDate"], x["ClosePrice"]) for x in api_latest] == [(x["Ticker"], x["TradeDate"], x["ClosePrice"]) for x in latest]
    cmp_ = c.get("/api/models/compare?run_ids=1,2&date_from=2025-01-01&date_to=2026-01-01&as_of=2026-07-01").json()["rows"]
    assert [(r["RunId"], r["CommonObservations"], r["Accuracy"]) for r in cmp_] == [(r["RunId"], r["CommonObservations"], r["Accuracy"]) for r in proc]
    preds = c.get("/api/predictions?run_id=1&as_of=2026-07-01&limit=500").json()
    assert preds["total"] == 129 and sum(1 for x in preds["items"] if x["EvaluationStatus"] == "ELIGIBLE") == 128


def test_host_origin_and_demo_write_guard(demo):
    _, c = demo
    assert c.get("/api/health", headers={"Host": "evil.example:8000"}).status_code == 421
    body = {"session_date": "2026-10-02", "dry_run": True, "confirm": "DRY_RUN"}
    r = c.post("/api/ops/eod", json=body, headers={"Origin": "http://evil.example", "X-MarketLab-Ops-Token": TOKEN})
    assert r.status_code == 403 and err(r) == "ORIGIN_NOT_ALLOWED"
    r = c.post("/api/ops/eod", json=body, headers={"Sec-Fetch-Site": "cross-site", "X-MarketLab-Ops-Token": TOKEN})
    assert r.status_code == 403
    r = c.post("/api/ops/eod", json=body, headers={"X-MarketLab-Ops-Token": TOKEN})
    assert r.status_code == 409 and err(r) == "MODE_DEMO_OFFLINE"
    meta = c.get("/api/meta").text
    assert TOKEN not in meta and "csp" not in meta.lower()
    assert "default-src 'self'" in c.get("/").headers["content-security-policy"]


def test_sql_downtime_is_503():
    s = load_settings(env={"MARKETLAB_SQL_SERVER": "tcp:127.0.0.1,1", "MARKETLAB_SQL_LOGIN_TIMEOUT": "2"})
    c = TestClient(create_app(s))
    assert c.get("/api/health").status_code == 200       # liveness does not depend on the DB
    r = c.get("/api/ready")
    assert r.status_code == 503 and not r.json()["checks"]["database"]["ok"]
    r = c.get("/api/datasets")
    assert r.status_code == 503 and err(r) == "DB_UNAVAILABLE"


def test_mode_mismatch_is_refused(require_sql):
    s = load_settings(env={"MARKETLAB_MODE": "REAL_PRIVATE", "MARKETLAB_SQL_DATABASE": "MarketLabVN30_Demo"})
    c = TestClient(create_app(s))
    r = c.get("/api/datasets")
    assert r.status_code == 503 and err(r) == "MODE_DATASET_MISMATCH"
    assert c.get("/api/ready").status_code == 503


def test_real_mode_token_lockout_and_job(real):
    s, c = real
    body = {"session_date": "2026-10-02", "dry_run": False, "confirm": "SYNC"}
    assert err(c.post("/api/ops/eod", json=body)) == "INVALID_OPS_TOKEN"
    r = c.post("/api/ops/eod", json={**body, "confirm": "DRY_RUN"}, headers={"X-MarketLab-Ops-Token": TOKEN})
    assert r.status_code == 422 and err(r) == "CONFIRMATION_MISMATCH"
    r = c.post("/api/ops/eod", json=body, headers={"X-MarketLab-Ops-Token": TOKEN})
    assert r.status_code == 202
    job = r.json()
    for _ in range(60):
        j = c.get(job["poll"]).json()
        if j["state"] != "RUNNING":
            break
        time.sleep(0.5)
    assert j["state"] == "DONE" and j["result"]["status"] == "SUCCESS" and j["result"]["inserted"] == 5
    runs = c.get("/api/ops/runs?dataset_id=1").json()
    assert runs["items"][0]["EodRunId"] == j["result"]["eod_run_id"] and runs["items"][0]["TriggerKind"] == "API"
    detail = c.get(f"/api/ops/runs/{j['result']['eod_run_id']}").json()
    assert len(detail["items"]) == 5 and {i["Outcome"] for i in detail["items"]} == {"INSERTED"}
    last = c.get("/api/ops/last-status?dataset_id=1").json()
    assert last["last_successful_trade_date"] == "2026-10-02" == last["dataset_observed_through"]
    with connect(s) as cn:
        n = query(cn, "SELECT COUNT(*) AS n FROM dbo.DailyPrice WHERE TradeDate='2026-10-02'")[0]["n"]
    assert n == 5
    cmp_ = c.get("/api/models/compare?run_ids=1,3&date_from=2026-10-01&date_to=2026-10-01&as_of=2026-10-05")
    assert cmp_.status_code == 409 and err(cmp_) == "INCOMPATIBLE_RUNS"
    # brute force: the missing-token request above was failure #1; 4 more wrong tokens -> locked even for the right one
    for _ in range(4):
        assert c.post("/api/ops/eod", json=body, headers={"X-MarketLab-Ops-Token": "w" * 40}).status_code == 401
    r = c.post("/api/ops/eod", json=body, headers={"X-MarketLab-Ops-Token": TOKEN})
    assert r.status_code == 429 and err(r) == "TOO_MANY_AUTH_FAILURES"


def test_real_mode_without_provider_reports_missing_source(it_env):
    s = it_settings(it_env["db"], it_env["ops_db"])
    c = TestClient(create_app(s))     # real service factory, MARKETLAB_PROVIDER_PYTHON not set
    r = c.post("/api/ops/eod", json={"session_date": "2026-10-05", "dry_run": True, "confirm": "DRY_RUN"},
               headers={"X-MarketLab-Ops-Token": TOKEN})
    assert r.status_code == 202
    for _ in range(40):
        j = c.get(r.json()["poll"]).json()
        if j["state"] != "RUNNING":
            break
        time.sleep(0.25)
    assert j["result"]["status"] == "FAILED" and j["result"]["error_code"] == "PROVIDER_NOT_CONFIGURED"
    assert c.get("/api/meta").json()["eod"]["provider_configured"] is False
