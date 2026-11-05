-- MarketLab VN30 - EOD extension, migration version 1 (business database side).
-- Run against ONE explicit business database:  sqlcmd -S . -E -C -b -d <Database> -i sql\13_eod_extension.sql
-- Idempotent. Adds NO table: the 13 business tables, their keys, CHECKs and other triggers are untouched.
-- Changes:
--   1. schema [ops] holding procedure ops.usp_EodApplySession (all-or-nothing session apply);
--   2. dbo.tr_Dataset_Guard: allows ONE extra case - a forward-only ObservedThrough move on a
--      REAL_PRIVATE dataset, with every other semantic column unchanged, issued inside
--      ops.usp_EodApplySession (SESSION_CONTEXT marker). All other changes still raise 51007.
--   3. database extended property MarketLabEodExtension = 1.
-- Operational tables (runs, audit, reconciliation) live in a separate ops database (sql/14_ops_database.sql)
-- so that the original 44 validation tests (which assert exactly 13 tables) keep their meaning.
-- Rollback: sql/13_eod_extension_rollback.sql. Preflight: sql/13_eod_preflight.sql.
-- DO NOT run on a research database without a verified backup and explicit owner approval.
SET NOCOUNT ON;
SET XACT_ABORT ON;
SET QUOTED_IDENTIFIER ON;
SET ANSI_NULLS ON;
GO
IF DB_NAME() IN (N'master',N'model',N'msdb',N'tempdb',N'MarketLabVN30_Demo')
BEGIN
 RAISERROR(N'13_eod_extension: refused on this database (public synthetic demo or system DB).',16,1);
 SET NOEXEC ON;
END;
GO
IF NOT EXISTS(SELECT 1 FROM sys.extended_properties WHERE class=0 AND name=N'MarketLabSchema' AND CONVERT(nvarchar(50),value)=N'1.0')
 OR (SELECT COUNT(*) FROM sys.tables t WHERE t.is_ms_shipped=0 AND SCHEMA_NAME(t.schema_id)=N'dbo'
     AND t.name IN (N'Market',N'Industry',N'Stock',N'Dataset',N'TradingDay',N'DailyPrice',N'StockIndex',N'IndexMembership',
                    N'ForecastModel',N'TargetDefinition',N'ModelRun',N'ForecastOrigin',N'Prediction'))<>13
 OR OBJECT_ID(N'dbo.usp_InsertDailyPrice',N'P') IS NULL
 OR OBJECT_ID(N'dbo.fn_EligiblePredictions',N'IF') IS NULL
BEGIN
 RAISERROR(N'13_eod_extension: database is not a complete MarketLab 1.0 schema. Nothing changed.',16,1);
 SET NOEXEC ON;
END;
GO
IF @@TRANCOUNT<>0
BEGIN
 RAISERROR(N'13_eod_extension: close open transactions first.',16,1);
 SET NOEXEC ON;
END;
GO
IF SCHEMA_ID(N'ops') IS NULL EXEC(N'CREATE SCHEMA ops AUTHORIZATION dbo;');
GO
CREATE OR ALTER TRIGGER dbo.tr_Dataset_Guard ON dbo.Dataset AFTER UPDATE AS
BEGIN
 SET NOCOUNT ON;
 -- MarketLab EOD extension v1. Original rule kept verbatim; the only exception is the guarded,
 -- forward-only ObservedThrough move for REAL_PRIVATE datasets issued by ops.usp_EodApplySession.
 IF EXISTS(SELECT 1 FROM inserted i JOIN deleted o ON o.DatasetId=i.DatasetId
 WHERE (EXISTS(SELECT 1 FROM dbo.DailyPrice p WHERE p.DatasetId=i.DatasetId) OR EXISTS(SELECT 1 FROM dbo.ModelRun r WHERE r.DatasetId=i.DatasetId))
 AND EXISTS(SELECT i.MarketId,i.DataKind,i.PriceBasis,i.PriceUnit,i.ObservedThrough EXCEPT SELECT o.MarketId,o.DataKind,o.PriceBasis,o.PriceUnit,o.ObservedThrough)
 AND NOT (o.DataKind='REAL_PRIVATE' AND i.DataKind='REAL_PRIVATE'
      AND NOT EXISTS(SELECT i.MarketId,i.DataKind,i.PriceBasis,i.PriceUnit EXCEPT SELECT o.MarketId,o.DataKind,o.PriceBasis,o.PriceUnit)
      AND i.ObservedThrough>o.ObservedThrough
      AND CONVERT(nvarchar(64),SESSION_CONTEXT(N'MarketLab.EodRunRef')) IS NOT NULL))
 THROW 51007,N'Ngu nghia dataset da su dung la bat bien; tao dataset moi.',1;
END;
GO
-- All-or-nothing apply of one session for one dataset.
-- @PricesJson: [{"StockId":1,"Open":"21.5","High":"21.9","Low":"21.3","Close":"21.8","Volume":"1000"}, ...]
-- (decimal values as strings: no float rounding). Caller validates precision <= 6 decimals before calling.
-- Result set 1: per-stock outcome (INSERTED / UNCHANGED / WOULD_INSERT).  Result set 2: one summary row.
-- Errors: 51140 open transaction, 51141 dataset not REAL_PRIVATE/unknown, 51142 universe incomplete or
-- duplicated, 51143 stock outside dataset scope, 51144 lock busy, 51145 conflicting existing price
-- (requires human reconciliation), 51146 bad date/JSON. Underlying 510xx errors propagate unchanged.
CREATE OR ALTER PROCEDURE ops.usp_EodApplySession
 @DatasetId int,
 @SessionDate date,
 @EodRunRef varchar(64),
 @PricesJson nvarchar(max),
 @ExpectedStockIdsJson nvarchar(max),
 @DryRun bit = 0
AS
BEGIN
 SET NOCOUNT ON; SET XACT_ABORT ON;
 IF @@TRANCOUNT<>0 THROW 51140,N'ops.usp_EodApplySession must start outside a transaction.',1;
 IF @SessionDate IS NULL OR NULLIF(LTRIM(RTRIM(@EodRunRef)),'') IS NULL OR ISJSON(@PricesJson)<>1 OR ISJSON(@ExpectedStockIdsJson)<>1
  THROW 51146,N'Session date, run reference or JSON payload invalid.',1;
 DECLARE @TodayVN date=CONVERT(date,SYSDATETIMEOFFSET() AT TIME ZONE 'SE Asia Standard Time');
 IF @SessionDate>@TodayVN THROW 51146,N'Session date is in the future (Asia/Ho_Chi_Minh).',1;
 IF NOT EXISTS(SELECT 1 FROM dbo.Dataset WHERE DatasetId=@DatasetId AND DataKind='REAL_PRIVATE')
  THROW 51141,N'Dataset does not exist or is not REAL_PRIVATE; EOD sync refused.',1;

 DECLARE @Rows TABLE(StockId int NOT NULL PRIMARY KEY,OpenPrice decimal(19,6) NOT NULL,HighPrice decimal(19,6) NOT NULL,
  LowPrice decimal(19,6) NOT NULL,ClosePrice decimal(19,6) NOT NULL,Volume bigint NOT NULL);
 DECLARE @Expected TABLE(StockId int NOT NULL PRIMARY KEY);
 DECLARE @Outcome TABLE(StockId int NOT NULL PRIMARY KEY,Outcome varchar(20) NOT NULL);
 BEGIN TRY
  INSERT @Expected(StockId) SELECT DISTINCT CONVERT(int,value) FROM OPENJSON(@ExpectedStockIdsJson);
  INSERT @Rows SELECT StockId,OpenPrice,HighPrice,LowPrice,ClosePrice,Volume
  FROM OPENJSON(@PricesJson) WITH(StockId int '$.StockId',OpenPrice decimal(19,6) '$.Open',HighPrice decimal(19,6) '$.High',
   LowPrice decimal(19,6) '$.Low',ClosePrice decimal(19,6) '$.Close',Volume bigint '$.Volume');
 END TRY
 BEGIN CATCH
  THROW 51142,N'Price payload has duplicate/NULL stock keys or non-numeric values.',1;
 END CATCH;
 IF NOT EXISTS(SELECT 1 FROM @Expected)
  THROW 51142,N'Expected universe is empty.',1;
 IF EXISTS(SELECT StockId FROM @Expected EXCEPT SELECT StockId FROM @Rows) OR EXISTS(SELECT StockId FROM @Rows EXCEPT SELECT StockId FROM @Expected)
  THROW 51142,N'Universe incomplete or contains unexpected stocks; nothing written.',1;
 IF EXISTS(SELECT 1 FROM @Rows r LEFT JOIN dbo.Stock s ON s.StockId=r.StockId JOIN dbo.Dataset d ON d.DatasetId=@DatasetId
           WHERE s.StockId IS NULL OR s.MarketId<>d.MarketId OR s.IsSynthetic<>0)
  THROW 51143,N'Stock outside dataset market or not REAL stock.',1;

 DECLARE @ObservedBefore date,@ObservedAfter date,@DayInserted bit=0,@Lock int;
 BEGIN TRY
  BEGIN TRANSACTION;
  DECLARE @Resource nvarchar(255)=CONCAT(N'MarketLab.EOD.',DB_NAME(),N'.',@DatasetId);
  EXEC @Lock=sys.sp_getapplock @Resource=@Resource,@LockMode='Exclusive',@LockOwner='Transaction',@LockTimeout=0;
  IF @Lock<0 THROW 51144,N'Another EOD job holds this dataset lock.',1;

  IF EXISTS(SELECT 1 FROM @Rows r JOIN dbo.DailyPrice p WITH(UPDLOCK,HOLDLOCK)
            ON p.DatasetId=@DatasetId AND p.StockId=r.StockId AND p.TradeDate=@SessionDate
            WHERE EXISTS(SELECT r.OpenPrice,r.HighPrice,r.LowPrice,r.ClosePrice,r.Volume
                         EXCEPT SELECT p.OpenPrice,p.HighPrice,p.LowPrice,p.ClosePrice,p.Volume))
   THROW 51145,N'Existing closed price differs from provider; human reconciliation required. Nothing written.',1;

  SELECT @ObservedBefore=ObservedThrough FROM dbo.Dataset WITH(UPDLOCK) WHERE DatasetId=@DatasetId;
  IF NOT EXISTS(SELECT 1 FROM dbo.TradingDay WHERE DatasetId=@DatasetId AND TradeDate=@SessionDate)
  BEGIN
   INSERT dbo.TradingDay(DatasetId,TradeDate) VALUES(@DatasetId,@SessionDate);  -- tr_TradingDay_Guard protects stored horizons
   SET @DayInserted=1;
  END;
  IF @SessionDate>@ObservedBefore
  BEGIN
   EXEC sys.sp_set_session_context @key=N'MarketLab.EodRunRef',@value=@EodRunRef;
   UPDATE dbo.Dataset SET ObservedThrough=@SessionDate WHERE DatasetId=@DatasetId;
   EXEC sys.sp_set_session_context @key=N'MarketLab.EodRunRef',@value=NULL;
  END;

  INSERT @Outcome(StockId,Outcome)
  SELECT r.StockId,CASE WHEN p.StockId IS NULL THEN CASE WHEN @DryRun=1 THEN 'WOULD_INSERT' ELSE 'INSERTED' END ELSE 'UNCHANGED' END
  FROM @Rows r LEFT JOIN dbo.DailyPrice p ON p.DatasetId=@DatasetId AND p.StockId=r.StockId AND p.TradeDate=@SessionDate;

  DECLARE @S int,@O decimal(19,6),@H decimal(19,6),@L decimal(19,6),@C decimal(19,6),@V bigint;
  DECLARE price_cursor CURSOR LOCAL FAST_FORWARD FOR SELECT StockId,OpenPrice,HighPrice,LowPrice,ClosePrice,Volume FROM @Rows ORDER BY StockId;
  OPEN price_cursor;
  FETCH NEXT FROM price_cursor INTO @S,@O,@H,@L,@C,@V;
  WHILE @@FETCH_STATUS=0
  BEGIN
   EXEC dbo.usp_InsertDailyPrice @DatasetId,@S,@SessionDate,@O,@H,@L,@C,@V,@AllowUpdate=0;
   FETCH NEXT FROM price_cursor INTO @S,@O,@H,@L,@C,@V;
  END;
  CLOSE price_cursor; DEALLOCATE price_cursor;

  SELECT @ObservedAfter=ObservedThrough FROM dbo.Dataset WHERE DatasetId=@DatasetId;
  IF @DryRun=1 ROLLBACK; ELSE COMMIT;
 END TRY
 BEGIN CATCH
  IF XACT_STATE()<>0 ROLLBACK;
  EXEC sys.sp_set_session_context @key=N'MarketLab.EodRunRef',@value=NULL;
  THROW;
 END CATCH;

 SELECT o.StockId,s.Ticker,o.Outcome FROM @Outcome o JOIN dbo.Stock s ON s.StockId=o.StockId ORDER BY s.Ticker;
 SELECT @DatasetId AS DatasetId,@SessionDate AS SessionDate,@DryRun AS DryRun,
  (SELECT COUNT(*) FROM @Outcome WHERE Outcome='INSERTED') AS InsertedCount,
  (SELECT COUNT(*) FROM @Outcome WHERE Outcome='UNCHANGED') AS UnchangedCount,
  (SELECT COUNT(*) FROM @Outcome WHERE Outcome='WOULD_INSERT') AS WouldInsertCount,
  @DayInserted AS TradingDayInserted,@ObservedBefore AS ObservedThroughBefore,
  CASE WHEN @DryRun=1 THEN @ObservedBefore ELSE @ObservedAfter END AS ObservedThroughAfter,
  CASE WHEN @DryRun=1 THEN @ObservedAfter END AS ObservedThroughWouldBe;
END;
GO
IF NOT EXISTS(SELECT 1 FROM sys.extended_properties WHERE class=0 AND name=N'MarketLabEodExtension')
 EXEC sys.sp_addextendedproperty @name=N'MarketLabEodExtension',@value=N'1';
GO
SELECT N'EOD_EXTENSION_V1_APPLIED' AS Result,DB_NAME() AS DatabaseName,
 (SELECT COUNT(*) FROM sys.tables WHERE is_ms_shipped=0) AS TableCount,
 OBJECT_ID(N'ops.usp_EodApplySession') AS ApplyProcObjectId;
GO
SET NOEXEC OFF;
GO
