USE MarketLabVN30_Demo;
-- 4 Stored Procedure nghiep vu
SELECT name AS ProcedureName, create_date FROM sys.procedures WHERE schema_id = SCHEMA_ID('dbo') ORDER BY name;
-- EXEC thu tuc chi doc: danh gia mo hinh demo_baseline
EXEC dbo.usp_GetModelPerformance
     @ModelCode = 'demo_baseline', @DatasetId = 1, @HorizonSessions = 5,
     @FromDate = '2025-01-01', @ToDate = '2025-12-31', @AsOfDate = '2026-07-01';
