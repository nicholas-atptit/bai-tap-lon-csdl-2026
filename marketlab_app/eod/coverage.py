"""Coverage / QA of stored OHLCV (read-only). Counts, dates and hashes only: no price value leaves the database.

Session calendar = provider reference sessions staged by the backfill job (weekends/holidays are not sessions);
falls back to dbo.TradingDay when no job exists. Expected sessions of a ticker start at its first provider candle
(earlier sessions are reported as NO_HISTORY, not as missing).
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from .. import queries
from ..config import DB_NAME_RE, ROOT, Settings
from ..db import connect, query

JUMP_LIMIT = 0.075     # HOSE daily band is +-7% of the reference price; larger close-to-close moves are flagged for review


def table_hash(settings: Settings, dataset_id: int, start: dt.date, end: dt.date) -> dict:
    with connect(settings) as c:
        r = query(c, """SELECT COUNT_BIG(*) AS n,
                          CONVERT(char(64),HASHBYTES('SHA2_256',STRING_AGG(CONVERT(nvarchar(max),CONCAT(StockId,'|',TradeDate,'|',OpenPrice,'|',HighPrice,'|',
                            LowPrice,'|',ClosePrice,'|',Volume)),N';') WITHIN GROUP (ORDER BY StockId,TradeDate)),2) AS values_sha256,
                          CONVERT(char(64),HASHBYTES('SHA2_256',STRING_AGG(CONVERT(nvarchar(max),CONCAT(StockId,'|',TradeDate,'|',CONVERT(varchar(30),LoadedAt,126))),N';')
                            WITHIN GROUP (ORDER BY StockId,TradeDate)),2) AS loadedat_sha256
                        FROM dbo.DailyPrice WHERE DatasetId=? AND TradeDate BETWEEN ? AND ?""", (dataset_id, start, end))[0]
    return r


def coverage(settings: Settings, start: dt.date | None = None, end: dt.date | None = None, job_id: int | None = None) -> dict:
    ops_db = settings.ops_database
    if not DB_NAME_RE.match(ops_db):
        raise ValueError("unsafe ops database name")
    with connect(settings, ops_db) as c:
        cfg = query(c, "SELECT * FROM ops.EodConfig WHERE DatabaseName=? AND Enabled=1", (settings.sql_database,))
        if not cfg:
            raise ValueError(f"no ops.EodConfig for {settings.sql_database}")
        cfg = cfg[0]
        if job_id is None:
            j = query(c, """SELECT TOP 1 JobId FROM ops.BackfillJob WHERE DatabaseName=? AND DatasetId=? AND IsDryRun=0
                             AND Status IN ('COMPLETED','COMPLETED_WITH_GAPS') ORDER BY JobId DESC""", (settings.sql_database, cfg["DatasetId"]))
            job_id = j[0]["JobId"] if j else None
        job = query(c, "SELECT * FROM ops.BackfillJob WHERE JobId=?", (job_id,))[0] if job_id else None
        start = start or (dt.date.fromisoformat(job["StartDate"]) if job else settings.history_start)
        end = end or (dt.date.fromisoformat(job["EndDate"]) if job else dt.date.today())
        # calendar of the job = every session it planned (reference candle or majority of stock candles), see backfill.py
        cal = [dt.date.fromisoformat(r["SessionDate"]) for r in query(c, """SELECT SessionDate FROM ops.BackfillSession WHERE JobId=?
                AND SessionDate BETWEEN ? AND ? ORDER BY SessionDate""", (job_id, start, end))] if job else []
        cal_evidence = query(c, """SELECT SUBSTRING(Message, 11, CHARINDEX(']', Message) - 11) AS Evidence, COUNT(*) AS n FROM ops.BackfillSession
                              WHERE JobId=? AND LEFT(Message, 10)='[calendar ' GROUP BY SUBSTRING(Message, 11, CHARINDEX(']', Message) - 11)""",
                             (job_id,)) if job else []
        first_provider = {r["Ticker"]: r["FirstDate"] for r in query(c, """SELECT Ticker, MIN(FirstDate) AS FirstDate FROM ops.BackfillFetch
                           WHERE JobId=? AND IsReference=0 GROUP BY Ticker""", (job_id,))} if job else {}
        fetch_failed = query(c, "SELECT COUNT(*) AS n FROM ops.BackfillFetch WHERE JobId=? AND Status='FAILED'", (job_id,))[0]["n"] if job else None
        recon = query(c, """SELECT Status, COUNT(*) AS n FROM ops.PriceReconciliation WHERE DatabaseName=? AND DatasetId=? GROUP BY Status""",
                      (settings.sql_database, cfg["DatasetId"]))
        rejects = query(c, "SELECT Code, COUNT(*) AS n FROM ops.BackfillReject WHERE JobId=? GROUP BY Code", (job_id,)) if job else []
    dataset_id = cfg["DatasetId"]
    with connect(settings) as c:
        ds = queries.dataset_exists(c, dataset_id)
        uni = queries.universe(c, dataset_id, cfg["IndexCode"], dt.date.fromisoformat(str(cfg["UniverseAsOf"])))
        if not cal:
            cal = [dt.date.fromisoformat(r["TradeDate"]) for r in query(c, "SELECT TradeDate FROM dbo.TradingDay WHERE DatasetId=? AND TradeDate BETWEEN ? AND ? ORDER BY TradeDate",
                                                                        (dataset_id, start, end))]
        stored = {}
        for r in query(c, "SELECT StockId, TradeDate FROM dbo.DailyPrice WHERE DatasetId=? AND TradeDate BETWEEN ? AND ?", (dataset_id, start, end)):
            stored.setdefault(r["StockId"], set()).add(dt.date.fromisoformat(r["TradeDate"]))
        totals = query(c, f"""SELECT
            (SELECT COUNT_BIG(*) FROM dbo.DailyPrice WHERE DatasetId=?) AS rows_all,
            (SELECT COUNT_BIG(*) FROM dbo.DailyPrice WHERE DatasetId=? AND TradeDate BETWEEN ? AND ?) AS rows_window,
            (SELECT COUNT_BIG(*) FROM dbo.DailyPrice WHERE DatasetId=? AND TradeDate<?) AS rows_before_floor,
            (SELECT MIN(TradeDate) FROM dbo.DailyPrice WHERE DatasetId=?) AS min_date,
            (SELECT MAX(TradeDate) FROM dbo.DailyPrice WHERE DatasetId=?) AS max_date,
            (SELECT COUNT(DISTINCT TradeDate) FROM dbo.DailyPrice WHERE DatasetId=? AND TradeDate BETWEEN ? AND ?) AS sessions_with_prices,
            (SELECT COUNT(*) FROM dbo.TradingDay WHERE DatasetId=? AND TradeDate BETWEEN ? AND ?) AS trading_days,
            (SELECT COUNT(*) FROM dbo.TradingDay WHERE DatasetId=? AND TradeDate<?) AS trading_days_before_floor,
            (SELECT COUNT(*) FROM (SELECT 1 AS x FROM dbo.DailyPrice WHERE DatasetId=? GROUP BY StockId,TradeDate HAVING COUNT(*)>1) d) AS duplicate_keys,
            (SELECT COUNT_BIG(*) FROM dbo.DailyPrice WHERE DatasetId=? AND NOT (OpenPrice>0 AND ClosePrice>0 AND LowPrice>0 AND HighPrice>=OpenPrice
               AND HighPrice>=ClosePrice AND HighPrice>=LowPrice AND LowPrice<=OpenPrice AND LowPrice<=ClosePrice AND Volume>=0)) AS ohlc_violations,
            (SELECT COUNT_BIG(*) FROM dbo.DailyPrice p WHERE p.DatasetId=? AND NOT EXISTS(SELECT 1 FROM dbo.TradingDay t WHERE t.DatasetId=p.DatasetId AND t.TradeDate=p.TradeDate)) AS rows_outside_calendar,
            (SELECT COUNT_BIG(*) FROM dbo.DailyPrice p WHERE p.DatasetId=? AND p.TradeDate BETWEEN ? AND ? AND NOT EXISTS(
               SELECT 1 FROM [{ops_db}].ops.PriceLoadLineage l WHERE l.DatabaseName=DB_NAME() AND l.DatasetId=p.DatasetId AND l.StockId=p.StockId AND l.TradeDate=p.TradeDate)) AS rows_without_lineage,
            (SELECT COUNT(*) FROM dbo.TradingDay WHERE DatasetId=? AND DATEPART(weekday,TradeDate) IN (1,7)) AS weekend_trading_days
            """, (dataset_id, dataset_id, start, end, dataset_id, settings.history_start, dataset_id, dataset_id, dataset_id, start, end,
                  dataset_id, start, end, dataset_id, settings.history_start, dataset_id, dataset_id, dataset_id, dataset_id, start, end, dataset_id))[0]
        jumps = {r["StockId"]: r for r in query(c, """WITH x AS (SELECT StockId, TradeDate, ClosePrice,
                    LAG(ClosePrice) OVER (PARTITION BY StockId ORDER BY TradeDate) AS prev FROM dbo.DailyPrice WHERE DatasetId=? AND TradeDate BETWEEN ? AND ?)
                    SELECT StockId, SUM(CASE WHEN prev IS NOT NULL AND ABS(ClosePrice/prev-1)>? THEN 1 ELSE 0 END) AS jumps,
                           SUM(CASE WHEN prev IS NOT NULL AND ABS(ClosePrice/prev-1)>0.15 THEN 1 ELSE 0 END) AS big_jumps,
                           MIN(CASE WHEN prev IS NOT NULL AND ABS(ClosePrice/prev-1)>? THEN TradeDate END) AS first_jump
                    FROM x GROUP BY StockId""", (dataset_id, start, end, JUMP_LIMIT, JUMP_LIMIT))}
        per_year = query(c, """SELECT YEAR(TradeDate) AS y, COUNT(DISTINCT TradeDate) AS sessions, COUNT_BIG(*) AS rows FROM dbo.DailyPrice
                               WHERE DatasetId=? AND TradeDate BETWEEN ? AND ? GROUP BY YEAR(TradeDate) ORDER BY y""", (dataset_id, start, end))
    cal_set = set(cal)
    per_ticker = []
    for u in uni:
        have = stored.get(u["StockId"], set())
        fp = first_provider.get(u["Ticker"])
        fpd = dt.date.fromisoformat(fp) if fp else None
        if job and fpd is None:
            expected, nohist = [], [d for d in cal]
        else:
            expected = [d for d in cal if fpd is None or d >= fpd]
            nohist = [d for d in cal if fpd is not None and d < fpd]
        missing = [d for d in expected if d not in have]
        j = jumps.get(u["StockId"], {})
        per_ticker.append({"ticker": u["Ticker"], "rows": len(have & cal_set), "rows_outside_provider_calendar": len(have - cal_set),
                           "first_stored": min(have).isoformat() if have else None, "last_stored": max(have).isoformat() if have else None,
                           "first_provider_candle": fp, "expected_sessions": len(expected), "missing_sessions": len(missing),
                           "missing_dates_sample": [d.isoformat() for d in missing[:8]], "no_history_sessions": len(nohist),
                           "jumps_gt_7_5pct": int(j.get("jumps") or 0), "jumps_gt_15pct": int(j.get("big_jumps") or 0),
                           "first_jump_date": j.get("first_jump")})
    missing_total = sum(t["missing_sessions"] for t in per_ticker)
    nohist_total = sum(t["no_history_sessions"] for t in per_ticker)
    full = missing_total == 0 and nohist_total == 0 and (fetch_failed or 0) == 0
    return {"generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "database": settings.sql_database,
            "dataset": {"DatasetId": dataset_id, "PriceBasis": ds["PriceBasis"], "PriceUnit": ds["PriceUnit"], "ObservedThrough": ds["ObservedThrough"]},
            "universe": {"index": cfg["IndexCode"], "as_of": str(cfg["UniverseAsOf"]), "size": len(uni),
                         "label": f"{len(uni)} mã thuộc universe được cấu hình (tham chiếu VN30 {str(cfg['UniverseAsOf'])[:7]}), không phải thành phần VN30 lịch sử"},
            "window": {"start": start.isoformat(), "end": end.isoformat(), "history_floor": settings.history_start.isoformat()},
            "calendar": {"source": (f"phiên của backfill job {job['JobRef']}: ngày có nến {cfg['CalendarReferenceSymbol']} hoặc có nến của ≥ 50% mã"
                                    if job else "dbo.TradingDay"), "evidence": {r["Evidence"]: r["n"] for r in cal_evidence},
                         "sessions": len(cal), "first": cal[0].isoformat() if cal else None, "last": cal[-1].isoformat() if cal else None},
            "totals": totals, "per_year": per_year, "per_ticker": per_ticker,
            "missing_sessions_total": missing_total, "no_history_sessions_total": nohist_total,
            "coverage_status": "FULL_COVERAGE" if full else "PARTIAL_COVERAGE",
            "job": ({k: job[k] for k in ("JobId", "JobRef", "Status", "StartDate", "EndDate", "EndDateSpec", "IsDryRun", "SessionsPlanned", "SessionsProcessed",
                                         "RowsInserted", "RowsUnchanged", "RowsMissing", "RowsNoHistory", "RowsRejected", "ConflictCount", "FetchCalls",
                                         "FetchRetries", "ResumeCount", "CreatedAtUtc", "FinishedAtUtc", "BackupVerifiedAtUtc")}
                    | {"ProviderMeta": json.loads(job["ProviderMeta"]) if job.get("ProviderMeta") else None,
                       "BackupFiles": [Path(x.strip()).name for x in (job.get("BackupFile") or "").split(";") if x.strip()]}) if job else None,
            "fetch_failed_chunks": fetch_failed, "rejects_by_code": rejects, "reconciliation_by_status": recon,
            "hash_window": table_hash(settings, dataset_id, start, end)}


def write_reports(cov: dict, md_path: Path, extra_sections: list[str] | None = None) -> tuple[Path, Path]:
    out_json = ROOT / "var" / "reports" / f"coverage_{cov['generated_at_utc'][:19].replace(':', '')}.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(cov, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    md_path.write_text(render_markdown(cov, extra_sections), encoding="utf-8")
    return md_path, out_json


def render_markdown(cov: dict, extra_sections: list[str] | None = None) -> str:
    t, j, w = cov["totals"], cov.get("job") or {}, cov["window"]
    pm = j.get("ProviderMeta") or {}
    lines = [
        "# Báo cáo backfill OHLCV lịch sử – MarketLab VN30 (REAL_PRIVATE)", "",
        f"Sinh tự động bởi `python -m marketlab_app.cli backfill report` lúc {cov['generated_at_utc']} (UTC). "
        "Chỉ chứa số đếm, ngày và hash; **không chứa giá**, token, mật khẩu hay chuỗi kết nối. Dữ liệu giá nằm trong SQL Server cục bộ "
        f"(`{cov['database']}`), không đưa lên GitHub (quyền phân phối dữ liệu nguồn: UNKNOWN).", "",
        "## 1. Phạm vi", "",
        "| Mục | Giá trị |", "|---|---|",
        f"| Universe | {cov['universe']['label']} |",
        f"| Cửa sổ yêu cầu | {w['start']} → {w['end']} (sàn lịch sử {w['history_floor']}; EndDate spec `{j.get('EndDateSpec', '—')}`) |",
        f"| Lịch phiên | {cov['calendar']['source']}: **{cov['calendar']['sessions']} phiên**, {cov['calendar']['first']} → {cov['calendar']['last']} "
        f"(bằng chứng: {', '.join(f'{k}: {v}' for k, v in cov['calendar'].get('evidence', {}).items()) or '—'}) |",
        f"| Khoảng dữ liệu thực tế đã lưu | MIN(TradeDate) = {t['min_date']}, MAX(TradeDate) = {t['max_date']} |",
        f"| Nguồn | KBS qua vnstock {pm.get('package_version', '—')} (bridge subprocess), lấy lúc {pm.get('called_utc', '—')} UTC |",
        f"| Quy ước giá | PriceBasis `{cov['dataset']['PriceBasis']}`: giá nguồn như KBS trả về tại thời điểm tải (KBS điều chỉnh hồi tố theo sự kiện doanh nghiệp; không phải total return). Đơn vị: {cov['dataset']['PriceUnit']} |",
        f"| ObservedThrough | {cov['dataset']['ObservedThrough']} |", "",
        "## 2. Kết quả nạp", "",
        "| Chỉ số | Giá trị |", "|---|---|",
        f"| Job | `{j.get('JobRef', '—')}` · trạng thái **{j.get('Status', '—')}** · resume {j.get('ResumeCount', 0)} lần |",
        f"| Số mã xử lý | {cov['universe']['size']} |",
        f"| Phiên đã xử lý / kế hoạch | {j.get('SessionsProcessed', '—')} / {j.get('SessionsPlanned', '—')} |",
        f"| Dòng thêm mới (INSERTED) | {j.get('RowsInserted', '—')} |",
        f"| Dòng bỏ qua vì đã có, cùng giá trị (UNCHANGED) | {j.get('RowsUnchanged', '—')} |",
        f"| Mã-phiên thiếu (MISSING) | {j.get('RowsMissing', '—')} |",
        f"| Mã-phiên trước lịch sử nguồn (NO_HISTORY) | {j.get('RowsNoHistory', '—')} |",
        f"| Dòng nguồn bị từ chối khi validate | {j.get('RowsRejected', '—')} ({', '.join(f'{r['Code']}: {r['n']}' for r in cov['rejects_by_code']) or 'không có'}) |",
        f"| Xung đột giá (cần đối soát) | {j.get('ConflictCount', '—')} · hàng đợi: {', '.join(f'{r['Status']}: {r['n']}' for r in cov['reconciliation_by_status']) or 'trống'} |",
        f"| Lần gọi provider / retry | {j.get('FetchCalls', '—')} / {j.get('FetchRetries', '—')} · chunk tải lỗi còn lại: {cov['fetch_failed_chunks']} |",
        f"| Backup trước khi ghi | {', '.join(j.get('BackupFiles') or []) or '—'} (xác minh {j.get('BackupVerifiedAtUtc', '—')} UTC) |",
        f"| Thời gian job | {j.get('CreatedAtUtc', '—')} → {j.get('FinishedAtUtc', '—')} UTC |", "",
        "## 3. Kiểm tra toàn vẹn trên SQL Server", "",
        "| Kiểm tra | Kết quả |", "|---|---|",
        f"| Tổng dòng OHLCV của dataset | {t['rows_all']} (trong cửa sổ: {t['rows_window']}) |",
        f"| Phiên có giá trong cửa sổ / dbo.TradingDay | {t['sessions_with_prices']} / {t['trading_days']} |",
        f"| Dòng giá TradeDate < {w['history_floor']} | {t['rows_before_floor']} (TradingDay: {t['trading_days_before_floor']}) |",
        f"| Khóa trùng (DatasetId, StockId, TradeDate) | {t['duplicate_keys']} |",
        f"| Vi phạm OHLC/Volume | {t['ohlc_violations']} |",
        f"| Dòng giá ngoài lịch dbo.TradingDay | {t['rows_outside_calendar']} |",
        f"| TradingDay rơi vào thứ Bảy/Chủ Nhật | {t['weekend_trading_days']} |",
        f"| Dòng trong cửa sổ chưa có lineage (ops.PriceLoadLineage) | {t['rows_without_lineage']} |",
        f"| SHA-256 giá trị (StockId, TradeDate, OHLCV) | `{cov['hash_window']['values_sha256']}` ({cov['hash_window']['n']} dòng) |",
        f"| SHA-256 LoadedAt | `{cov['hash_window']['loadedat_sha256']}` |",
        f"| **Độ phủ** | **{cov['coverage_status']}**: {cov['missing_sessions_total']} mã-phiên thiếu, {cov['no_history_sessions_total']} mã-phiên trước lịch sử nguồn |", "",
        "### Theo năm", "", "| Năm | Phiên có giá | Dòng OHLCV |", "|---|---|---|",
        *[f"| {r['y']} | {r['sessions']} | {r['rows']} |" for r in cov["per_year"]], "",
        "## 4. Độ phủ theo mã", "",
        "Phiên kỳ vọng của một mã = các phiên của lịch tham chiếu kể từ nến đầu tiên mà nguồn có cho mã đó. "
        f"Biến động Close liên tiếp > {JUMP_LIMIT:.1%} (biên độ HOSE ±7%) được đếm để rà soát điểm gãy điều chỉnh giá; đây là cờ kiểm tra, không phải lỗi tự động.", "",
        "| Mã | Dòng | Phiên đầu – cuối đã lưu | Nến nguồn đầu tiên | Kỳ vọng | Thiếu | Trước lịch sử nguồn | Δ>7,5% | Δ>15% |",
        "|---|---|---|---|---|---|---|---|---|",
        *[f"| {x['ticker']} | {x['rows']} | {x['first_stored'] or '—'} – {x['last_stored'] or '—'} | {x['first_provider_candle'] or '—'} | {x['expected_sessions']} | "
          f"{x['missing_sessions']}{(' (' + ', '.join(x['missing_dates_sample']) + ('…' if x['missing_sessions'] > 8 else '') + ')') if x['missing_sessions'] else ''} | "
          f"{x['no_history_sessions']} | {x['jumps_gt_7_5pct']} | {x['jumps_gt_15pct']} |" for x in cov["per_ticker"]], ""]
    for sec in extra_sections or []:
        lines += [sec, ""]
    return "\n".join(lines)
