"""MarketLab VN30 local web application (server-side rendered).

Architecture: Browser -> this Python web application (FastAPI used only as the HTTP/ASGI framework, Jinja2 templates)
-> SQL Server via pyodbc. The browser never talks to SQL Server and there is no JSON/REST API or Swagger for the UI:
every page is rendered on the server from the existing views/functions/procedures (marketlab_app/queries.py).
The only write action, a guarded EOD sync, is an HTML form POST protected by the ops token, a CSRF token
(double-submit cookie, SameSite=Strict), Origin/Sec-Fetch-Site checks, lockout and a single-job guard.
Bind 127.0.0.1 only.
"""
from __future__ import annotations

import datetime as dt
import hmac
import json
import logging
import math
import re
import secrets
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from urllib.parse import parse_qs, urlencode

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import __version__, queries
from .config import Settings
from .db import DatabaseUnavailable, SqlError, connect, query
from .eod.calendar import now_vn

log = logging.getLogger("marketlab.web")
PKG = Path(__file__).parent
TICKER_RE = re.compile(r"^[A-Za-z0-9]{1,20}$")
PAGE_SIZE = 50
DISCLAIMER = ("Công cụ học thuật quản lý dữ liệu và đánh giá dự báo đã có. Không phải sàn giao dịch, không phải khuyến nghị đầu tư; "
              "giá là dữ liệu cuối phiên (EOD), không phải realtime.")
INFERENCE_MSG = ("Chưa cấu hình mô hình tạo dự báo mới: repository không có model artifact hay pipeline inference. "
                 "Hệ thống chỉ quản lý và đánh giá các dự báo đã có.")
SCOPE_LABEL = {"DEMO_OFFLINE": "DEMO_OFFLINE · DỮ LIỆU MÔ PHỎNG (SYNTHETIC)",
               "REAL_PRIVATE": "REAL_PRIVATE · DỮ LIỆU THẬT RIÊNG TƯ (EOD, không chia sẻ)",
               "RESEARCH_READ_ONLY": "RESEARCH_READ_ONLY · DỮ LIỆU NGHIÊN CỨU RIÊNG, CHỈ ĐỌC"}
SQL_ERROR_MAP = {51016: (422, "INVALID_FILTER"), 51017: (404, "NOT_FOUND"), 51018: (422, "INVALID_RUN_LIST"),
                 51019: (422, "RUNS_NOT_FOUND_OR_COUNT"), 51020: (409, "INCOMPATIBLE_RUNS"),
                 51021: (422, "NO_COMMON_MATURED_OBSERVATIONS")}
STATUS_TEXT = {"CURRENT": "Đã cập nhật", "BEHIND": "Có thể chậm", "SYNTHETIC_FIXED": "Mô phỏng cố định", "UNKNOWN": "Chưa rõ",
               "ELIGIBLE": "Đã chấm", "PENDING": "Chưa trưởng thành", "MISSING_ENDPOINT": "Thiếu giá endpoint",
               "COMPLETED": "Hoàn tất", "COMPLETED_WITH_GAPS": "Hoàn tất, còn thiếu", "INTERRUPTED": "Bị gián đoạn",
               "FETCHING": "Đang tải nguồn", "APPLYING": "Đang ghi", "CREATED": "Mới tạo", "COMPLETE": "Đủ mã",
               "DRY_RUN_PARTIAL": "Dry run, thiếu mã", "NO_HISTORY": "Chưa có lịch sử nguồn", "REJECTED_ROW": "Bị từ chối",
               "FULL_COVERAGE": "Đủ dữ liệu", "PARTIAL_COVERAGE": "Còn thiếu"}
STATUS_CLASS = {"SUCCESS": "good", "DRY_RUN_OK": "info", "NO_SESSION": "info", "SKIPPED": "warning", "PARTIAL": "serious",
                "FAILED": "critical", "RUNNING": "info", "ELIGIBLE": "good", "PENDING": "warning", "MISSING_ENDPOINT": "serious",
                "PENDING_REVIEW": "warning", "APPROVED_UPDATE": "good", "REJECTED": "critical", "INSERTED": "good",
                "UNCHANGED": "info", "WOULD_INSERT": "info", "MISSING": "serious", "CONFLICT": "critical", "NOT_WRITTEN": "warning",
                "CURRENT": "good", "BEHIND": "warning", "SYNTHETIC_FIXED": "info", "UNKNOWN": "serious",
                "COMPLETED": "good", "COMPLETED_WITH_GAPS": "serious", "INTERRUPTED": "warning", "FETCHING": "info",
                "APPLYING": "info", "CREATED": "info", "COMPLETE": "good", "DRY_RUN_PARTIAL": "info", "NO_HISTORY": "info",
                "REJECTED_ROW": "serious", "FULL_COVERAGE": "good", "PARTIAL_COVERAGE": "serious"}
MODE_SHORT = {"DEMO_OFFLINE": "DEMO", "REAL_PRIVATE": "LIVE", "RESEARCH_READ_ONLY": "RESEARCH"}
RANGE_PRESETS = [("3T", 92), ("6T", 183), ("1N", 365), ("2N", 730), ("Tất cả", None)]
EXPORT_LIMIT = 5000
HINTS = {"DB_UNAVAILABLE": "SQL Server không truy cập được: kiểm tra dịch vụ MSSQLSERVER rồi tải lại trang.",
         "MODE_DATASET_MISMATCH": "Sửa MARKETLAB_MODE / MARKETLAB_SQL_DATABASE trong .env rồi khởi động lại bằng scripts\\Start-MarketLab.ps1.",
         "OPS_UNAVAILABLE": "Database ops chưa sẵn sàng (python -m marketlab_app.deploy ops-db)."}


class PageError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


# ---- formatting helpers (vi-VN: thousands '.', decimals ',') -----------------------------------------------
def fmt_num(v, digits: int = 2) -> str:
    if v is None or v == "":
        return "—"
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "—"
    if not math.isfinite(x):
        return "—"
    s = f"{x:,.{digits}f}"
    if digits:
        s = s.rstrip("0").rstrip(".")
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def fmt_pct(v) -> str:
    return "—" if v is None else f"{fmt_num(float(v) * 100, 2)}%"


def fmt_date(v) -> str:
    return str(v)[:10] if v else "—"


def fmt_time(v) -> str:
    return (str(v).replace("T", " ")[:19] + " UTC") if v else "—"


def fmt_ms(v) -> str:
    if v is None:
        return "—"
    return f"{fmt_num(v, 0)} ms" if v < 1000 else f"{fmt_num(v / 1000, 1)} s"


def short_unit(u: str | None) -> str:
    return (u.split(";")[0].split("(")[0].strip() if u and len(u) > 28 else (u or ""))


def parse_date(raw: str | None, name: str) -> dt.date | None:
    if raw in (None, ""):
        return None
    try:
        return dt.date.fromisoformat(raw)
    except ValueError:
        raise PageError(422, "INVALID_DATE", f"{name} phải có dạng YYYY-MM-DD") from None


def parse_int(raw: str | None, name: str, lo: int = 1, hi: int = 10**9) -> int | None:
    if raw in (None, ""):
        return None
    if not str(raw).isdigit() or not lo <= int(raw) <= hi:
        raise PageError(422, "INVALID_NUMBER", f"{name} phải là số nguyên trong [{lo}, {hi}]")
    return int(raw)


class Guard:
    """Lockout after failed ops-token attempts (single local process)."""

    def __init__(self):
        self.failures: deque[float] = deque()
        self.lock = threading.Lock()
        self.last_job_start = 0.0

    def locked(self) -> bool:
        now = time.monotonic()
        with self.lock:
            while self.failures and now - self.failures[0] > 600:
                self.failures.popleft()
            return len(self.failures) >= 5

    def fail(self):
        with self.lock:
            self.failures.append(time.monotonic())


def create_app(settings: Settings, service_factory=None, backfill_factory=None) -> FastAPI:
    app = FastAPI(title="MarketLab VN30", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)
    templates = Jinja2Templates(directory=PKG / "templates")
    env = templates.env
    env.filters.update(num=fmt_num, pct=fmt_pct, dt=fmt_date, ts=fmt_time, ms=fmt_ms)
    env.globals.update(STATUS_TEXT=STATUS_TEXT, STATUS_CLASS=STATUS_CLASS)
    allowed_hosts = {f"{h}:{settings.port}" for h in ("127.0.0.1", "localhost")} | {"127.0.0.1", "localhost", "testserver"}
    allowed_origins = {f"http://{h}:{settings.port}" for h in ("127.0.0.1", "localhost")} | {"http://testserver"}
    guard = Guard()
    jobs: dict[str, dict] = {}
    job_lock = threading.Lock()
    mode_cache: dict = {"at": 0.0, "value": None}

    from .eod.opsstore import OpsStore
    from .eod.service import EodService, EodSetupError
    ops = OpsStore(settings)
    make_service = service_factory or (lambda: EodService(settings, trigger="WEB"))
    # REAL_PRIVATE history floor (2023-01-01): every price query, chart, table and export starts at or after it
    floor = None if settings.is_demo else settings.history_start
    bjobs: dict[str, dict] = {}

    def make_backfill(progress):
        if backfill_factory:
            return backfill_factory(progress)
        from .eod.backfill import BackfillService
        from .eod.backup import backup_for_backfill
        return BackfillService(settings, trigger="WEB", progress=progress, backup_fn=lambda: backup_for_backfill(settings))

    # ---- middleware ------------------------------------------------------------------------------------------
    @app.middleware("http")
    async def security(request: Request, call_next):
        if request.headers.get("host", "") not in allowed_hosts:
            return PlainTextResponse("Host not allowed (loopback only)", 421)
        if request.method not in ("GET", "HEAD"):
            origin = request.headers.get("origin")
            if origin is not None and origin not in allowed_origins:
                return PlainTextResponse("Cross-origin request refused", 403)
            if request.headers.get("sec-fetch-site") not in (None, "same-origin", "none"):
                return PlainTextResponse("Cross-site request refused", 403)
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers["Server-Timing"] = f"app;dur={elapsed_ms:.1f}"
        if elapsed_ms > 1000:
            log.warning("slow request %.0f ms %s %s", elapsed_ms, request.method, request.url.path)
        response.headers["X-Content-Type-Options"] = "nosniff"
        # same-origin (not no-referrer): with no-referrer Chromium sends "Origin: null" on same-origin form POSTs
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
                                                       "connect-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if not request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    # ---- shared context ----------------------------------------------------------------------------------------
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

    def eod_info() -> dict:
        ok_ops, why = ops.available()
        cfg = []
        if ok_ops:
            try:
                cfg = ops.config()
            except (DatabaseUnavailable, SqlError):
                cfg = []
        enabled = (not settings.is_demo) and ok_ops and bool(cfg)
        reason = ("DEMO_OFFLINE: không đồng bộ dữ liệu thật vào CSDL mô phỏng" if settings.is_demo else
                  (why if not ok_ops else ("chưa có ops.EodConfig cho database này (chỉ đọc)" if not cfg else "ok")))
        return {"enabled": enabled, "reason": reason, "ops_ok": ok_ops,
                "config": [{k: (str(v) if isinstance(v, dt.time) else v) for k, v in x.items()} for x in cfg],
                "token_configured": bool(settings.ops_token), "provider_configured": bool(settings.provider_python)}

    def base_context(request: Request, c, page: str, ds_raw: str | None) -> dict:
        m = mode_check(c)
        if not m["ok"]:
            raise PageError(503, "MODE_DATASET_MISMATCH",
                            f"MARKETLAB_MODE={settings.mode} chỉ phục vụ dataset {m['expected']}, database có {m['kinds']}. Không tự chuyển chế độ.")
        datasets = queries.datasets(c)
        ds_id = parse_int(ds_raw, "ds") or datasets[0]["DatasetId"]
        ds = next((d for d in datasets if d["DatasetId"] == ds_id), None)
        if ds is None:
            raise PageError(404, "DATASET_NOT_FOUND", f"Dataset {ds_id} không tồn tại")
        eod = eod_info()
        ext = queries.schema_status(c)["eod_extension"] if not settings.is_demo else False
        scope = "DEMO_OFFLINE" if settings.is_demo else ("REAL_PRIVATE" if ext and eod["config"] else "RESEARCH_READ_ONLY")
        uni = None
        if eod["config"]:
            cfg = eod["config"][0]
            uni = (f"{ds['StocksWithPrices']} mã thuộc universe được cấu hình (tham chiếu {cfg['IndexCode']} {str(cfg['UniverseAsOf'])[:7]}); "
                   "không phải thành phần VN30 lịch sử tại từng thời điểm")
        return {"request": request, "page": page, "datasets": datasets, "ds": ds, "dsq": f"ds={ds['DatasetId']}",
                "scope": scope, "scope_label": SCOPE_LABEL[scope], "mode_short": MODE_SHORT[scope], "database": settings.sql_database,
                "floor": floor.isoformat() if floor else None, "universe_label": uni,
                "server_label": "(local)" if settings.sql_server in (".", "(local)", "localhost") else settings.sql_server,
                "today_vn": today_vn().isoformat(), "disclaimer": DISCLAIMER, "inference_msg": INFERENCE_MSG, "eod": eod,
                "peers": [{"label": lb, "url": u} for lb, u in settings.peers if not u.endswith(f":{settings.port}")],
                "version": __version__}

    def render(name: str, ctx: dict, status: int = 200) -> HTMLResponse:
        return templates.TemplateResponse(ctx["request"], name, ctx, status_code=status)

    def error_page(request: Request, status: int, code: str, message: str) -> HTMLResponse:
        return templates.TemplateResponse(request, "error.html", {"request": request, "status": status, "code": code, "message": message,
                                                                  "hint": HINTS.get(code), "disclaimer": DISCLAIMER,
                                                                  "scope": None, "page": None}, status_code=status)

    @app.exception_handler(PageError)
    async def page_error(request: Request, exc: PageError):
        return error_page(request, exc.status, exc.code, exc.message)

    @app.exception_handler(DatabaseUnavailable)
    async def db_down(request: Request, exc: DatabaseUnavailable):
        return error_page(request, 503, "DB_UNAVAILABLE", str(exc))

    @app.exception_handler(SqlError)
    async def sql_error(request: Request, exc: SqlError):
        status, code = SQL_ERROR_MAP.get(exc.number or 0, (500, f"SQL_{exc.number}"))
        if status >= 500:
            log.error("SQL error %s: %s", exc.number, exc.message)
        return error_page(request, status, code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def bad_input(request: Request, exc: RequestValidationError):
        return error_page(request, 422, "INVALID_INPUT", "Tham số không hợp lệ")

    def freshness(ds: dict, eod_status: dict | None) -> dict:
        now = now_vn()
        cutoff = dt.time(*(int(x) for x in settings.eod_cutoff.split(":")))
        d = now.date() if now.time() >= cutoff else now.date() - dt.timedelta(days=1)
        while d.weekday() >= 5:
            d -= dt.timedelta(days=1)
        last = ds["LastPriceDate"]
        base = {"expected": d.isoformat(), "last": last, "last_success": (eod_status or {}).get("last_successful_trade_date")}
        if ds["DataKind"] == "SYNTHETIC":
            return {**base, "status": "SYNTHETIC_FIXED", "message": "Dữ liệu mô phỏng cố định, không cập nhật theo phiên"}
        if not last:
            return {**base, "status": "UNKNOWN", "message": "Dataset chưa có giá"}
        if last >= d.isoformat():
            return {**base, "status": "CURRENT", "message": f"Đã có giá phiên {last} (phiên ngày làm việc dự kiến gần nhất: {d})"}
        gap = sum(1 for i in range((d - dt.date.fromisoformat(last)).days)
                  if (dt.date.fromisoformat(last) + dt.timedelta(days=i + 1)).weekday() < 5)
        return {**base, "status": "BEHIND",
                "message": f"Giá mới nhất {last}, chậm {gap} ngày làm việc so với {d} (có thể do nghỉ lễ hoặc chưa đồng bộ)"}

    def last_backfill_job() -> dict | None:
        if settings.is_demo:
            return None
        try:
            from .eod.backfill import jobs as list_jobs
            rows = list_jobs(settings, limit=50)
            if not rows:
                return None
            real = sorted((j for j in rows if not j["IsDryRun"] and j["Status"] in ("COMPLETED", "COMPLETED_WITH_GAPS")),
                          key=lambda j: ((j["SessionsPlanned"] or 0), j["JobId"]), reverse=True)
            main = dict(real[0] if real else rows[0])      # widest completed real job = the history load of record
            main["LatestJobId"], main["LatestStatus"] = rows[0]["JobId"], rows[0]["Status"]
            return main
        except (DatabaseUnavailable, SqlError):
            return None

    def pager(total: int, page: int, extra: dict) -> dict:
        pages = max(1, math.ceil(total / PAGE_SIZE))
        mk = lambda p: "?" + urlencode({**{k: v for k, v in extra.items() if v not in (None, "")}, "page": p})  # noqa: E731
        return {"total": total, "page": page, "pages": pages, "from": (page - 1) * PAGE_SIZE + 1 if total else 0,
                "to": min(total, page * PAGE_SIZE), "prev": mk(page - 1) if page > 1 else None, "next": mk(page + 1) if page < pages else None}

    # ---- liveness (plain text, used by Start-MarketLab.ps1; not a data API) ------------------------------------
    @app.get("/health", include_in_schema=False)
    def health():
        return PlainTextResponse(f"ok {settings.mode} {__version__}")

    # ---- 1. overview --------------------------------------------------------------------------------------------
    @app.get("/", response_class=HTMLResponse)
    def overview(request: Request, ds: str | None = None):
        with connect(settings) as c:
            ctx = base_context(request, c, "overview", ds)
            d = ctx["ds"]
            as_of = today_vn()
            eligible = queries.eligible_count(c, d["DatasetId"], as_of) if d["ModelRuns"] else None
            latest = queries.latest_prices(c, d["DatasetId"])
            cov = queries.coverage_summary(c, d["DatasetId"], floor)
        eod_status = ops.last_status(d["DatasetId"]) if ctx["eod"]["enabled"] else None
        ctx.update(as_of=as_of.isoformat(), eligible=eligible, latest=latest, eod_status=eod_status, fresh=freshness(d, eod_status),
                   cov=cov, last_backfill=last_backfill_job())
        return render("overview.html", ctx)

    # ---- 2. OHLCV history & chart -------------------------------------------------------------------------------
    def market_filters(c, d: dict, stocks: list[dict], t, f, to, sort, order) -> tuple[dict, list[str], dt.date | None, dt.date | None]:
        form = {"t": (t or "").strip().upper(), "f": f or "", "to": to or "", "sort": sort, "order": order}
        errors = []
        if form["t"] and not TICKER_RE.match(form["t"]):
            errors.append("Mã chỉ gồm 1–20 chữ cái/chữ số.")
        elif form["t"] and form["t"] not in {s["Ticker"] for s in stocks}:
            errors.append(f"{form['t']} không thuộc dataset {d['DatasetCode']}.")
        try:
            date_from, date_to = parse_date(f, "Từ ngày"), parse_date(to, "Đến ngày")
        except PageError as exc:
            errors.append(exc.message)
            date_from = date_to = None
        if floor and date_from and date_from < floor:
            errors.append(f"Chế độ LIVE chỉ lưu và hiển thị giá từ {floor.isoformat()} trở đi; chọn Từ ngày ≥ {floor.isoformat()}.")
        if floor and date_to and date_to < floor:
            errors.append(f"Đến ngày phải ≥ {floor.isoformat()} (sàn lịch sử của chế độ LIVE).")
        if date_from and date_to and date_from > date_to:
            errors.append("Từ ngày phải nhỏ hơn hoặc bằng Đến ngày.")
        if sort not in queries.PRICE_SORT or order not in ("asc", "desc"):
            errors.append("Tham số sắp xếp không hợp lệ.")
        return form, errors, date_from, date_to

    @app.get("/market", response_class=HTMLResponse)
    def market(request: Request, ds: str | None = None, t: str | None = None, f: str | None = None, to: str | None = None,
               sort: str = "date", order: str = "desc", page: str | None = None):
        with connect(settings) as c:
            ctx = base_context(request, c, "market", ds)
            d = ctx["ds"]
            stocks, _ = queries.stocks(c, d["DatasetId"], None, 500, 0)
            ctx["stocks"] = stocks
            form, errors, date_from, date_to = market_filters(c, d, stocks, t, f, to, sort, order)
            ctx["form"] = form
            pg = parse_int(page, "page", 1, 100000) or 1
            ctx["errors"] = errors
            ctx["source"] = source_info(d)
            if errors:
                return render("market.html", ctx, 422)
            if not form["t"]:
                first = next((s for s in stocks if s["PriceRows"]), None)
                form["t"] = first["Ticker"] if first else ""
            eff = {}
            if form["t"]:
                rng = queries.ticker_range(c, d["DatasetId"], form["t"], floor)
                last = dt.date.fromisoformat(rng["LastDate"]) if rng["LastDate"] else None
                first_d = dt.date.fromisoformat(rng["FirstDate"]) if rng["FirstDate"] else None
                defaulted = not (date_from or date_to)
                if defaulted and last:      # default view: the last 12 months of stored sessions
                    date_to, date_from = last, max(last - dt.timedelta(days=365), first_d)
                q_from = max(date_from, floor) if (date_from and floor) else (date_from or floor)
                pts = queries.price_series(c, d["DatasetId"], form["t"], q_from, date_to, 5000)
                items, total = queries.prices(c, d["DatasetId"], form["t"], q_from, date_to, sort, order == "desc", PAGE_SIZE, (pg - 1) * PAGE_SIZE)
                link = {"ds": d["DatasetId"], "t": form["t"], "sort": form["sort"], "order": form["order"]}
                presets = []
                for label, days in RANGE_PRESETS:
                    if not last:
                        break
                    pf = max(last - dt.timedelta(days=days), first_d) if days else first_d
                    href = "/market?" + urlencode({**link, "f": pf.isoformat(), "to": last.isoformat()})
                    presets.append({"label": label, "href": href, "active": bool(date_from == pf and date_to == last)})
                hits = [x for x in presets if x["active"]]
                for x in hits[:-1]:      # short histories map several presets to one range: highlight only the widest
                    x["active"] = False
                if date_from or first_d:
                    eff["f"] = (date_from or first_d).isoformat()
                if date_to or last:
                    eff["to"] = (date_to or last).isoformat()
                ctx.update(points=pts, rows=items, gaps=[x["TradeDate"] for x in pts if x["InCalendarWithoutPrice"]], rng=rng, presets=presets,
                           defaulted=defaulted, eff=eff,
                           export_href="/market/export.csv?" + urlencode({"ds": d["DatasetId"], "t": form["t"], **eff}),
                           pg=pager(total, pg, {"ds": d["DatasetId"], "t": form["t"], "f": form["f"] or eff.get("f"), "to": form["to"] or eff.get("to"),
                                                "sort": form["sort"], "order": form["order"]}),
                           chart_json={"ticker": form["t"], "datasetCode": d["DatasetCode"], "unit": d["PriceUnit"],
                                       "unitShort": short_unit(d["PriceUnit"]), "basis": d["PriceBasis"], "points": pts})
            sort_links = {}
            for key in queries.PRICE_SORT:
                nxt = "asc" if (sort == key and order == "desc") else "desc"
                sort_links[key] = "?" + urlencode({k: v for k, v in {"ds": d["DatasetId"], "t": form["t"], "f": form["f"] or eff.get("f"),
                                                                      "to": form["to"] or eff.get("to"), "sort": key, "order": nxt}.items() if v})
            ctx["sort_links"] = sort_links
        return render("market.html", ctx)

    def source_info(d: dict) -> dict:
        """Provenance line for the chart: dataset note + latest real backfill job (provider version and fetch time)."""
        info = {"note": d["ProvenanceNote"], "basis": d["PriceBasis"], "unit": d["PriceUnit"], "job": None, "provider": None}
        if not settings.is_demo:
            try:
                from .eod.backfill import job_detail, jobs as list_jobs
                done = [j for j in list_jobs(settings, limit=20) if not j["IsDryRun"] and j["Status"] in ("COMPLETED", "COMPLETED_WITH_GAPS")]
                if done:   # the job that loaded the widest window (a later partial rerun is not the main source)
                    done.sort(key=lambda j: ((j["SessionsPlanned"] or 0), j["JobId"]), reverse=True)
                    info["job"] = done[0]
                    info["provider"] = (job_detail(settings, done[0]["JobId"]) or {}).get("ProviderMeta")
            except (DatabaseUnavailable, SqlError):
                pass
        return info

    @app.get("/market/export.csv")
    def market_export(request: Request, ds: str | None = None, t: str | None = None, f: str | None = None, to: str | None = None):
        """CSV download of one ticker and date range (max 5,000 rows), same filters/floor as the page; not a data API."""
        import csv
        import io
        with connect(settings) as c:
            ctx = base_context(request, c, "market", ds)
            d = ctx["ds"]
            stocks, _ = queries.stocks(c, d["DatasetId"], None, 500, 0)
            form, errors, date_from, date_to = market_filters(c, d, stocks, t, f, to, "date", "asc")
            if not form["t"] and not errors:
                errors.append("Chọn mã cần xuất.")
            if errors:
                raise PageError(422, "INVALID_EXPORT", " ".join(errors))
            rng = queries.ticker_range(c, d["DatasetId"], form["t"], floor)
            lowest = floor or dt.date(1900, 1, 1)
            q_from = max(date_from or lowest, lowest)
            q_to = date_to or (dt.date.fromisoformat(rng["LastDate"]) if rng["LastDate"] else today_vn())
            rows = queries.export_prices(c, d["DatasetId"], form["t"], q_from, q_to, EXPORT_LIMIT + 1)
        if len(rows) > EXPORT_LIMIT:
            raise PageError(422, "EXPORT_TOO_LARGE", f"Tối đa {EXPORT_LIMIT} dòng mỗi lần xuất; thu hẹp khoảng ngày.")
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(["Ticker", "TradeDate", "Open", "High", "Low", "Close", "Volume", "DatasetCode", "PriceBasis", "Scope"])
        for r in rows:
            w.writerow([r["Ticker"], r["TradeDate"], r["OpenPrice"], r["HighPrice"], r["LowPrice"], r["ClosePrice"], r["Volume"],
                        d["DatasetCode"], d["PriceBasis"], ctx["mode_short"]])
        name = f"marketlab_{ctx['mode_short'].lower()}_{form['t']}_{q_from}_{q_to}.csv"
        notice = ("REAL_PRIVATE: du lieu rieng tu, quyen phan phoi nguon UNKNOWN - chi dung cuc bo, khong chia se"
                  if not settings.is_demo else "DEMO_OFFLINE: du lieu mo phong (synthetic)")
        return Response("\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{name}"', "X-MarketLab-Notice": notice})

    # ---- 3. forecasts & performance -----------------------------------------------------------------------------
    @app.get("/forecast", response_class=HTMLResponse)
    def forecast(request: Request, ds: str | None = None, as_of: str | None = None, run: str | None = None, t: str | None = None,
                 status: str | None = None, page: str | None = None):
        with connect(settings) as c:
            ctx = base_context(request, c, "forecast", ds)
            d = ctx["ds"]
            errors = []
            try:
                aso = parse_date(as_of, "as_of") or today_vn()
            except PageError as exc:
                errors.append(exc.message)
                aso = today_vn()
            tk = (t or "").strip().upper()
            if tk and not TICKER_RE.match(tk):
                errors.append("Mã chỉ gồm chữ cái/chữ số.")
            if status not in (None, "", "eligible", "pending", "missing_endpoint"):
                errors.append("Trạng thái không hợp lệ.")
            runs = queries.model_runs(c, d["DatasetId"])
            perf = {p["RunId"]: p for p in queries.performance(c, aso, d["DatasetId"])}
            run_id = parse_int(run, "run") or (runs[0]["RunId"] if runs else None)
            if run_id and not any(r["RunId"] == run_id for r in runs):
                raise PageError(404, "RUN_NOT_FOUND", f"Run {run_id} không thuộc dataset {d['DatasetCode']}")
            ctx.update(as_of=aso.isoformat(), runs=runs, perf=perf, run_id=run_id, errors=errors,
                       form={"t": tk, "status": status or ""}, total_eligible=sum(p["EvaluatedRows"] for p in perf.values()))
            if run_id and not errors:
                pg = parse_int(page, "page", 1, 100000) or 1
                items, total = queries.predictions(c, run_id, aso, tk or None, None, None, status or None, PAGE_SIZE, (pg - 1) * PAGE_SIZE)
                ctx.update(preds=items, run=next(r for r in runs if r["RunId"] == run_id),
                           pg=pager(total, pg, {"ds": d["DatasetId"], "as_of": aso.isoformat(), "run": run_id, "t": tk, "status": status}))
        return render("forecast.html", ctx, 422 if errors else 200)

    # ---- 4. model comparison -----------------------------------------------------------------------------------
    @app.get("/compare", response_class=HTMLResponse)
    def compare(request: Request, ds: str | None = None, f: str | None = None, to: str | None = None, as_of: str | None = None):
        run_ids_raw = request.query_params.getlist("runs")
        with connect(settings) as c:
            ctx = base_context(request, c, "compare", ds)
            d = ctx["ds"]
            runs = queries.model_runs(c, d["DatasetId"])
            firsts = sorted(r["FirstOrigin"] for r in runs if r["FirstOrigin"])
            lasts = sorted(r["LastOrigin"] for r in runs if r["LastOrigin"])
            form = {"f": f or (firsts[0] if firsts else ""), "to": to or (lasts[-1] if lasts else ""), "as_of": as_of or today_vn().isoformat(),
                    "runs": [int(x) for x in run_ids_raw if x.isdigit()] or [r["RunId"] for r in runs]}
            ctx.update(runs=runs, form=form, submitted=bool(run_ids_raw), errors=[], result=None)
            if run_ids_raw:
                ids = [int(x) for x in run_ids_raw if x.isdigit()]
                errs = ctx["errors"]
                if len(ids) != len(run_ids_raw) or len(set(ids)) != len(ids):
                    errs.append("Danh sách run không hợp lệ hoặc bị trùng.")
                if not 2 <= len(set(ids)) <= 8:
                    errs.append("Chọn từ 2 đến 8 run.")
                try:
                    df, dto, aso = parse_date(form["f"], "Ngày gốc từ"), parse_date(form["to"], "đến"), parse_date(form["as_of"], "as_of")
                except PageError as exc:
                    errs.append(exc.message)
                    df = dto = aso = None
                if df and dto and df > dto:
                    errs.append("Ngày gốc từ phải ≤ đến.")
                if not (df and dto and aso):
                    errs.append("Nhập đủ khoảng ngày gốc và as_of.")
                if errs:
                    return render("compare.html", ctx, 422)
                try:
                    res = queries.compare_runs(c, ids, df, dto, aso)
                except SqlError as exc:
                    status, code = SQL_ERROR_MAP.get(exc.number or 0, (500, f"SQL_{exc.number}"))
                    errs.append(f"{code}: {exc.message}")
                    return render("compare.html", ctx, status)
                ctx["result"] = res["rows"]
                ctx["targets"] = ", ".join(sorted({r["TargetCode"] for r in runs if r["RunId"] in ids}))
        return render("compare.html", ctx)

    # ---- 5. EOD operations --------------------------------------------------------------------------------------
    def csrf_for(request: Request) -> tuple[str, bool]:
        tok = request.cookies.get("ml_csrf", "")
        if re.fullmatch(r"[A-Za-z0-9_-]{32,64}", tok or ""):
            return tok, False
        return secrets.token_urlsafe(32), True

    def ops_context(request: Request, c, ds: str | None, status: str | None, page: str | None, run: str | None,
                    trigger: str | None = None) -> dict:
        ctx = base_context(request, c, "ops", ds)
        d = ctx["ds"]
        ctx["calendar"] = None
        universe_ids = None
        if ctx["eod"]["enabled"]:
            cfg = ctx["eod"]["config"][0]
            universe_ids = [u["StockId"] for u in queries.universe(c, d["DatasetId"], cfg["IndexCode"], dt.date.fromisoformat(str(cfg["UniverseAsOf"])))]
        ctx["calendar"] = queries.calendar_check(c, d["DatasetId"], universe_ids, None, None, 30)
        ctx["universe_source"] = "ops.EodConfig index snapshot" if universe_ids else "mọi mã cùng thị trường & loại dữ liệu"
        if status not in (None, "", "SUCCESS", "DRY_RUN_OK", "NO_SESSION", "SKIPPED", "PARTIAL", "FAILED", "RUNNING"):
            raise PageError(422, "INVALID_STATUS", "Trạng thái lọc không hợp lệ")
        ctx["status_filter"] = status or ""
        if ctx["eod"]["enabled"]:
            pg = parse_int(page, "page", 1, 100000) or 1
            include_bf = trigger == "all"
            ctx["trigger_filter"] = "all" if include_bf else ""
            items, total = ops.runs(d["DatasetId"], 15, (pg - 1) * 15, status or None, include_backfill=include_bf)
            pages = max(1, math.ceil(total / 15))
            mk = lambda p: "?" + urlencode({k: v for k, v in {"ds": d["DatasetId"], "status": status, "trigger": "all" if include_bf else None,  # noqa: E731
                                                              "page": p}.items() if v})
            ctx.update(last=ops.last_status(d["DatasetId"]), runs=items,
                       ops_pager={"total": total, "from": (pg - 1) * 15 + 1 if total else 0, "to": min(total, pg * 15),
                                  "prev": mk(pg - 1) if pg > 1 else None, "next": mk(pg + 1) if pg < pages else None},
                       recon=ops.reconciliation(d["DatasetId"], None, 50))
            rid = parse_int(run, "run")
            if rid:
                detail = ops.run_detail(rid)
                if not detail:
                    raise PageError(404, "EOD_RUN_NOT_FOUND", f"Không có run EOD #{rid} cho database này")
                ctx["detail"] = detail
            with connect(settings) as c2:
                ctx["last_price_date"] = query(c2, "SELECT MAX(TradeDate) AS d FROM dbo.DailyPrice WHERE DatasetId=?", (d["DatasetId"],))[0]["d"]
        return ctx

    def with_csrf_cookie(resp: HTMLResponse, token: str, new: bool) -> HTMLResponse:
        if new:
            resp.set_cookie("ml_csrf", token, httponly=True, samesite="strict", path="/", max_age=8 * 3600)
        return resp

    @app.get("/ops", response_class=HTMLResponse)
    def ops_page(request: Request, ds: str | None = None, status: str | None = None, page: str | None = None, run: str | None = None,
                 trigger: str | None = None):
        if trigger not in (None, "", "all"):
            raise PageError(422, "INVALID_TRIGGER", "Bộ lọc nguồn kích hoạt không hợp lệ")
        with connect(settings) as c:
            ctx = ops_context(request, c, ds, status, page, run, trigger)
        token, new = csrf_for(request)
        ctx.update(csrf=token, form_date=today_vn().isoformat(), action_error=None)
        return with_csrf_cookie(render("ops.html", ctx), token, new)

    def check_write(request: Request, form: dict) -> tuple[int, str] | None:
        """Common gate of every server-side write action: CSRF, mode, token configured, lockout, token."""
        cookie = request.cookies.get("ml_csrf", "")
        if not cookie or not hmac.compare_digest(cookie.encode(), form.get("csrf", "").encode()):
            return 403, "CSRF_FAILED: phiên biểu mẫu không hợp lệ hoặc đã hết hạn; tải lại trang rồi thử lại."
        if settings.is_demo:
            return 409, "MODE_DEMO_OFFLINE: không ghi dữ liệu thật vào CSDL mô phỏng."
        if not settings.ops_token:
            return 503, "OPS_TOKEN_NOT_CONFIGURED: chưa cấu hình MARKETLAB_OPS_TOKEN; thao tác ghi bị tắt."
        if guard.locked():
            return 429, "TOO_MANY_AUTH_FAILURES: đã nhập sai token quá 5 lần, chờ 10 phút."
        if not hmac.compare_digest(form.get("ops_token", "").encode(), settings.ops_token.encode()):
            guard.fail()
            return 401, "INVALID_OPS_TOKEN: token sai hoặc thiếu (MARKETLAB_OPS_TOKEN trong .env trên máy chủ)."
        return None

    def any_job_running() -> bool:
        return any(j["state"] == "RUNNING" for j in list(jobs.values()) + list(bjobs.values()))

    @app.post("/ops/eod", response_class=HTMLResponse)
    async def ops_eod(request: Request):
        raw = (await request.body())[:4096].decode("utf-8", "replace")
        form = {k: v[0] for k, v in parse_qs(raw, keep_blank_values=True).items()}
        ds = form.get("ds")

        def refuse(status: int, message: str):
            with connect(settings) as c:
                ctx = ops_context(request, c, ds, None, None, None)
            token, new = csrf_for(request)
            ctx.update(csrf=token, form_date=form.get("session_date") or today_vn().isoformat(), action_error=message)
            return with_csrf_cookie(render("ops.html", ctx, status), token, new)

        bad = check_write(request, form)
        if bad:
            return refuse(*bad)
        action = form.get("action")
        if action not in ("DRY_RUN", "SYNC"):
            return refuse(422, "INVALID_ACTION: chọn Dry run hoặc Sync.")
        if action == "SYNC" and form.get("confirm_sync") != "yes":
            return refuse(422, "CONFIRMATION_REQUIRED: tích ô xác nhận trước khi ghi thật.")
        try:
            session = dt.date.fromisoformat(form.get("session_date", ""))
        except ValueError:
            return refuse(422, "INVALID_DATE: ngày phiên phải có dạng YYYY-MM-DD.")
        with job_lock:
            if any_job_running():
                return refuse(409, "JOB_ALREADY_RUNNING: một job EOD/backfill khác đang chạy.")
            if time.monotonic() - guard.last_job_start < 5:
                return refuse(429, "RATE_LIMITED: chờ vài giây giữa hai job.")
            guard.last_job_start = time.monotonic()
            for old in [k for k, v in jobs.items() if v["state"] != "RUNNING"][:-49]:
                jobs.pop(old, None)
            job_id = uuid.uuid4().hex
            jobs[job_id] = {"job_id": job_id, "state": "RUNNING", "session_date": session.isoformat(), "dry_run": action == "DRY_RUN",
                            "ds": ds, "started": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "result": None, "error": None}

        def work():
            try:
                res = make_service().sync_session(session, None, action == "DRY_RUN")
                jobs[job_id].update(state="DONE", result=res.to_dict())
            except EodSetupError as exc:
                jobs[job_id].update(state="ERROR", error=f"EOD_SETUP: {exc}")
            except Exception as exc:  # noqa: BLE001
                log.exception("EOD job failed")
                jobs[job_id].update(state="ERROR", error=f"INTERNAL_ERROR: {type(exc).__name__}")

        threading.Thread(target=work, name=f"eod-{job_id[:8]}", daemon=True).start()
        return RedirectResponse(f"/ops/jobs/{job_id}?ds={ds or ''}", status_code=303)

    @app.get("/ops/jobs/{job_id}", response_class=HTMLResponse)
    def ops_job(request: Request, job_id: str, ds: str | None = None):
        if not re.fullmatch(r"[0-9a-f]{32}", job_id) or job_id not in jobs:
            raise PageError(404, "JOB_NOT_FOUND", "Không tìm thấy job (job chỉ tồn tại trong tiến trình server hiện tại)")
        with connect(settings) as c:
            ctx = base_context(request, c, "ops", ds)
        ctx["job"] = jobs[job_id]
        return render("ops_job.html", ctx)

    # ---- 6. historical backfill ------------------------------------------------------------------------------------
    def backfill_context(request: Request, c, ds: str | None, job: str | None) -> dict:
        ctx = base_context(request, c, "backfill", ds)
        d = ctx["ds"]
        ctx.update(bf_jobs=[], bf_job=None, bf_cov=None, bf_enabled=False, bf_reason=None)
        if settings.is_demo:
            ctx["bf_reason"] = "DEMO_OFFLINE dùng CSDL mô phỏng: không nạp dữ liệu thị trường thật vào chế độ này."
        elif not ctx["eod"]["enabled"]:
            ctx["bf_reason"] = ctx["eod"]["reason"]
        else:
            from .eod.backfill import job_detail, jobs as list_jobs
            try:
                ctx["bf_jobs"] = list_jobs(settings, limit=15)
                ctx["bf_enabled"] = True
            except SqlError as exc:
                ctx["bf_reason"] = f"Ops database chưa có schema v3 (sql/16_ops_schema_v3_backfill.sql): SQL {exc.number}"
            jid = parse_int(job, "job")
            if ctx["bf_enabled"]:
                if jid is None:
                    real = sorted((j for j in ctx["bf_jobs"] if not j["IsDryRun"]),   # main job = widest real window, then newest
                                  key=lambda j: ((j["SessionsPlanned"] or 0), j["JobId"]), reverse=True)
                    jid = (real or ctx["bf_jobs"] or [{}])[0].get("JobId")
                if jid:
                    ctx["bf_job"] = job_detail(settings, jid)
                    if ctx["bf_job"] is None:
                        raise PageError(404, "BACKFILL_JOB_NOT_FOUND", f"Không có job backfill #{jid} cho database này")
        ctx["ticker_cov"] = queries.ticker_coverage(c, d["DatasetId"], floor)
        ctx["cov"] = queries.coverage_summary(c, d["DatasetId"], floor)
        ctx["running"] = [j for j in bjobs.values() if j["state"] == "RUNNING"]
        return ctx

    @app.get("/backfill", response_class=HTMLResponse)
    def backfill_page(request: Request, ds: str | None = None, job: str | None = None):
        with connect(settings) as c:
            ctx = backfill_context(request, c, ds, job)
        token, new = csrf_for(request)
        ctx.update(csrf=token, action_error=None, bf_form={"start": (floor or settings.history_start).isoformat(), "end": "latest", "tickers": ""})
        return with_csrf_cookie(render("backfill.html", ctx), token, new)

    @app.post("/backfill/run", response_class=HTMLResponse)
    async def backfill_run(request: Request):
        raw = (await request.body())[:4096].decode("utf-8", "replace")
        form = {k: v[0] for k, v in parse_qs(raw, keep_blank_values=True).items()}
        ds = form.get("ds")
        bf_form = {"start": form.get("start_date", ""), "end": form.get("end_date", "latest") or "latest", "tickers": form.get("tickers", "")}

        def refuse(status: int, message: str):
            with connect(settings) as c:
                ctx = backfill_context(request, c, ds, None)
            token, new = csrf_for(request)
            ctx.update(csrf=token, action_error=message, bf_form=bf_form)
            return with_csrf_cookie(render("backfill.html", ctx, status), token, new)

        bad = check_write(request, form)
        if bad:
            return refuse(*bad)
        action = form.get("action")
        if action not in ("DRY_RUN", "RUN", "RESUME", "RESUME_DRY"):
            return refuse(422, "INVALID_ACTION: chọn Dry run, Backfill hoặc Tiếp tục job.")
        if action in ("RUN", "RESUME") and form.get("confirm_write") != "yes":
            return refuse(422, "CONFIRMATION_REQUIRED: tích ô xác nhận trước khi ghi thật (backup được tạo và xác minh tự động trước khi ghi).")
        try:
            start = dt.date.fromisoformat(bf_form["start"]) if bf_form["start"] else settings.history_start
        except ValueError:
            return refuse(422, "INVALID_DATE: Từ ngày phải có dạng YYYY-MM-DD.")
        if start < settings.history_start:
            return refuse(422, f"BEFORE_HISTORY_START: chỉ nạp dữ liệu từ {settings.history_start.isoformat()} trở đi.")
        end = bf_form["end"].strip()
        if end != "latest" and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", end):
            return refuse(422, "INVALID_DATE: Đến ngày là 'latest' hoặc YYYY-MM-DD.")
        tickers = [x.strip().upper() for x in re.split(r"[,\s;]+", bf_form["tickers"]) if x.strip()]
        if any(not TICKER_RE.match(x) for x in tickers) or len(tickers) > 60:
            return refuse(422, "INVALID_TICKERS: danh sách mã cách nhau bằng dấu phẩy (tối đa 60 mã).")
        if tickers:
            with connect(settings) as c:
                cfg = eod_info()["config"]
                names = {u["Ticker"] for u in queries.universe(c, cfg[0]["DatasetId"], cfg[0]["IndexCode"],
                                                                dt.date.fromisoformat(str(cfg[0]["UniverseAsOf"])))} if cfg else set()
            unknown = [x for x in tickers if x not in names]
            if unknown:
                return refuse(422, f"INVALID_TICKERS: không thuộc universe được cấu hình: {', '.join(unknown[:10])}.")
        with job_lock:
            if any_job_running():
                return refuse(409, "JOB_ALREADY_RUNNING: một job EOD/backfill khác đang chạy trong tiến trình này.")
            if time.monotonic() - guard.last_job_start < 5:
                return refuse(429, "RATE_LIMITED: chờ vài giây giữa hai job.")
            guard.last_job_start = time.monotonic()
            wid = uuid.uuid4().hex
            bjobs[wid] = {"job_id": wid, "state": "RUNNING", "action": action, "dry_run": action in ("DRY_RUN", "RESUME_DRY"),
                          "start": start.isoformat(), "end": end, "tickers": tickers, "ds": ds, "progress": [],
                          "started": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "result": None, "error": None}

        def progress(msg: str):
            log_ = bjobs[wid]["progress"]
            log_.append(f"{dt.datetime.now(dt.timezone.utc):%H:%M:%S} {msg}"[:300])
            del log_[:-40]

        def work():
            from .eod.backfill import BackfillError
            try:
                svc = make_backfill(progress)
                resume = action in ("RESUME", "RESUME_DRY")
                res = svc.run(None if resume else start, end, tickers or None, bjobs[wid]["dry_run"], resume)
                bjobs[wid].update(state="DONE", result=res)
            except BackfillError as exc:
                bjobs[wid].update(state="ERROR", error=f"{exc.code}: {exc.message}"[:600])
            except Exception as exc:  # noqa: BLE001
                log.exception("backfill job failed")
                bjobs[wid].update(state="ERROR", error=f"INTERNAL_ERROR: {type(exc).__name__}")

        threading.Thread(target=work, name=f"backfill-{wid[:8]}", daemon=True).start()
        return RedirectResponse(f"/backfill/jobs/{wid}?ds={ds or ''}", status_code=303)

    @app.get("/backfill/jobs/{wid}", response_class=HTMLResponse)
    def backfill_job(request: Request, wid: str, ds: str | None = None):
        if not re.fullmatch(r"[0-9a-f]{32}", wid) or wid not in bjobs:
            raise PageError(404, "JOB_NOT_FOUND", "Không tìm thấy job (job web chỉ tồn tại trong tiến trình server hiện tại; xem bảng job trên trang Backfill)")
        with connect(settings) as c:
            ctx = base_context(request, c, "backfill", ds)
        ctx["wjob"] = bjobs[wid]
        if not settings.is_demo:
            from .eod.backfill import jobs as list_jobs
            ctx["db_job"] = (list_jobs(settings, limit=1) or [None])[0]
        return render("backfill_job.html", ctx)

    # ---- static -------------------------------------------------------------------------------------------------
    app.mount("/static", StaticFiles(directory=PKG / "web"), name="static")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return FileResponse(PKG / "web" / "favicon.svg", media_type="image/svg+xml")

    @app.exception_handler(404)
    async def not_found(request: Request, exc):
        return error_page(request, 404, "NOT_FOUND", f"Không có trang {request.url.path}")

    @app.exception_handler(405)
    async def not_allowed(request: Request, exc):
        return error_page(request, 405, "METHOD_NOT_ALLOWED", "Phương thức không được hỗ trợ")

    app.state.jobs = jobs
    app.state.backfill_jobs = bjobs
    app.state.chart_json = json.dumps
    return app
