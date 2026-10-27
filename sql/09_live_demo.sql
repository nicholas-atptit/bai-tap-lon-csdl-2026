-- 3-5 minute, rerunnable SSMS demonstration. SYNTHETIC data only.
-- Run the complete file with F5, then present the five groups of result sets.
-- Blocks 4-5 share local variables and must be executed together. No SQLCMD mode needed.
USE [MarketLabVN30_Demo];
GO
SET NOCOUNT ON;
SET QUOTED_IDENTIFIER ON;
SET ANSI_NULLS ON;
IF DB_NAME()<>N'MarketLabVN30_Demo' THROW 52010,N'Sai database demo.',1;
IF @@TRANCOUNT<>0 THROW 52011,N'Can session khong co transaction dang mo.',1;
IF (SELECT COUNT(*) FROM dbo.Dataset WHERE DataKind='SYNTHETIC')<>1
 OR EXISTS(SELECT 1 FROM dbo.Stock WHERE IsSynthetic<>1) THROW 52012,N'Chi chay tren dataset mo phong.',1;

-- DEMO 1 (0:00-0:40): 13 tables, their actual primary keys and foreign keys.
SELECT t.name AS TableName,
 STUFF((SELECT ','+QUOTENAME(c.name) FROM sys.indexes i JOIN sys.index_columns ic ON ic.object_id=i.object_id AND ic.index_id=i.index_id
 JOIN sys.columns c ON c.object_id=ic.object_id AND c.column_id=ic.column_id
 WHERE i.object_id=t.object_id AND i.is_primary_key=1 ORDER BY ic.key_ordinal FOR XML PATH(''),TYPE).value('.','nvarchar(max)'),1,1,'') AS PrimaryKey,
 (SELECT COUNT(*) FROM sys.foreign_keys fk WHERE fk.parent_object_id=t.object_id) AS ForeignKeyCount
FROM sys.tables t WHERE t.is_ms_shipped=0 ORDER BY t.name;
SELECT fk.name AS ForeignKey,OBJECT_NAME(fk.parent_object_id) AS ChildTable,OBJECT_NAME(fk.referenced_object_id) AS ParentTable
FROM sys.foreign_keys fk ORDER BY ChildTable,ForeignKey;

-- DEMO 2 (0:40-1:30): INNER JOIN, GROUP BY/HAVING, and a meaningful subquery.
SELECT TOP(5) s.Ticker,i.IndustryName,p.TradeDate,p.ClosePrice
FROM dbo.vw_LatestStockPrice p INNER JOIN dbo.Stock s ON s.StockId=p.StockId
INNER JOIN dbo.Industry i ON i.IndustryId=s.IndustryId ORDER BY s.Ticker;
SELECT s.Ticker,COUNT(*) AS ObservedSessions,AVG(CONVERT(decimal(25,2),p.Volume)) AS AverageVolume
FROM dbo.DailyPrice p JOIN dbo.Stock s ON s.StockId=p.StockId GROUP BY s.Ticker HAVING COUNT(*)>=20 ORDER BY s.Ticker;
SELECT TOP(5) s.Ticker,p.TradeDate,p.Volume FROM dbo.DailyPrice p JOIN dbo.Stock s ON s.StockId=p.StockId
WHERE p.Volume>(SELECT AVG(CONVERT(decimal(25,2),q.Volume)) FROM dbo.DailyPrice q WHERE q.DatasetId=p.DatasetId AND q.StockId=p.StockId)
ORDER BY s.Ticker,p.TradeDate;

-- DEMO 3 (1:30-2:10): same mature observations, then the required functions.
EXEC dbo.usp_CompareModels '1,2','20250101','20260101','20260701';
SELECT dbo.fn_CalculateReturn(100,110) AS SourceCloseReturnPct,
 dbo.fn_CheckPredictionDirection(0,0) AS FlatMatchesFlat,
 (SELECT COUNT(*) FROM dbo.fn_EligiblePredictions('20260701')) AS EvaluatedPredictions;

-- DEMO 4 (2:10-2:50): the CHECK must reject negative Volume; catch only that error.
DECLARE @DatasetId int=1,@StockId int=1,@Date date=(SELECT MIN(TradeDate) FROM dbo.DailyPrice WHERE DatasetId=1 AND StockId=1);
DECLARE @Before bigint=(SELECT Volume FROM dbo.DailyPrice WHERE DatasetId=@DatasetId AND StockId=@StockId AND TradeDate=@Date),@Caught bit=0;
IF @Before IS NULL OR @Before=9223372036854775807 THROW 52013,N'Khong co hang an toan de demo.',1;
DECLARE @BeforeHash varbinary(32)=HASHBYTES('SHA2_256',(SELECT * FROM dbo.DailyPrice ORDER BY DatasetId,StockId,TradeDate FOR JSON PATH,INCLUDE_NULL_VALUES));
DECLARE @WasXactAbort bit=CASE WHEN (@@OPTIONS & 16384)=16384 THEN 1 ELSE 0 END;
SET XACT_ABORT OFF;
BEGIN TRY
 BEGIN TRANSACTION;
 UPDATE dbo.DailyPrice SET Volume=-1 WHERE DatasetId=@DatasetId AND StockId=@StockId AND TradeDate=@Date;
 ROLLBACK;
END TRY
BEGIN CATCH
 DECLARE @Error int=ERROR_NUMBER(),@Message nvarchar(2048)=ERROR_MESSAGE();
 IF XACT_STATE()<>0 ROLLBACK;
 IF @Error<>547 OR CHARINDEX('CK_DailyPrice_Volume',@Message)=0 THROW;
 SET @Caught=1;
 SELECT @Error AS ExpectedError,@Message AS ConstraintEvidence,N'PASS: invalid update rejected; session continues' AS Result;
END CATCH;
IF @Caught<>1 THROW 52014,N'CHECK khong tu choi du lieu am. Demo FAIL.',1;

-- DEMO 5 (2:50-3:50): show BEFORE, DURING and AFTER, not just an unobserved rollback.
BEGIN TRY
 SELECT N'BEFORE' AS Stage,@Before AS Volume;
 BEGIN TRANSACTION;
 UPDATE dbo.DailyPrice SET Volume=Volume+1 WHERE DatasetId=@DatasetId AND StockId=@StockId AND TradeDate=@Date;
 SELECT N'DURING' AS Stage,Volume FROM dbo.DailyPrice WHERE DatasetId=@DatasetId AND StockId=@StockId AND TradeDate=@Date;
 ROLLBACK;
 SELECT N'AFTER ROLLBACK' AS Stage,Volume FROM dbo.DailyPrice WHERE DatasetId=@DatasetId AND StockId=@StockId AND TradeDate=@Date;
END TRY
BEGIN CATCH
 IF XACT_STATE()<>0 ROLLBACK;
 IF @WasXactAbort=1 SET XACT_ABORT ON;
 THROW;
END CATCH;
DECLARE @AfterHash varbinary(32)=HASHBYTES('SHA2_256',(SELECT * FROM dbo.DailyPrice ORDER BY DatasetId,StockId,TradeDate FOR JSON PATH,INCLUDE_NULL_VALUES));
IF @WasXactAbort=1 SET XACT_ABORT ON;
IF @BeforeHash<>@AfterHash OR @@TRANCOUNT<>0 THROW 52015,N'Du lieu thay doi hoac transaction chua dong.',1;
SELECT N'LIVE_DEMO_PASS' AS Result,CONVERT(varchar(64),@BeforeHash,2) AS PriceHashBefore,
 CONVERT(varchar(64),@AfterHash,2) AS PriceHashAfter,@@TRANCOUNT AS OpenTransactions;
GO
