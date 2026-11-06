"""Server-rendered backfill page, LIVE history floor (2023-01-01) on every UI path, CSV export, EOD log separation.
Writes go only to an isolated MarketLabVN30_IT_* database through the test-only FakeProvider."""
import csv
import datetime as dt
import html
import io
import re
import time

import pytest
from fastapi.testclient import TestClient

from conftest import CLOCK, counts, fake_series
from marketlab_app.config import load_settings
from marketlab_app.db import connect, query
from marketlab_app.eod import backfill as bf
from marketlab_app.eod.providers import FakeProvider
from marketlab_app.web_app import create_app

pytestmark = pytest.mark.integration
TOKEN = "t" * 40
SEP = (dt.date(2026, 9, 1), dt.date(2026, 9, 30))


def text(r) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", r.text)))


def csrf_of(r) -> str:
    return re.search(r'name="csrf" value="([^"]+)"', r.text).group(1)


@pytest.fixture(scope="module")
def demo(require_sql):
    s = load_settings(env={"MARKETLAB_MODE": "DEMO_OFFLINE", "MARKETLAB_SQL_DATABASE": "MarketLabVN30_Demo", "MARKETLAB_OPS_TOKEN": TOKEN})
    return s, TestClient(create_app(s))


@pytest.fixture(scope="module")
def real(it_env):
    s = it_env["settings"]
    data = fake_series(*SEP)
    app = create_app(s, backfill_factory=lambda progress: bf.BackfillService(s, provider=FakeProvider(data), clock=CLOCK, trigger="TEST",
                                                                             progress=progress))
    return s, TestClient(app)


def post(c, page, **form):
    return c.post("/backfill/run", data={"csrf": csrf_of(page), "ds": "1", "ops_token": TOKEN, **form}, follow_redirects=False)


def wait_job(c, location, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        r = c.get(location)
        if 'data-status="' in r.text or 'role="alert"' in r.text:
            return r
        time.sleep(0.3)
    raise AssertionError("web backfill job did not finish")


def test_backfill_page_is_disabled_in_demo(demo):
    r = demo[1].get("/backfill")
    assert r.status_code == 200 and "DEMO_OFFLINE dùng CSDL mô phỏng" in text(r)
    assert re.search(r'id="bRun"[^>]*disabled', r.text) and 'action="/backfill/run"' not in r.text
    page = demo[1].get("/ops")
    r = demo[1].post("/backfill/run", data={"csrf": demo[1].cookies.get("ml_csrf"), "ops_token": TOKEN, "action": "DRY_RUN"})
    assert r.status_code == 409 and "MODE_DEMO_OFFLINE" in text(r) and page.status_code == 200


def test_backfill_form_guards(real):
    s, c = real
    page = c.get("/backfill?ds=1")
    assert page.status_code == 200 and "LIVE" in page.text and c.cookies.get("ml_csrf")
    before = counts(s, s.sql_database)
    r = c.post("/backfill/run", data={"csrf": "x" * 43, "ds": "1", "ops_token": TOKEN, "action": "DRY_RUN"})
    assert r.status_code == 403 and "CSRF_FAILED" in text(r)
    r = post(c, page, ops_token="w" * 40, action="DRY_RUN")
    assert r.status_code == 401 and "INVALID_OPS_TOKEN" in text(r) and "w" * 40 not in r.text and TOKEN not in r.text
    r = post(c, page, action="RUN", start_date="2026-09-01", end_date="2026-09-30")
    assert r.status_code == 422 and "CONFIRMATION_REQUIRED" in text(r)
    r = post(c, page, action="DRY_RUN", start_date="2022-12-01", end_date="2026-09-30")
    assert r.status_code == 422 and "BEFORE_HISTORY_START" in text(r)
    r = post(c, page, action="DRY_RUN", start_date="2026-09-01", end_date="tomorrow")
    assert r.status_code == 422 and "INVALID_DATE" in text(r)
    r = post(c, page, action="DRY_RUN", start_date="2026-09-01", tickers="TST01;DROP TABLE")
    assert r.status_code == 422 and "INVALID_TICKERS" in text(r)
    r = post(c, page, action="DELETE")
    assert r.status_code == 422 and "INVALID_ACTION" in text(r)
    assert counts(s, s.sql_database) == before


def test_web_dry_run_then_real_backfill(real):
    s, c = real
    before = counts(s, s.sql_database)
    page = c.get("/backfill?ds=1")
    r = post(c, page, action="DRY_RUN", start_date=SEP[0].isoformat(), end_date=SEP[1].isoformat())
    assert r.status_code == 303 and r.headers["location"].startswith("/backfill/jobs/")
    done = wait_job(c, r.headers["location"])
    assert 'data-status="DRY_RUN_OK"' in done.text, text(done)[:500]
    assert counts(s, s.sql_database) == before                    # dry run: business tables untouched
    time.sleep(5.2)                                              # one job start per 5 s (rate limit)
    page = c.get("/backfill?ds=1")
    r = post(c, page, action="RUN", confirm_write="yes", start_date=SEP[0].isoformat(), end_date=SEP[1].isoformat())
    done = wait_job(c, r.headers["location"])
    assert 'data-status="COMPLETED"' in done.text, text(done)[text(done).find("Trạng thái"):][:900]
    n = sum(1 for d in range((SEP[1] - SEP[0]).days + 1) if (SEP[0] + dt.timedelta(days=d)).weekday() < 5)
    assert counts(s, s.sql_database)["prices"] - before["prices"] == n * 5
    page = c.get("/backfill?ds=1")
    assert page.status_code == 200 and 'id="bfJobs"' in page.text and 'id="tickerCoverage"' in page.text and 'id="bfFetch"' in page.text
    assert "COMPLETED" in page.text or "Hoàn tất" in text(page)


def test_live_floor_on_market_page_and_export(real):
    s, c = real
    r = c.get("/market?ds=1&t=TST01&f=2022-06-01&to=2026-09-30")
    assert r.status_code == 422 and "2023-01-01" in text(r) and 'id="chartData"' not in r.text
    r = c.get("/market?ds=1&t=TST01&to=2022-12-31")
    assert r.status_code == 422
    assert 'min="2023-01-01"' in c.get("/market?ds=1&t=TST01").text
    r = c.get("/market/export.csv?ds=1&t=TST01&f=2022-01-01&to=2026-09-30")
    assert r.status_code == 422 and "INVALID_EXPORT" in text(r)
    r = c.get(f"/market/export.csv?ds=1&t=TST01&f={SEP[0]}&to={SEP[1]}")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "REAL_PRIVATE" in r.headers["x-marketlab-notice"] and "attachment" in r.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert rows and all(SEP[0].isoformat() <= x["TradeDate"] <= SEP[1].isoformat() for x in rows)
    with connect(s) as cn:
        sql = query(cn, "SELECT p.TradeDate, p.ClosePrice FROM dbo.DailyPrice p JOIN dbo.Stock s ON s.StockId=p.StockId "
                        "WHERE s.Ticker='TST01' AND p.TradeDate BETWEEN ? AND ? ORDER BY p.TradeDate", SEP)
    assert [(x["TradeDate"], float(x["Close"])) for x in rows] == [(x["TradeDate"], float(x["ClosePrice"])) for x in sql]


def test_market_default_range_is_last_12_months_and_presets(real):
    _, c = real
    r = c.get("/market?ds=1&t=TST01")
    assert r.status_code == 200 and "Mặc định: 12 tháng gần nhất" in text(r)
    pts = re.search(r'id="chartData">(.*?)</script>', r.text, re.S).group(1)
    dates = re.findall(r'"TradeDate": "(\d{4}-\d{2}-\d{2})"', pts)
    assert dates and dt.date.fromisoformat(dates[0]) >= dt.date.fromisoformat(dates[-1]) - dt.timedelta(days=366)
    assert all(lbl in r.text for lbl in (">3T<", ">6T<", ">1N<", ">Tất cả<")) and 'id="exportCsv"' in r.text


def test_daily_eod_log_hides_backfill_runs_unless_asked(real):
    _, c = real
    r = c.get("/ops?ds=1")
    assert r.status_code == 200 and "<td>BACKFILL</td>" not in r.text
    r = c.get("/ops?ds=1&trigger=all")
    assert r.status_code == 200 and "<td>BACKFILL</td>" in r.text
    assert c.get("/ops?ds=1&trigger=x").status_code == 422


def test_overview_labels_live_and_universe(real):
    _, c = real
    r = c.get("/?ds=1")
    assert r.status_code == 200 and 'data-mode="LIVE"' in r.text and "universe được cấu hình" in text(r)
    assert 'data-metric="date_range"' in r.text and 'data-metric="data_status"' in r.text and 'data-metric="last_backfill"' in r.text
    for p in ("/api/docs", "/openapi.json", "/docs", "/redoc", "/api/backfill", "/api/prices"):
        assert c.get(p).status_code == 404, p
