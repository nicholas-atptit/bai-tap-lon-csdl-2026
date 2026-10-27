USE [MarketLabVN30_Demo];
GO
CREATE OR ALTER VIEW dbo.vw_LatestStockPrice AS
 WITH Ranked AS(SELECT p.*,ROW_NUMBER() OVER(PARTITION BY DatasetId,StockId ORDER BY TradeDate DESC) AS rn FROM dbo.DailyPrice p)
 SELECT p.DatasetId,s.StockId,s.Ticker,p.TradeDate,p.ClosePrice,p.Volume,d.PriceUnit,d.PriceBasis
 FROM Ranked p JOIN dbo.Stock s ON s.StockId=p.StockId JOIN dbo.Dataset d ON d.DatasetId=p.DatasetId WHERE rn=1;
GO
CREATE OR ALTER VIEW dbo.vw_StudyUniverse AS
 SELECT d.DatasetId,d.DatasetCode,d.DataKind,s.StockId,s.Ticker,s.CompanyName,s.IndustryId,
 MIN(p.TradeDate) AS FirstObservedDate,MAX(p.TradeDate) AS LastObservedDate,COUNT_BIG(*) AS PriceRows
 FROM dbo.DailyPrice p JOIN dbo.Stock s ON s.StockId=p.StockId JOIN dbo.Dataset d ON d.DatasetId=p.DatasetId
 GROUP BY d.DatasetId,d.DatasetCode,d.DataKind,s.StockId,s.Ticker,s.CompanyName,s.IndustryId;
GO
-- A bounded snapshot only. Not a current or historical VN30 membership claim.
CREATE OR ALTER VIEW dbo.vw_VN30SnapshotJune2026 AS
 SELECT s.StockId,s.Ticker,m.ValidFrom,m.ValidTo,m.EvidenceNote
 FROM dbo.IndexMembership m JOIN dbo.Stock s ON s.StockId=m.StockId JOIN dbo.StockIndex x ON x.IndexId=m.IndexId
 WHERE x.IndexCode='VN30' AND CONVERT(date,'20260630') BETWEEN m.ValidFrom AND m.ValidTo;
GO
CREATE OR ALTER VIEW dbo.vw_ModelPerformance AS
 SELECT e.RunId,e.ModelId,e.DatasetId,e.TargetId,e.HorizonSessions,COUNT_BIG(*) AS EvaluatedRows,
 AVG(CONVERT(decimal(19,10),CASE WHEN e.PredictedLabel=e.ActualLabel THEN 1.0 ELSE 0.0 END)) AS Accuracy,
 AVG(POWER(CONVERT(float,e.ProbabilityPositive)-CONVERT(int,e.ActualLabel),2)) AS BrierScore,
 AVG(-LOG(CASE WHEN e.ActualLabel=1 THEN
 CASE WHEN e.ProbabilityPositive<0.000000000001 THEN 0.000000000001 ELSE CONVERT(float,e.ProbabilityPositive) END
 ELSE CASE WHEN e.ProbabilityPositive>0.999999999999 THEN 0.000000000001 ELSE 1.0-CONVERT(float,e.ProbabilityPositive) END END)) AS NaturalLogLoss
 FROM dbo.fn_EligiblePredictions(CONVERT(date,SYSUTCDATETIME())) e
 GROUP BY e.RunId,e.ModelId,e.DatasetId,e.TargetId,e.HorizonSessions;
GO
