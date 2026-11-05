"""Local API gateway (FastAPI) + static dashboard. Bind 127.0.0.1 only."""
from __future__ import annotations

import datetime as dt
import hmac
import logging
import re
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__, queries
from .config import Settings
from .db import DatabaseUnavailable, SqlError, connect, query
from .eod.calendar import now_vn

log = logging.getLogger("marketlab.api")
WEB = Path(__file__).with_name("web")
TICKER_RE = re.compile(r"^[A-Za-z0-9]{1,20}$")
DISCLAIMER = ("Công cụ học thuật quản lý dữ liệu và đánh giá dự báo đã có. Không phải sàn giao dịch, không phải khuyến nghị đầu tư; "
              "giá là dữ liệu cuối phiên (EOD), không phải realtime.")
INFERENCE_STATUS = {"configured": False,
                    "message": "Chưa cấu hình mô hình tạo dự báo mới: repository không có model artifact hay pipeline inference. "
                               "Hệ thống chỉ quản lý và đánh giá các dự báo đã có."}


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details or {}


SQL_ERROR_MAP = {
    51016: (422, "INVALID_FILTER"), 51017: (404, "NOT_FOUND"), 51018: (422, "INVALID_RUN_LIST"),
    51019: (422, "RUNS_NOT_FOUND_OR_COUNT"), 51020: (409, "INCOMPATIBLE_RUNS"),
    51021: (422, "NO_COMMON_MATURED_OBSERVATIONS"),
}


class EodRequest(BaseModel):
    session_date: dt.date | None = Field(None, description="Session date (Asia/Ho_Chi_Minh). Omit = today in Vietnam.")
    dry_run: bool = Field(True, description="True = validate and roll back inside SQL Server (default).")
    confirm: Literal["SYNC", "DRY_RUN"] = Field(..., description="Must equal 'SYNC' for a real write or 'DRY_RUN' for a dry run.")


class Guard:
    """Brute-force and abuse protection for write endpoints (in-memory, single local process)."""

    def __init__(self):
        self.failures: deque[float] = deque()
        self.lock = threading.Lock()
        self.last_job_start = 0.0

    def check_lockout(self):
        now = time.monotonic()
        with self.lock:
            while self.failures and now - self.failures[0] > 600:
                self.failures.popleft()
            if len(self.failures) >= 5:
                raise ApiError(429, "TOO_MANY_AUTH_FAILURES", "Too many failed token attempts; wait 10 minutes.")

    def fail(self):
        with self.lock:
            self.failures.append(time.monotonic())


def create_app(settings: Settings, service_factory=None) -> FastAPI:
    app = FastAPI(title="MarketLab VN30 Local API", version=__version__, docs_url=None, redoc_url=None,
                  openapi_url="/api/openapi.json",
                  description="Local gateway over the MarketLab VN30 SQL Server database. " + DISCLAIMER)
    # Swagger UI served from local files (works offline; no CDN).
    import swagger_ui_bundle
    from fastapi.openapi.docs import get_swagger_ui_html
    app.mount("/api/docs-assets", StaticFiles(directory=swagger_ui_bundle.swagger_ui_path), name="swagger-assets")

    @app.get("/api/docs", include_in_schema=False)
    def docs():
        return get_swagger_ui_html(openapi_url="/api/openapi.json", title="MarketLab VN30 API - Swagger",
                                   swagger_js_url="/api/docs-assets/swagger-ui-bundle.js",
                                   swagger_css_url="/api/docs-assets/swagger-ui.css",
                                   swagger_favicon_url="/api/docs-assets/favicon-32x32.png")
    allowed_hosts = {f"{h}:{settings.port}" for h in ("127.0.0.1", "localhost")} | {"127.0.0.1", "localhost", "testserver"}
    allowed_origins = {f"http://{h}:{settings.port}" for h in ("127.0.0.1", "localhost")} | {"http://testserver"}
    guard = Guard()
    jobs: dict[str, dict] = {}
    job_lock = threading.Lock()
    mode_cache: dict = {"at": 0.0, "value": None}

    from .eod.opsstore import OpsStore
    from .eod.service import EodService, EodSetupError
    ops = OpsStore(settings)
    make_service = service_factory or (lambda: EodService(settings, trigger="API"))

    # ---- middleware --------------------------------------------------------------------------------
    @app.middleware("http")
    async def security(request: Request, call_next):
        host = request.headers.get("host", "")
        if host not in allowed_hosts:
            return JSONResponse({"error": {"code": "HOST_NOT_ALLOWED", "message": "Only loopback Host headers are accepted"}}, 421)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if origin is not None and origin not in allowed_origins:
                return JSONResponse({"error": {"code": "ORIGIN_NOT_ALLOWED", "message": "Cross-origin write refused"}}, 403)
            if request.headers.get("sec-fetch-site") not in (None, "same-origin", "none"):
                return JSONResponse({"error": {"code": "CROSS_SITE_REFUSED", "message": "Cross-site write refused"}}, 403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        if not request.url.path.startswith("/api/docs"):
            response.headers["Content-Security-Policy"] = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
                                                           "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    # ---- error handlers ----------------------------------------------------------------------------
    @app.exception_handler(ApiError)
    async def api_error(_, exc: ApiError):
        return JSONResponse({"error": {"code": exc.code, "message": exc.message, **({"details": exc.details} if exc.details else {})}}, exc.status)

    @app.exception_handler(DatabaseUnavailable)
    async def db_down(_, exc: DatabaseUnavailable):
        return JSONResponse({"error": {"code": "DB_UNAVAILABLE", "message": str(exc)}}, 503)

    @app.exception_handler(SqlError)
    async def sql_error(_, exc: SqlError):
        status, code = SQL_ERROR_MAP.get(exc.number or 0, (500, f"SQL_{exc.number}"))
        if status >= 500:
            log.error("SQL error %s: %s", exc.number, exc.message)
        return JSONResponse({"error": {"code": code, "message": exc.message, "sql_error": exc.number}}, status)

    @app.exception_handler(RequestValidationError)
    async def bad_input(_, exc: RequestValidationError):
        details = [{"field": ".".join(str(x) for x in e.get("loc", [])[1:]), "message": e.get("msg")} for e in exc.errors()]
        return JSONResponse({"error": {"code": "INVALID_INPUT", "message": "Invalid request parameters", "details": details}}, 422)

    # ---- helpers -----------------------------------------------------------------------------------
    def today_vn() -> dt.date:
        return now_vn().date()

    def mode_check(c) -> dict:
        now = time.monotonic()
        if mode_cache["value"] is None or now - mode_cache["at"] > 30:
            kinds = queries.dataset_kinds(c)
            expected = "SYNTHETIC" if settings.is_demo else "REAL_PRIVATE"
            mode_cache["value"] = {"kinds": kinds, "expected": expected, "ok": bool(kinds) and set(kinds) == {expected}}
            mode_cache["at"] = now
        return mode_cache["value"]

    def require_mode(c):
        m = mode_check(c)
        if not m["ok"]:
            raise ApiError(503, "MODE_DATASET_MISMATCH",
                           f"MARKETLAB_MODE={settings.mode} expects only {m['expected']} datasets, database has {m['kinds']}. "
                           "No automatic switch is performed; fix .env.")

    def require_dataset(c, dataset_id: int) -> dict:
        require_mode(c)
        ds = queries.dataset_exists(c, dataset_id)
        if not ds:
            raise ApiError(404, "DATASET_NOT_FOUND", f"Dataset {dataset_id} does not exist")
        return ds

    def check_range(a, b, name="date"):
        if a and b and a > b:
            raise ApiError(422, "INVALID_DATE_RANGE", f"{name}_from must be <= {name}_to")

    def check_ticker(t: str | None) -> str | None:
        if t is None or t == "":
            return None
        if not TICKER_RE.match(t):
            raise ApiError(422, "INVALID_TICKER", "ticker must be 1-20 letters/digits")
        return t.upper()

    def page(items, total, limit, offset):
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    def require_token(x_marketlab_ops_token: Annotated[str | None, Header()] = None):
        if settings.is_demo:
            raise ApiError(409, "MODE_DEMO_OFFLINE", "EOD sync is disabled in DEMO_OFFLINE (synthetic database). Start in REAL_PRIVATE.")
        if not settings.ops_token:
            raise ApiError(503, "OPS_TOKEN_NOT_CONFIGURED", "MARKETLAB_OPS_TOKEN is not configured; write operations are disabled")
        guard.check_lockout()
        if not x_marketlab_ops_token or not hmac.compare_digest(x_marketlab_ops_token.encode(), settings.ops_token.encode()):
            guard.fail()
            raise ApiError(401, "INVALID_OPS_TOKEN", "Missing or invalid X-MarketLab-Ops-Token header")

    # ---- health / meta -----------------------------------------------------------------------------
    @app.get("/api/health", tags=["system"], summary="Process liveness only (does NOT check DB or data freshness)")
    def health():
        return {"status": "ok", "version": __version__, "mode": settings.mode,
                "server_time_vn": now_vn().isoformat(timespec="seconds")}

    @app.get("/api/ready", tags=["system"], summary="DB connectivity, required schema objects and mode/dataset consistency")
    def ready():
        checks: dict = {}
        try:
            with connect(settings) as c:
                st = queries.schema_status(c)
                m = mode_check(c)
                mode_cache["at"] = 0  # always fresh for ready
            checks["database"] = {"ok": True, "name": settings.sql_database}
            checks["schema"] = {"ok": not st["missing"] and st["marketlab_schema"] == "1.0", **st}
            checks["mode"] = {"ok": m["ok"], "mode": settings.mode, "dataset_kinds": m["kinds"]}
        except DatabaseUnavailable as exc:
            checks["database"] = {"ok": False, "error": str(exc)}
        ok_ops, why = ops.available()
        checks["ops"] = {"ok": ok_ops, "detail": why, "required": not settings.is_demo}
        ready_ok = all(v.get("ok") for k, v in checks.items() if k != "ops")
        body = {"ready": ready_ok, "checks": checks}
        return JSONResponse(body, 200 if ready_ok else 503)

    @app.get("/api/meta", tags=["system"], summary="Mode, source labels, disclaimers, inference status")
    def meta():
        ok_ops, why = ops.available()
        eod_cfg = []
        if ok_ops:
            try:
                eod_cfg = ops.config()
            except (DatabaseUnavailable, SqlError):
                eod_cfg = []
        label = ("DEMO_OFFLINE · DỮ LIỆU MÔ PHỎNG (SYNTHETIC)" if settings.is_demo
                 else "REAL_PRIVATE · DỮ LIỆU THẬT RIÊNG TƯ (không chia sẻ / không đẩy lên GitHub)")
        return {"mode": settings.mode, "label": label, "database": settings.sql_database, "server": settings.sql_server,
                "disclaimer": DISCLAIMER, "inference": INFERENCE_STATUS, "today_vn": today_vn().isoformat(),
                "eod": {"enabled": (not settings.is_demo) and ok_ops and bool(eod_cfg),
                        "reason": ("DEMO_OFFLINE: không đồng bộ dữ liệu thật vào CSDL mô phỏng" if settings.is_demo else
                                   (why if not ok_ops else ("chưa có ops.EodConfig cho database này" if not eod_cfg else "ok"))),
                        "config": [{k: (str(v) if isinstance(v, dt.time) else v) for k, v in x.items()} for x in eod_cfg],
                        "token_configured": bool(settings.ops_token),
                        "provider_configured": bool(settings.provider_python)}}

    # ---- catalog -----------------------------------------------------------------------------------
    @app.get("/api/datasets", tags=["catalog"])
    def list_datasets():
        with connect(settings) as c:
            require_mode(c)
            return {"items": queries.datasets(c)}

    @app.get("/api/overview", tags=["catalog"], summary="Dashboard summary for one dataset")
    def overview(dataset_id: int = Query(..., ge=1), as_of: dt.date | None = None):
        as_of = as_of or today_vn()
        with connect(settings) as c:
            require_dataset(c, dataset_id)
            ds = [d for d in queries.datasets(c) if d["DatasetId"] == dataset_id][0]
            eligible = queries.eligible_count(c, dataset_id, as_of)
        eod = None
        if not settings.is_demo and ops.available()[0]:
            eod = ops.last_status(dataset_id)
        return {"dataset": ds, "as_of": as_of.isoformat(), "eligible_predictions": eligible, "eod": eod,
                "freshness": {"dataset_observed_through": ds["ObservedThrough"], "last_price_date": ds["LastPriceDate"],
                              "today_vn": today_vn().isoformat(), "kind": "EOD (cuối phiên), không phải realtime"}}

    @app.get("/api/stocks", tags=["catalog"])
    def list_stocks(dataset_id: int = Query(..., ge=1), q: str | None = Query(None, max_length=20),
                    limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
        if q and not TICKER_RE.match(q):
            raise ApiError(422, "INVALID_TICKER", "q must be letters/digits")
        with connect(settings) as c:
            require_dataset(c, dataset_id)
            items, total = queries.stocks(c, dataset_id, q, limit, offset)
        return page(items, total, limit, offset)

    # ---- prices ------------------------------------------------------------------------------------
    @app.get("/api/prices", tags=["prices"], summary="Paged OHLCV table")
    def list_prices(dataset_id: int = Query(..., ge=1), ticker: str | None = None, date_from: dt.date | None = None,
                    date_to: dt.date | None = None, sort: Literal["date", "ticker", "close", "volume"] = "date",
                    order: Literal["asc", "desc"] = "desc", limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
        check_range(date_from, date_to)
        t = check_ticker(ticker)
        with connect(settings) as c:
            ds = require_dataset(c, dataset_id)
            if t and queries.stock_id(c, dataset_id, t) is None:
                raise ApiError(404, "TICKER_NOT_FOUND", f"{t} is not in dataset {dataset_id}")
            items, total = queries.prices(c, dataset_id, t, date_from, date_to, sort, order == "desc", limit, offset)
        return {**page(items, total, limit, offset), "price_unit": ds["PriceUnit"], "price_basis": ds["PriceBasis"]}

    @app.get("/api/prices/series", tags=["prices"], summary="Close/volume series of one ticker for charts")
    def series(dataset_id: int = Query(..., ge=1), ticker: str = Query(...), date_from: dt.date | None = None,
               date_to: dt.date | None = None, max_points: int = Query(1500, ge=2, le=5000)):
        check_range(date_from, date_to)
        t = check_ticker(ticker)
        if not t:
            raise ApiError(422, "INVALID_TICKER", "ticker is required")
        with connect(settings) as c:
            ds = require_dataset(c, dataset_id)
            if queries.stock_id(c, dataset_id, t) is None:
                raise ApiError(404, "TICKER_NOT_FOUND", f"{t} is not in dataset {dataset_id}")
            pts = queries.price_series(c, dataset_id, t, date_from, date_to, max_points)
        return {"ticker": t, "points": pts, "price_unit": ds["PriceUnit"], "price_basis": ds["PriceBasis"],
                "note": "Close nguồn cuối phiên; không phải giá điều chỉnh tổng lợi suất, không realtime"}

    @app.get("/api/prices/latest", tags=["prices"], summary="dbo.vw_LatestStockPrice per ticker")
    def latest(dataset_id: int = Query(..., ge=1)):
        with connect(settings) as c:
            ds = require_dataset(c, dataset_id)
            items = queries.latest_prices(c, dataset_id)
        return {"items": items, "price_unit": ds["PriceUnit"], "price_basis": ds["PriceBasis"],
                "observed_through": ds["ObservedThrough"]}

    # ---- forecasts ---------------------------------------------------------------------------------
    @app.get("/api/models", tags=["forecasts"], summary="Model runs (model, target/horizon, threshold)")
    def models(dataset_id: int | None = Query(None, ge=1)):
        with connect(settings) as c:
            if dataset_id is not None:
                require_dataset(c, dataset_id)
            else:
                require_mode(c)
            items = queries.model_runs(c, dataset_id)
        return {"items": items, "inference": INFERENCE_STATUS}

    @app.get("/api/predictions", tags=["forecasts"], summary="Predictions of one run with eligibility at as_of")
    def preds(run_id: int = Query(..., ge=1), as_of: dt.date | None = None, ticker: str | None = None,
              origin_from: dt.date | None = None, origin_to: dt.date | None = None,
              status: Literal["eligible", "pending", "missing_endpoint"] | None = None,
              limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
        check_range(origin_from, origin_to, "origin")
        t = check_ticker(ticker)
        as_of = as_of or today_vn()
        with connect(settings) as c:
            require_mode(c)
            if not queries.run_info(c, run_id):
                raise ApiError(404, "RUN_NOT_FOUND", f"Run {run_id} does not exist")
            items, total = queries.predictions(c, run_id, as_of, t, origin_from, origin_to, status, limit, offset)
        return {**page(items, total, limit, offset), "as_of": as_of.isoformat(),
                "note": "ProbabilityPositive là xác suất Close mục tiêu > Close gốc; không phải khuyến nghị đầu tư"}

    @app.get("/api/performance", tags=["forecasts"], summary="Accuracy/Brier/log loss on dbo.fn_EligiblePredictions(as_of)")
    def perf(as_of: dt.date | None = None, dataset_id: int | None = Query(None, ge=1), run_id: int | None = Query(None, ge=1)):
        as_of = as_of or today_vn()
        with connect(settings) as c:
            if dataset_id is not None:
                require_dataset(c, dataset_id)
            else:
                require_mode(c)
            if run_id is not None and not queries.run_info(c, run_id):
                raise ApiError(404, "RUN_NOT_FOUND", f"Run {run_id} does not exist")
            items = queries.performance(c, as_of, dataset_id, run_id)
        return {"as_of": as_of.isoformat(), "items": items,
                "rules": "Chỉ dự báo có đủ giá gốc và mục tiêu, TargetDate <= as_of và <= ObservedThrough, OriginDate > ValidationEnd; "
                         "nhãn = 1 khi Close mục tiêu > Close gốc; dự đoán = 1 khi p >= Threshold của run."}

    @app.get("/api/models/compare", tags=["forecasts"], summary="dbo.usp_CompareModels on the common (StockId,OriginDate,TargetDate) set")
    def compare(run_ids: str = Query(..., pattern=r"^\d+(,\d+){1,7}$"), date_from: dt.date = Query(...),
                date_to: dt.date = Query(...), as_of: dt.date | None = None):
        check_range(date_from, date_to)
        ids = [int(x) for x in run_ids.split(",")]
        if len(set(ids)) != len(ids):
            raise ApiError(422, "DUPLICATE_RUN_IDS", "run_ids must be distinct")
        as_of = as_of or today_vn()
        with connect(settings) as c:
            require_mode(c)
            res = queries.compare_runs(c, ids, date_from, date_to, as_of)
        return {"as_of": as_of.isoformat(), "date_from": date_from.isoformat(), "date_to": date_to.isoformat(),
                "run_ids": ids, **res,
                "note": "Mô tả trên cùng tập quan sát giao; khác biệt không tự chứng minh ưu thế thống kê."}

    # ---- operations ----------------------------------------------------------------------------------
    def ops_ready():
        if settings.is_demo:
            raise ApiError(409, "MODE_DEMO_OFFLINE", "EOD operations log is not used in DEMO_OFFLINE (synthetic database)")
        ok, why = ops.available()
        if not ok:
            raise ApiError(503, "OPS_UNAVAILABLE", why)

    @app.get("/api/ops/runs", tags=["operations"])
    def ops_runs(dataset_id: int | None = Query(None, ge=1), status: Literal["RUNNING", "SUCCESS", "FAILED", "SKIPPED", "NO_SESSION", "PARTIAL", "DRY_RUN_OK"] | None = None,
                 limit: int = Query(25, ge=1, le=200), offset: int = Query(0, ge=0)):
        ops_ready()
        items, total = ops.runs(dataset_id, limit, offset, status)
        return page(items, total, limit, offset)

    @app.get("/api/ops/runs/{eod_run_id}", tags=["operations"])
    def ops_run(eod_run_id: int):
        ops_ready()
        r = ops.run_detail(eod_run_id)
        if not r:
            raise ApiError(404, "EOD_RUN_NOT_FOUND", f"EOD run {eod_run_id} not found for this database")
        return r

    @app.get("/api/ops/last-status", tags=["operations"], summary="last_requested_date vs last_successful_trade_date vs observed_through")
    def ops_last(dataset_id: int = Query(..., ge=1)):
        ops_ready()
        with connect(settings) as c:
            ds = require_dataset(c, dataset_id)
            last_price = query(c, "SELECT MAX(TradeDate) AS d FROM dbo.DailyPrice WHERE DatasetId=?", (dataset_id,))[0]["d"]
        return {**ops.last_status(dataset_id), "dataset_observed_through": ds["ObservedThrough"], "last_price_date": last_price,
                "today_vn": today_vn().isoformat()}

    @app.get("/api/ops/calendar-check", tags=["operations"], summary="Per TradingDay: stored prices vs expected universe")
    def cal_check(dataset_id: int = Query(..., ge=1), date_from: dt.date | None = None, date_to: dt.date | None = None,
                  limit: int = Query(60, ge=1, le=400)):
        check_range(date_from, date_to)
        with connect(settings) as c:
            require_dataset(c, dataset_id)
            universe_ids = None
            if not settings.is_demo and ops.available()[0]:
                cfg = ops.config(dataset_id)
                if cfg:
                    universe_ids = [u["StockId"] for u in queries.universe(c, dataset_id, cfg[0]["IndexCode"],
                                                                           dt.date.fromisoformat(str(cfg[0]["UniverseAsOf"])))]
            items = queries.calendar_check(c, dataset_id, universe_ids, date_from, date_to, limit)
        return {"items": items, "universe_source": "ops.EodConfig index snapshot" if universe_ids else "all dataset-market stocks of matching kind"}

    @app.get("/api/ops/reconciliation", tags=["operations"])
    def recon(dataset_id: int = Query(..., ge=1), status: Literal["PENDING_REVIEW", "APPROVED_UPDATE", "REJECTED"] | None = None,
              limit: int = Query(50, ge=1, le=500)):
        ops_ready()
        return {"items": ops.reconciliation(dataset_id, status, limit)}

    @app.post("/api/ops/eod", tags=["operations"], status_code=202,
              summary="Start a guarded EOD sync (or dry run). Header X-MarketLab-Ops-Token required.")
    def start_eod(body: EodRequest, _: None = Depends(require_token)):
        if body.dry_run != (body.confirm == "DRY_RUN"):
            raise ApiError(422, "CONFIRMATION_MISMATCH", "confirm must be 'DRY_RUN' for dry_run=true and 'SYNC' for a real write")
        with job_lock:
            if any(j["state"] == "RUNNING" for j in jobs.values()):
                raise ApiError(409, "JOB_ALREADY_RUNNING", "An EOD job started from this server is still running")
            if time.monotonic() - guard.last_job_start < 5:
                raise ApiError(429, "RATE_LIMITED", "Wait a few seconds between EOD jobs")
            guard.last_job_start = time.monotonic()
            for old in [k for k, v in jobs.items() if v["state"] != "RUNNING"][:-49]:   # keep the last 50 finished jobs
                jobs.pop(old, None)
            job_id = uuid.uuid4().hex
            jobs[job_id] = {"job_id": job_id, "state": "RUNNING", "request": body.model_dump(mode="json"),
                            "started_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "result": None, "error": None}

        def work():
            try:
                svc = make_service()
                res = svc.sync_session(body.session_date, None, body.dry_run)
                jobs[job_id].update(state="DONE", result=res.to_dict())
            except EodSetupError as exc:
                jobs[job_id].update(state="ERROR", error={"code": "EOD_SETUP", "message": str(exc)})
            except Exception as exc:  # noqa: BLE001
                log.exception("EOD job failed")
                jobs[job_id].update(state="ERROR", error={"code": "INTERNAL_ERROR", "message": type(exc).__name__})
            finally:
                jobs[job_id]["finished_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()

        threading.Thread(target=work, name=f"eod-{job_id[:8]}", daemon=True).start()
        return {"job_id": job_id, "state": "RUNNING", "poll": f"/api/ops/jobs/{job_id}"}

    @app.get("/api/ops/jobs/{job_id}", tags=["operations"])
    def job(job_id: str):
        if not re.fullmatch(r"[0-9a-f]{32}", job_id) or job_id not in jobs:
            raise ApiError(404, "JOB_NOT_FOUND", "Unknown job id (jobs live only in this server process)")
        return jobs[job_id]

    # ---- web UI --------------------------------------------------------------------------------------
    app.mount("/static", StaticFiles(directory=WEB), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(WEB / "index.html")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return FileResponse(WEB / "favicon.svg", media_type="image/svg+xml")

    return app
