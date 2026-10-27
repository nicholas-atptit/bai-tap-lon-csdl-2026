-- OPTIONAL, READ ONLY, AGGREGATES ONLY. Requires the private research DB on the author's machine.
-- The submission demo does not depend on this database or contain its source records.
USE [MarketLabVN30_Research_20261027];
GO
SET NOCOUNT ON;
SELECT N'REAL_PRIVATE_RETROSPECTIVE' AS DataClassification,
 (SELECT COUNT_BIG(*) FROM dbo.Stock) AS Stocks,(SELECT COUNT_BIG(*) FROM dbo.DailyPrice) AS DailyPrices,
 (SELECT COUNT_BIG(*) FROM dbo.Prediction) AS Predictions,
 N'Universe selected from June-2026 snapshot; not a full historical VN30 membership series' AS Scope;
EXEC dbo.usp_CompareModels '1,2','20250101','20260101','20260701';
GO
