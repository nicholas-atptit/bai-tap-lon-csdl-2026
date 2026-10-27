-- Read-only preflight for the SYNTHETIC demonstration. Run before 09_live_demo.sql.
USE [MarketLabVN30_Demo];
GO
SET NOCOUNT ON;
SET QUOTED_IDENTIFIER ON;
SET ANSI_NULLS ON;
IF DB_NAME()<>N'MarketLabVN30_Demo' THROW 52000,N'Sai database demo.',1;
IF @@TRANCOUNT<>0 THROW 52001,N'Ket thuc transaction dang mo truoc khi demo.',1;
DECLARE @Checks TABLE(Item nvarchar(80),Actual bigint,Expected bigint);
INSERT @Checks VALUES
 (N'Tables',(SELECT COUNT(*) FROM sys.tables WHERE is_ms_shipped=0),13),
 (N'Stock',(SELECT COUNT_BIG(*) FROM dbo.Stock),8),
 (N'DailyPrice',(SELECT COUNT_BIG(*) FROM dbo.DailyPrice),280),
 (N'Prediction',(SELECT COUNT_BIG(*) FROM dbo.Prediction),258),
 (N'Eligible at 2026-07-01',(SELECT COUNT_BIG(*) FROM dbo.fn_EligiblePredictions('20260701')),256),
 (N'Procedures',(SELECT COUNT(*) FROM sys.procedures WHERE is_ms_shipped=0),4),
 (N'Functions',(SELECT COUNT(*) FROM sys.objects WHERE type IN('FN','IF','TF') AND is_ms_shipped=0),3),
 (N'Views',(SELECT COUNT(*) FROM sys.views WHERE is_ms_shipped=0),4),
 (N'Prediction.TargetDate redundant column',CASE WHEN COL_LENGTH('dbo.Prediction','TargetDate') IS NULL THEN 0 ELSE 1 END,0),
 (N'Disabled/untrusted FK',(SELECT COUNT(*) FROM sys.foreign_keys WHERE is_disabled=1 OR is_not_trusted=1),0),
 (N'Disabled/untrusted CHECK',(SELECT COUNT(*) FROM sys.check_constraints WHERE is_disabled=1 OR is_not_trusted=1),0),
 (N'Disabled business triggers',(SELECT COUNT(*) FROM sys.triggers WHERE is_ms_shipped=0 AND is_disabled=1),0),
 (N'Non-synthetic datasets',(SELECT COUNT(*) FROM dbo.Dataset WHERE DataKind<>'SYNTHETIC'),0),
 (N'Non-synthetic stocks',(SELECT COUNT(*) FROM dbo.Stock WHERE IsSynthetic<>1),0);
DECLARE @MissingEndpoint bigint;
SELECT @MissingEndpoint=COUNT_BIG(*) FROM dbo.Prediction p
JOIN dbo.ModelRun r ON r.RunId=p.RunId JOIN dbo.ForecastOrigin f ON f.RunId=p.RunId AND f.OriginDate=p.OriginDate
LEFT JOIN dbo.DailyPrice a ON a.DatasetId=r.DatasetId AND a.StockId=p.StockId AND a.TradeDate=p.OriginDate
LEFT JOIN dbo.DailyPrice z ON z.DatasetId=r.DatasetId AND z.StockId=p.StockId AND z.TradeDate=f.TargetDate
WHERE a.StockId IS NULL OR z.StockId IS NULL;
INSERT @Checks VALUES(N'Missing actual endpoints',@MissingEndpoint,2);
IF NOT EXISTS(SELECT 1 FROM sys.foreign_keys WHERE name=N'FK_Prediction_ForecastOrigin' AND is_disabled=0 AND is_not_trusted=0)
 THROW 52002,N'Thieu FK Prediction -> ForecastOrigin.',1;
SELECT CAST(@@SERVERNAME AS nvarchar(128)) AS ServerName,CAST(SERVERPROPERTY('Edition') AS nvarchar(100)) AS Edition,
 CAST(SERVERPROPERTY('ProductVersion') AS nvarchar(30)) AS EngineVersion,DB_NAME() AS DatabaseName,
 N'SYNTHETIC DEMO ONLY' AS DataClassification;
SELECT Item,Actual,Expected,CASE WHEN Actual=Expected THEN 'PASS' ELSE 'FAIL' END AS Status FROM @Checks ORDER BY Item;
IF EXISTS(SELECT 1 FROM @Checks WHERE Actual<>Expected) THROW 52003,N'Preflight FAIL. Khong reset du lieu de che loi; xem ket qua.',1;
SELECT N'PREFLIGHT_PASS' AS Result,@@TRANCOUNT AS OpenTransactions;
GO
