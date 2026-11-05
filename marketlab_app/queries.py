"""Read-only SQL used by the API and by the post-EOD evaluation snapshot.

Business rules stay in SQL Server: eligibility comes from dbo.fn_EligiblePredictions(@AsOf); the metric formulas
below are copied verbatim from dbo.vw_ModelPerformance (which is fixed to SYSUTCDATETIME) so that an explicit
as_of can be used; comparisons call dbo.usp_CompareModels.
"""
from __future__ import annotations

import datetime as dt

import pyodbc

from .db import query, query_sets

REQUIRED_OBJECTS = {
    "tables": ["Market", "Industry", "Stock", "Dataset", "TradingDay", "DailyPrice", "StockIndex", "IndexMembership",
               "ForecastModel", "TargetDefinition", "ModelRun", "ForecastOrigin", "Prediction"],
    "functions": ["fn_CalculateReturn", "fn_CheckPredictionDirection", "fn_EligiblePredictions"],
    "views": ["vw_LatestStockPrice", "vw_StudyUniverse", "vw_VN30SnapshotJune2026", "vw_ModelPerformance"],
    "procedures": ["usp_InsertDailyPrice", "usp_AddPrediction", "usp_GetModelPerformance", "usp_CompareModels"],
}

METRICS_SELECT = """
 COUNT_BIG(*) AS EvaluatedRows,
 AVG(CONVERT(decimal(19,10),CASE WHEN e.PredictedLabel=e.ActualLabel THEN 1.0 ELSE 0.0 END)) AS Accuracy,
 AVG(POWER(CONVERT(float,e.ProbabilityPositive)-CONVERT(int,e.ActualLabel),2)) AS BrierScore,
 AVG(-LOG(CASE WHEN e.ActualLabel=1 THEN
 CASE WHEN e.ProbabilityPositive<0.000000000001 THEN 0.000000000001 ELSE CONVERT(float,e.ProbabilityPositive) END
 ELSE CASE WHEN e.ProbabilityPositive>0.999999999999 THEN 0.000000000001 ELSE 1.0-CONVERT(float,e.ProbabilityPositive) END END)) AS NaturalLogLoss
"""


def schema_status(c: pyodbc.Connection) -> dict:
    found = query(c, """
        SELECT o.name, o.type FROM sys.objects o WHERE o.schema_id=SCHEMA_ID('dbo') AND o.is_ms_shipped=0
          AND o.type IN ('U','FN','IF','TF','V','P')""")
    names = {(r["name"], r["type"].strip()) for r in found}
    kinds = {"tables": ("U",), "functions": ("FN", "IF", "TF"), "views": ("V",), "procedures": ("P",)}
    missing = {k: [n for n in v if not any((n, t) in names for t in kinds[k])] for k, v in REQUIRED_OBJECTS.items()}
    props = {r["name"]: r["value"] for r in query(c, "SELECT name, CONVERT(nvarchar(50),value) AS value FROM sys.extended_properties WHERE class=0")}
    total_tables = query(c, "SELECT COUNT(*) AS n FROM sys.tables WHERE is_ms_shipped=0")[0]["n"]
    return {"missing": {k: v for k, v in missing.items() if v}, "marketlab_schema": props.get("MarketLabSchema"),
            "eod_extension": props.get("MarketLabEodExtension") == "1"
                             and bool(query(c, "SELECT 1 AS x WHERE OBJECT_ID('ops.usp_EodApplySession','P') IS NOT NULL")),
            "user_tables": total_tables}


def dataset_kinds(c: pyodbc.Connection) -> list[str]:
    return [r["DataKind"] for r in query(c, "SELECT DISTINCT DataKind FROM dbo.Dataset")]


def datasets(c: pyodbc.Connection) -> list[dict]:
    return query(c, """
        SELECT d.DatasetId, d.DatasetCode, d.DataKind, d.PriceBasis, d.PriceUnit, d.ObservedThrough, d.ManifestPath,
               d.ProvenanceNote, m.MarketCode, m.CurrencyCode,
               (SELECT COUNT_BIG(*) FROM dbo.DailyPrice p WHERE p.DatasetId=d.DatasetId) AS PriceRows,
               (SELECT COUNT(DISTINCT p.StockId) FROM dbo.DailyPrice p WHERE p.DatasetId=d.DatasetId) AS StocksWithPrices,
               (SELECT COUNT(*) FROM dbo.TradingDay t WHERE t.DatasetId=d.DatasetId) AS TradingDays,
               (SELECT MIN(t.TradeDate) FROM dbo.TradingDay t WHERE t.DatasetId=d.DatasetId) AS FirstTradingDay,
               (SELECT MAX(t.TradeDate) FROM dbo.TradingDay t WHERE t.DatasetId=d.DatasetId) AS LastTradingDay,
               (SELECT MAX(p.TradeDate) FROM dbo.DailyPrice p WHERE p.DatasetId=d.DatasetId) AS LastPriceDate,
               (SELECT COUNT(*) FROM dbo.ModelRun r WHERE r.DatasetId=d.DatasetId) AS ModelRuns,
               (SELECT COUNT_BIG(*) FROM dbo.Prediction p JOIN dbo.ModelRun r ON r.RunId=p.RunId WHERE r.DatasetId=d.DatasetId) AS Predictions
        FROM dbo.Dataset d JOIN dbo.Market m ON m.MarketId=d.MarketId ORDER BY d.DatasetId""")


def dataset_exists(c: pyodbc.Connection, dataset_id: int) -> dict | None:
    r = query(c, "SELECT DatasetId, DataKind, ObservedThrough, PriceUnit, PriceBasis FROM dbo.Dataset WHERE DatasetId=?", (dataset_id,))
    return r[0] if r else None


def eligible_count(c: pyodbc.Connection, dataset_id: int, as_of: dt.date) -> int:
    return query(c, "SELECT COUNT_BIG(*) AS n FROM dbo.fn_EligiblePredictions(?) WHERE DatasetId=?", (as_of, dataset_id))[0]["n"]


def stocks(c: pyodbc.Connection, dataset_id: int, q: str | None, limit: int, offset: int) -> tuple[list[dict], int]:
    where, params = ["d.DatasetId=?"], [dataset_id]
    if q:
        where.append("s.Ticker LIKE ? ESCAPE '\\'")
        params.append(q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_").upper() + "%")
    base = f"""FROM dbo.Dataset d JOIN dbo.Stock s ON s.MarketId=d.MarketId
               AND s.IsSynthetic=CASE WHEN d.DataKind='SYNTHETIC' THEN 1 ELSE 0 END
               LEFT JOIN dbo.vw_StudyUniverse u ON u.DatasetId=d.DatasetId AND u.StockId=s.StockId
               LEFT JOIN dbo.Industry i ON i.IndustryId=s.IndustryId
               WHERE {' AND '.join(where)}"""
    total = query(c, "SELECT COUNT(*) AS n " + base, params)[0]["n"]
    items = query(c, f"""SELECT s.StockId, s.Ticker, s.CompanyName, i.IndustryName, s.IsSynthetic,
                           u.FirstObservedDate, u.LastObservedDate, ISNULL(u.PriceRows,0) AS PriceRows,
                           CASE WHEN EXISTS(SELECT 1 FROM dbo.IndexMembership m JOIN dbo.StockIndex x ON x.IndexId=m.IndexId
                                WHERE m.StockId=s.StockId AND x.IndexCode='VN30') THEN 1 ELSE 0 END AS InVN30Snapshot
                         {base} ORDER BY s.Ticker OFFSET ? ROWS FETCH NEXT ? ROWS ONLY""", params + [offset, limit])
    return items, total


def stock_id(c: pyodbc.Connection, dataset_id: int, ticker: str) -> int | None:
    r = query(c, """SELECT s.StockId FROM dbo.Stock s JOIN dbo.Dataset d ON d.MarketId=s.MarketId
                    WHERE d.DatasetId=? AND s.Ticker=?""", (dataset_id, ticker.upper()))
    return r[0]["StockId"] if r else None


PRICE_SORT = {"date": "p.TradeDate", "ticker": "s.Ticker", "close": "p.ClosePrice", "volume": "p.Volume"}


def prices(c, dataset_id: int, ticker: str | None, date_from, date_to, sort: str, desc: bool, limit: int, offset: int):
    where, params = ["p.DatasetId=?"], [dataset_id]
    if ticker:
        where.append("s.Ticker=?")
        params.append(ticker.upper())
    if date_from:
        where.append("p.TradeDate>=?")
        params.append(date_from)
    if date_to:
        where.append("p.TradeDate<=?")
        params.append(date_to)
    base = f"FROM dbo.DailyPrice p JOIN dbo.Stock s ON s.StockId=p.StockId WHERE {' AND '.join(where)}"
    total = query(c, "SELECT COUNT_BIG(*) AS n " + base, params)[0]["n"]
    tie = [c for c in ("p.TradeDate", "s.Ticker") if c != PRICE_SORT[sort]]
    order = ", ".join([f"{PRICE_SORT[sort]} {'DESC' if desc else 'ASC'}"] + tie)
    items = query(c, f"""SELECT s.Ticker, p.StockId, p.TradeDate, p.OpenPrice, p.HighPrice, p.LowPrice, p.ClosePrice, p.Volume, p.LoadedAt
                         {base} ORDER BY {order} OFFSET ? ROWS FETCH NEXT ? ROWS ONLY""", params + [offset, limit])
    return items, total


def price_series(c, dataset_id: int, ticker: str, date_from, date_to, max_points: int) -> list[dict]:
    """Every dbo.TradingDay session between the ticker's first and last stored price (and the filter window).
    Sessions present in the dataset calendar but without a stored price come back with NULL prices
    (InCalendarWithoutPrice=1) so charts break the line instead of drawing through a missing session."""
    where, params = ["t.DatasetId=?"], [dataset_id]
    if date_from:
        where.append("t.TradeDate>=?")
        params.append(date_from)
    if date_to:
        where.append("t.TradeDate<=?")
        params.append(date_to)
    return query(c, f"""
        WITH st AS (SELECT StockId FROM dbo.Stock s JOIN dbo.Dataset d ON d.MarketId=s.MarketId WHERE d.DatasetId=? AND s.Ticker=?),
        rng AS (SELECT MIN(p.TradeDate) AS f, MAX(p.TradeDate) AS l FROM dbo.DailyPrice p JOIN st ON st.StockId=p.StockId WHERE p.DatasetId=?)
        SELECT TOP (?) x.* FROM (
          SELECT TOP (?) t.TradeDate, p.OpenPrice, p.HighPrice, p.LowPrice, p.ClosePrice, p.Volume,
                 CONVERT(bit, CASE WHEN p.StockId IS NULL THEN 1 ELSE 0 END) AS InCalendarWithoutPrice
          FROM dbo.TradingDay t CROSS JOIN rng
          LEFT JOIN dbo.DailyPrice p ON p.DatasetId=t.DatasetId AND p.TradeDate=t.TradeDate AND p.StockId=(SELECT StockId FROM st)
          WHERE {' AND '.join(where)} AND t.TradeDate BETWEEN rng.f AND rng.l
          ORDER BY t.TradeDate DESC) x ORDER BY x.TradeDate ASC""",
                 [dataset_id, ticker.upper(), dataset_id, max_points, max_points] + params)


def latest_prices(c, dataset_id: int) -> list[dict]:
    return query(c, """SELECT v.Ticker, v.StockId, v.TradeDate, v.ClosePrice, v.Volume, v.PriceUnit, v.PriceBasis,
                              prev.ClosePrice AS PreviousClose, prev.TradeDate AS PreviousDate,
                              dbo.fn_CalculateReturn(prev.ClosePrice, v.ClosePrice) AS SourceCloseChangePct
                       FROM dbo.vw_LatestStockPrice v
                       OUTER APPLY (SELECT TOP 1 p.ClosePrice, p.TradeDate FROM dbo.DailyPrice p
                                    WHERE p.DatasetId=v.DatasetId AND p.StockId=v.StockId AND p.TradeDate<v.TradeDate
                                    ORDER BY p.TradeDate DESC) prev
                       WHERE v.DatasetId=? ORDER BY v.Ticker""", (dataset_id,))


def model_runs(c, dataset_id: int | None) -> list[dict]:
    where, params = "", []
    if dataset_id is not None:
        where, params = "WHERE r.DatasetId=?", [dataset_id]
    return query(c, f"""SELECT r.RunId, r.RunCode, r.DatasetId, d.DatasetCode, m.ModelId, m.ModelCode, m.ModelName, m.MethodNote,
                               t.TargetId, t.TargetCode, t.HorizonSessions, r.Threshold, r.TrainStart, r.TrainEnd, r.ValidationEnd,
                               r.EvaluationClass, r.SourceRun, r.CompletedAt,
                               (SELECT COUNT_BIG(*) FROM dbo.Prediction p WHERE p.RunId=r.RunId) AS Predictions,
                               (SELECT MIN(OriginDate) FROM dbo.ForecastOrigin f WHERE f.RunId=r.RunId) AS FirstOrigin,
                               (SELECT MAX(OriginDate) FROM dbo.ForecastOrigin f WHERE f.RunId=r.RunId) AS LastOrigin,
                               (SELECT MAX(TargetDate) FROM dbo.ForecastOrigin f WHERE f.RunId=r.RunId) AS LastTarget
                        FROM dbo.ModelRun r JOIN dbo.ForecastModel m ON m.ModelId=r.ModelId
                        JOIN dbo.TargetDefinition t ON t.TargetId=r.TargetId JOIN dbo.Dataset d ON d.DatasetId=r.DatasetId
                        {where} ORDER BY r.RunId""", params)


def run_info(c, run_id: int) -> dict | None:
    r = query(c, "SELECT RunId, DatasetId, TargetId FROM dbo.ModelRun WHERE RunId=?", (run_id,))
    return r[0] if r else None


PRED_STATUS = {"eligible": "e.RunId IS NOT NULL",
               "pending": "e.RunId IS NULL AND (f.TargetDate>? OR f.TargetDate>d.ObservedThrough)",
               "missing_endpoint": "e.RunId IS NULL AND NOT (f.TargetDate>? OR f.TargetDate>d.ObservedThrough)"}


def predictions(c, run_id: int, as_of: dt.date, ticker: str | None, origin_from, origin_to, status: str | None,
                limit: int, offset: int):
    where, params = ["p.RunId=?"], [run_id]
    if ticker:
        where.append("s.Ticker=?")
        params.append(ticker.upper())
    if origin_from:
        where.append("p.OriginDate>=?")
        params.append(origin_from)
    if origin_to:
        where.append("p.OriginDate<=?")
        params.append(origin_to)
    if status:
        where.append(PRED_STATUS[status])
        if "?" in PRED_STATUS[status]:
            params.append(as_of)
    base = f"""FROM dbo.Prediction p JOIN dbo.ForecastOrigin f ON f.RunId=p.RunId AND f.OriginDate=p.OriginDate
               JOIN dbo.ModelRun r ON r.RunId=p.RunId JOIN dbo.Dataset d ON d.DatasetId=r.DatasetId
               JOIN dbo.Stock s ON s.StockId=p.StockId
               LEFT JOIN dbo.fn_EligiblePredictions(?) e ON e.RunId=p.RunId AND e.StockId=p.StockId AND e.OriginDate=p.OriginDate
               WHERE {' AND '.join(where)}"""
    head = [as_of]
    total = query(c, "SELECT COUNT_BIG(*) AS n " + base, head + params)[0]["n"]
    items = query(c, f"""SELECT p.RunId, s.Ticker, p.StockId, p.OriginDate, f.TargetDate, p.ProbabilityPositive, r.Threshold,
                           CONVERT(bit,CASE WHEN p.ProbabilityPositive>=r.Threshold THEN 1 ELSE 0 END) AS PredictedLabel,
                           e.ActualLabel, e.ActualSourceCloseReturnPct,
                           CASE WHEN e.RunId IS NOT NULL THEN 'ELIGIBLE'
                                WHEN f.TargetDate>? OR f.TargetDate>d.ObservedThrough THEN 'PENDING'
                                ELSE 'MISSING_ENDPOINT' END AS EvaluationStatus
                         {base} ORDER BY p.OriginDate, s.Ticker OFFSET ? ROWS FETCH NEXT ? ROWS ONLY""",
                  [as_of] + head + params + [offset, limit])
    return items, total


def performance(c, as_of: dt.date, dataset_id: int | None = None, run_id: int | None = None) -> list[dict]:
    where, params = [], []
    if dataset_id is not None:
        where.append("r.DatasetId=?")
        params.append(dataset_id)
    if run_id is not None:
        where.append("r.RunId=?")
        params.append(run_id)
    w = ("WHERE " + " AND ".join(where)) if where else ""
    return query(c, f"""
        WITH ev AS (SELECT e.RunId, {METRICS_SELECT} FROM dbo.fn_EligiblePredictions(?) e GROUP BY e.RunId),
        st AS (SELECT p.RunId, COUNT_BIG(*) AS TotalPredictions,
                      SUM(CASE WHEN f.TargetDate>? OR f.TargetDate>d.ObservedThrough THEN 1 ELSE 0 END) AS PendingNotMatured
               FROM dbo.Prediction p JOIN dbo.ForecastOrigin f ON f.RunId=p.RunId AND f.OriginDate=p.OriginDate
               JOIN dbo.ModelRun r ON r.RunId=p.RunId JOIN dbo.Dataset d ON d.DatasetId=r.DatasetId GROUP BY p.RunId)
        SELECT r.RunId, r.RunCode, m.ModelCode, r.DatasetId, t.TargetCode, t.HorizonSessions, r.Threshold, r.EvaluationClass,
               ? AS AsOfDate, ISNULL(st.TotalPredictions,0) AS TotalPredictions, ISNULL(ev.EvaluatedRows,0) AS EvaluatedRows,
               ISNULL(st.PendingNotMatured,0) AS PendingNotMatured,
               ISNULL(st.TotalPredictions,0)-ISNULL(ev.EvaluatedRows,0)-ISNULL(st.PendingNotMatured,0) AS MissingEndpoint,
               ev.Accuracy, ev.BrierScore, ev.NaturalLogLoss
        FROM dbo.ModelRun r JOIN dbo.ForecastModel m ON m.ModelId=r.ModelId JOIN dbo.TargetDefinition t ON t.TargetId=r.TargetId
        LEFT JOIN ev ON ev.RunId=r.RunId LEFT JOIN st ON st.RunId=r.RunId {w} ORDER BY r.RunId""",
                 [as_of, as_of, as_of] + params)


def compare_runs(c, run_ids: list[int], date_from: dt.date, date_to: dt.date, as_of: dt.date) -> dict:
    """dbo.usp_CompareModels (authoritative Accuracy/Brier on the intersection) + log loss on the SAME intersection."""
    sets = query_sets(c, "EXEC dbo.usp_CompareModels @RunIds=?, @FromDate=?, @ToDate=?, @AsOfDate=?",
                      (",".join(str(r) for r in run_ids), date_from, date_to, as_of))
    proc_rows = sets[-1] if sets else []
    n = len(run_ids)
    placeholders = ",".join("?" for _ in run_ids)
    extra = query(c, f"""
        WITH el AS (SELECT e.* FROM dbo.fn_EligiblePredictions(?) e WHERE e.RunId IN ({placeholders}) AND e.OriginDate BETWEEN ? AND ?),
        cm AS (SELECT StockId, OriginDate, TargetDate FROM el GROUP BY StockId, OriginDate, TargetDate HAVING COUNT(*)=?)
        SELECT e.RunId, {METRICS_SELECT}, MIN(e.OriginDate) AS FirstOrigin, MAX(e.OriginDate) AS LastOrigin, MAX(e.TargetDate) AS LastTarget
        FROM el e JOIN cm ON cm.StockId=e.StockId AND cm.OriginDate=e.OriginDate AND cm.TargetDate=e.TargetDate
        GROUP BY e.RunId ORDER BY e.RunId""", [as_of] + run_ids + [date_from, date_to, n])
    by_run = {r["RunId"]: r for r in extra}
    merged = []
    for row in proc_rows:
        x = by_run.get(row["RunId"], {})
        merged.append({**row, "NaturalLogLoss": x.get("NaturalLogLoss"), "IntersectionRowsCheck": x.get("EvaluatedRows"),
                       "FirstOrigin": x.get("FirstOrigin"), "LastOrigin": x.get("LastOrigin"), "LastTarget": x.get("LastTarget")})
    return {"rows": merged}


def calendar_check(c, dataset_id: int, universe_ids: list[int] | None, date_from, date_to, limit: int) -> list[dict]:
    """Per trading day: price rows vs expected universe size (missing rows are reported, never filled)."""
    where, params = ["t.DatasetId=?"], [dataset_id]
    if date_from:
        where.append("t.TradeDate>=?")
        params.append(date_from)
    if date_to:
        where.append("t.TradeDate<=?")
        params.append(date_to)
    if universe_ids:
        expected_sql = str(len(universe_ids))
    else:
        expected_sql = "(SELECT COUNT(*) FROM dbo.Stock s JOIN dbo.Dataset d ON d.MarketId=s.MarketId WHERE d.DatasetId=t.DatasetId AND s.IsSynthetic=CASE WHEN d.DataKind='SYNTHETIC' THEN 1 ELSE 0 END)"
    return query(c, f"""SELECT TOP (?) t.TradeDate, COUNT(p.StockId) AS PriceRows, {expected_sql} AS ExpectedRows,
                               {expected_sql}-COUNT(p.StockId) AS MissingRows,
                               CASE WHEN t.TradeDate>d.ObservedThrough THEN 1 ELSE 0 END AS AfterObservedThrough
                        FROM dbo.TradingDay t JOIN dbo.Dataset d ON d.DatasetId=t.DatasetId
                        LEFT JOIN dbo.DailyPrice p ON p.DatasetId=t.DatasetId AND p.TradeDate=t.TradeDate
                        WHERE {' AND '.join(where)}
                        GROUP BY t.TradeDate, t.DatasetId, d.ObservedThrough ORDER BY t.TradeDate DESC""", [limit] + params)


def universe(c, dataset_id: int, index_code: str, as_of: dt.date) -> list[dict]:
    return query(c, """SELECT s.StockId, s.Ticker FROM dbo.IndexMembership m
                       JOIN dbo.StockIndex x ON x.IndexId=m.IndexId JOIN dbo.Stock s ON s.StockId=m.StockId
                       JOIN dbo.Dataset d ON d.DatasetId=? AND d.MarketId=s.MarketId AND d.MarketId=x.MarketId
                       WHERE x.IndexCode=? AND ? BETWEEN m.ValidFrom AND m.ValidTo AND s.IsSynthetic=0
                       ORDER BY s.Ticker""", (dataset_id, index_code, as_of))
