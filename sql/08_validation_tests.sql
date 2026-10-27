USE [MarketLabVN30_Demo];
GO
SET NOCOUNT ON;
CREATE TABLE #TestResults(TestName nvarchar(150),Status varchar(4),Evidence nvarchar(2000));
GO
CREATE PROCEDURE #RunTest @Name nvarchar(150),@Sql nvarchar(max),@Expected int=NULL,@Contains nvarchar(150)=NULL AS
BEGIN
 SET NOCOUNT ON; SET XACT_ABORT OFF;
 BEGIN TRY
  BEGIN TRANSACTION;
  EXEC sys.sp_executesql @Sql;
  IF @@TRANCOUNT<>1 THROW 51901,'Test transaction scope corrupted',1;
  ROLLBACK;
  INSERT #TestResults VALUES(@Name,CASE WHEN @Expected IS NULL THEN 'PASS' ELSE 'FAIL' END,CASE WHEN @Expected IS NULL THEN N'Executed; all writes rolled back' ELSE N'Expected rejection did not occur' END);
 END TRY
 BEGIN CATCH
  DECLARE @Err int=ERROR_NUMBER(),@Message nvarchar(2000)=ERROR_MESSAGE();
  IF XACT_STATE()<>0 ROLLBACK;
  INSERT #TestResults VALUES(@Name,CASE WHEN @Expected=@Err AND (@Contains IS NULL OR CHARINDEX(@Contains,@Message)>0) THEN 'PASS' ELSE 'FAIL' END,CONCAT(@Err,N': ',@Message));
 END CATCH;
END;
GO

EXEC #RunTest N'PK rejects duplicate',N'INSERT dbo.Market SELECT TOP(1) * FROM dbo.Market;',2627,N'PK_Market';
GO

EXEC #RunTest N'UNIQUE rejects duplicate code',N'INSERT dbo.Market SELECT 90001,MarketCode,N''Test'',''VND'' FROM dbo.Market WHERE MarketId=1;',2627,N'UQ_Market_Code';
GO

EXEC #RunTest N'FK rejects unknown industry',N'INSERT dbo.Stock(StockId,MarketId,Ticker,IndustryId) VALUES(90001,1,''ZZTEST'',999999);',547,N'FK_Stock_Industry';
GO

EXEC #RunTest N'NOT NULL rejects missing name',N'INSERT dbo.Industry VALUES(90001,''ZZTEST'',NULL,N''Test'');',515,N'IndustryName';
GO

EXEC #RunTest N'CHECK positive price',N'DECLARE @D int=(SELECT MIN(DatasetId) FROM dbo.Dataset),@S int=(SELECT MIN(StockId) FROM dbo.Stock),
@R int=(SELECT MIN(RunId) FROM dbo.ModelRun),@DT date=(SELECT MIN(TradeDate) FROM dbo.DailyPrice);
UPDATE dbo.DailyPrice SET OpenPrice=0,HighPrice=0,LowPrice=0,ClosePrice=0 WHERE DatasetId=@D AND StockId=@S AND TradeDate=@DT;',547,N'CK_DailyPrice_Positive';
GO

EXEC #RunTest N'CHECK OHLC range',N'DECLARE @D int=(SELECT MIN(DatasetId) FROM dbo.Dataset),@S int=(SELECT MIN(StockId) FROM dbo.Stock),
@R int=(SELECT MIN(RunId) FROM dbo.ModelRun),@DT date=(SELECT MIN(TradeDate) FROM dbo.DailyPrice);
UPDATE dbo.DailyPrice SET HighPrice=LowPrice/2 WHERE DatasetId=@D AND StockId=@S AND TradeDate=@DT;',547,N'CK_DailyPrice_OHLC';
GO

EXEC #RunTest N'CHECK negative volume',N'DECLARE @D int=(SELECT MIN(DatasetId) FROM dbo.Dataset),@S int=(SELECT MIN(StockId) FROM dbo.Stock),
@R int=(SELECT MIN(RunId) FROM dbo.ModelRun),@DT date=(SELECT MIN(TradeDate) FROM dbo.DailyPrice);
UPDATE dbo.DailyPrice SET Volume=-1 WHERE DatasetId=@D AND StockId=@S AND TradeDate=@DT;',547,N'CK_DailyPrice_Volume';
GO

EXEC #RunTest N'FK rejects date outside calendar',N'DECLARE @D int=(SELECT MIN(DatasetId) FROM dbo.Dataset),@S int=(SELECT MIN(StockId) FROM dbo.Stock),
@R int=(SELECT MIN(RunId) FROM dbo.ModelRun),@DT date=(SELECT MIN(TradeDate) FROM dbo.DailyPrice);
INSERT dbo.DailyPrice(DatasetId,StockId,TradeDate,OpenPrice,HighPrice,LowPrice,ClosePrice,Volume) VALUES(@D,@S,''19000101'',10,11,9,10,0);',547,N'FK_DailyPrice_TradingDay';
GO

EXEC #RunTest N'CHECK probability',N'DECLARE @D int=(SELECT MIN(DatasetId) FROM dbo.Dataset),@S int=(SELECT MIN(StockId) FROM dbo.Stock),
@R int=(SELECT MIN(RunId) FROM dbo.ModelRun),@DT date=(SELECT MIN(TradeDate) FROM dbo.DailyPrice);
UPDATE dbo.Prediction SET ProbabilityPositive=1.1 WHERE RunId=@R;',547,N'CK_Prediction_Probability';
GO

EXEC #RunTest N'CHECK target ordering',N'DECLARE @D int=(SELECT MIN(DatasetId) FROM dbo.Dataset),@S int=(SELECT MIN(StockId) FROM dbo.Stock),
@R int=(SELECT MIN(RunId) FROM dbo.ModelRun),@DT date=(SELECT MIN(TradeDate) FROM dbo.DailyPrice);
UPDATE dbo.ForecastOrigin SET TargetDate=OriginDate WHERE RunId=@R;',547,N'CK_ForecastOrigin_Dates';
GO

EXEC #RunTest N'TRIGGER native horizon',N'DECLARE @D int=(SELECT MIN(DatasetId) FROM dbo.Dataset),@S int=(SELECT MIN(StockId) FROM dbo.Stock),
@R int=(SELECT MIN(RunId) FROM dbo.ModelRun),@DT date=(SELECT MIN(TradeDate) FROM dbo.DailyPrice);
UPDATE dbo.ForecastOrigin SET TargetDate=DATEADD(day,1,TargetDate) WHERE RunId=@R;',51002,NULL;
GO

EXEC #RunTest N'TRIGGER out of sample',N'DECLARE @D int=(SELECT MIN(DatasetId) FROM dbo.Dataset),@S int=(SELECT MIN(StockId) FROM dbo.Stock),
@R int=(SELECT MIN(RunId) FROM dbo.ModelRun),@DT date=(SELECT MIN(TradeDate) FROM dbo.DailyPrice);
INSERT dbo.TradingDay VALUES(@D,''20241231''); DECLARE @T date=(SELECT MIN(TargetDate) FROM dbo.ForecastOrigin); EXEC dbo.usp_AddPrediction @R,@S,''20241231'',@T,0.4;',51002,NULL;
GO

EXEC #RunTest N'TRIGGER overlap membership',N'INSERT dbo.IndexMembership SELECT TOP(1) IndexId,StockId,DATEADD(day,1,ValidFrom),ValidTo,N''Overlap test'' FROM dbo.IndexMembership;',51004,NULL;
GO

EXEC #RunTest N'TRIGGER immutable run',N'DECLARE @D int=(SELECT MIN(DatasetId) FROM dbo.Dataset),@S int=(SELECT MIN(StockId) FROM dbo.Stock),
@R int=(SELECT MIN(RunId) FROM dbo.ModelRun),@DT date=(SELECT MIN(TradeDate) FROM dbo.DailyPrice);
UPDATE dbo.ModelRun SET Threshold=0.6 WHERE RunId=@R;',51006,NULL;
GO

EXEC #RunTest N'TRIGGER immutable target',N'UPDATE dbo.TargetDefinition SET HorizonSessions=HorizonSessions+1;',51009,NULL;
GO

EXEC #RunTest N'TRIGGER immutable dataset',N'UPDATE dbo.Dataset SET ObservedThrough=DATEADD(day,1,ObservedThrough);',51007,NULL;
GO

EXEC #RunTest N'TRIGGER immutable stock',N'DECLARE @D int=(SELECT MIN(DatasetId) FROM dbo.Dataset),@S int=(SELECT MIN(StockId) FROM dbo.Stock),
@R int=(SELECT MIN(RunId) FROM dbo.ModelRun),@DT date=(SELECT MIN(TradeDate) FROM dbo.DailyPrice);
UPDATE dbo.Stock SET IsSynthetic=1-IsSynthetic WHERE StockId=@S;',51008,NULL;
GO

EXEC #RunTest N'TRIGGER calendar preserves endpoint',N'DECLARE @D int=(SELECT MIN(DatasetId) FROM dbo.Dataset),@S int=(SELECT MIN(StockId) FROM dbo.Stock),
@R int=(SELECT MIN(RunId) FROM dbo.ModelRun),@DT date=(SELECT MIN(TradeDate) FROM dbo.DailyPrice);
DECLARE @Gap date; SELECT TOP(1) @Gap=DATEADD(day,n.n,@DT) FROM (VALUES(1),(2),(3),(4),(5),(6),(7)) n(n) WHERE NOT EXISTS(SELECT 1 FROM dbo.TradingDay td WHERE td.DatasetId=@D AND td.TradeDate=DATEADD(day,n.n,@DT)) ORDER BY n.n; INSERT dbo.TradingDay VALUES(@D,@Gap);',51022,NULL;
GO

EXEC #RunTest N'SP price invalid',N'DECLARE @D int=(SELECT MIN(DatasetId) FROM dbo.Dataset),@S int=(SELECT MIN(StockId) FROM dbo.Stock),
@R int=(SELECT MIN(RunId) FROM dbo.ModelRun),@DT date=(SELECT MIN(TradeDate) FROM dbo.DailyPrice);
EXEC dbo.usp_InsertDailyPrice @D,@S,@DT,10,9,8,10,100;',51010,NULL;
GO

EXEC #RunTest N'SP price conflicting duplicate',N'DECLARE @D int=(SELECT MIN(DatasetId) FROM dbo.Dataset),@S int=(SELECT MIN(StockId) FROM dbo.Stock),
@R int=(SELECT MIN(RunId) FROM dbo.ModelRun),@DT date=(SELECT MIN(TradeDate) FROM dbo.DailyPrice);
EXEC dbo.usp_InsertDailyPrice @D,@S,@DT,10,11,9,10,999;',51012,NULL;
GO

EXEC #RunTest N'SP price invalid calendar',N'DECLARE @D int=(SELECT MIN(DatasetId) FROM dbo.Dataset),@S int=(SELECT MIN(StockId) FROM dbo.Stock),
@R int=(SELECT MIN(RunId) FROM dbo.ModelRun),@DT date=(SELECT MIN(TradeDate) FROM dbo.DailyPrice);
EXEC dbo.usp_InsertDailyPrice @D,@S,''19000101'',10,11,9,10,0;',51011,NULL;
GO

EXEC #RunTest N'SP prediction invalid probability',N'DECLARE @D int=(SELECT MIN(DatasetId) FROM dbo.Dataset),@S int=(SELECT MIN(StockId) FROM dbo.Stock),
@R int=(SELECT MIN(RunId) FROM dbo.ModelRun),@DT date=(SELECT MIN(TradeDate) FROM dbo.DailyPrice);
EXEC dbo.usp_AddPrediction @R,@S,''20250101'',''20250201'',1.1;',51013,NULL;
GO

EXEC #RunTest N'SP prediction unknown run',N'DECLARE @D int=(SELECT MIN(DatasetId) FROM dbo.Dataset),@S int=(SELECT MIN(StockId) FROM dbo.Stock),
@R int=(SELECT MIN(RunId) FROM dbo.ModelRun),@DT date=(SELECT MIN(TradeDate) FROM dbo.DailyPrice);
EXEC dbo.usp_AddPrediction 999999,@S,''20250101'',''20250201'',0.5;',51014,NULL;
GO

EXEC #RunTest N'SP prediction conflicting duplicate',N'DECLARE @D int=(SELECT MIN(DatasetId) FROM dbo.Dataset),@S int=(SELECT MIN(StockId) FROM dbo.Stock),
@R int=(SELECT MIN(RunId) FROM dbo.ModelRun),@DT date=(SELECT MIN(TradeDate) FROM dbo.DailyPrice);
DECLARE @O date,@T date,@P decimal(19,16); SELECT TOP(1) @O=p.OriginDate,@T=f.TargetDate,@P=p.ProbabilityPositive FROM dbo.Prediction p JOIN dbo.ForecastOrigin f ON f.RunId=p.RunId AND f.OriginDate=p.OriginDate WHERE p.RunId=@R AND p.StockId=@S; SET @P=CASE WHEN @P=0.1 THEN 0.2 ELSE 0.1 END; EXEC dbo.usp_AddPrediction @R,@S,@O,@T,@P;',51015,NULL;
GO

EXEC #RunTest N'SP performance invalid filter',N'EXEC dbo.usp_GetModelPerformance ''missing'',1,20,''20260101'',''20250101'',''20260701'';',51016,NULL;
GO

EXEC #RunTest N'SP performance unknown model',N'EXEC dbo.usp_GetModelPerformance ''missing'',1,20,''20250101'',''20260101'',''20260701'';',51017,NULL;
GO

EXEC #RunTest N'SP compare invalid id',N'EXEC dbo.usp_CompareModels ''1,abc'',''20250101'',''20260101'',''20260701'';',51018,NULL;
GO

EXEC #RunTest N'SP compare missing run',N'EXEC dbo.usp_CompareModels ''1,999999'',''20250101'',''20260101'',''20260701'';',51019,NULL;
GO

EXEC #RunTest N'SP compare no mature overlap',N'EXEC dbo.usp_CompareModels ''1,2'',''20250101'',''20260101'',''19000101'';',51021,NULL;
GO

EXEC #RunTest N'SP compare incompatible targets',N'INSERT dbo.TargetDefinition VALUES(999,''TEST_H999'',999,''PROBABILITY_CLOSE_UP'',''CLOSE_TARGET_GT_CLOSE_ORIGIN_ELSE_ZERO''); INSERT dbo.ModelRun SELECT 999,''TEST_RUN_999'',ModelId,DatasetId,999,TrainStart,TrainEnd,ValidationEnd,SelectedC,Threshold,EvaluationClass,SourceRun,CompletedAt FROM dbo.ModelRun WHERE RunId=1; EXEC dbo.usp_CompareModels ''1,999'',''20250101'',''20260101'',''20260701'';',51020,NULL;
GO

EXEC #RunTest N'Functions return/zero/null',N'IF dbo.fn_CalculateReturn(100,110)<>10 OR dbo.fn_CalculateReturn(0,10) IS NOT NULL OR dbo.fn_CalculateReturn(NULL,10) IS NOT NULL OR dbo.fn_CheckPredictionDirection(0,0)<>1 OR dbo.fn_CheckPredictionDirection(0,1)<>0 OR dbo.fn_CheckPredictionDirection(NULL,1) IS NOT NULL THROW 51900,''Bad function result'',1;';
GO

EXEC #RunTest N'Schema thirteen tables',N'IF (SELECT COUNT(*) FROM sys.tables WHERE is_ms_shipped=0)<>13 THROW 51900,''Table count'',1;';
GO

EXEC #RunTest N'Constraints enabled and trusted',N'IF EXISTS(SELECT 1 FROM sys.foreign_keys WHERE is_disabled=1 OR is_not_trusted=1) OR EXISTS(SELECT 1 FROM sys.check_constraints WHERE is_disabled=1 OR is_not_trusted=1) THROW 51900,''Disabled constraint'',1;';
GO

EXEC #RunTest N'DEFAULT stock flag',N'INSERT dbo.Stock(StockId,MarketId,Ticker) VALUES(90001,1,''ZZTEST''); IF (SELECT IsSynthetic FROM dbo.Stock WHERE StockId=90001)<>0 THROW 51900,''Default not applied'',1;';
GO

EXEC #RunTest N'DEFAULT load timestamp',N'DECLARE @D int=(SELECT MIN(DatasetId) FROM dbo.Dataset),@S int=(SELECT MIN(StockId) FROM dbo.Stock),
@R int=(SELECT MIN(RunId) FROM dbo.ModelRun),@DT date=(SELECT MIN(TradeDate) FROM dbo.DailyPrice);
DECLARE @Syn bit=(SELECT CASE WHEN DataKind=''SYNTHETIC'' THEN 1 ELSE 0 END FROM dbo.Dataset WHERE DatasetId=@D); INSERT dbo.Stock(StockId,MarketId,Ticker,IsSynthetic) VALUES(90001,1,''ZZTEST'',@Syn); EXEC dbo.usp_InsertDailyPrice @D,90001,@DT,10,11,9,10,0; IF (SELECT LoadedAt FROM dbo.DailyPrice WHERE StockId=90001) IS NULL THROW 51900,''Missing default timestamp'',1;';
GO

EXEC #RunTest N'SP price idempotent',N'DECLARE @D int=(SELECT MIN(DatasetId) FROM dbo.Dataset),@S int=(SELECT MIN(StockId) FROM dbo.Stock),
@R int=(SELECT MIN(RunId) FROM dbo.ModelRun),@DT date=(SELECT MIN(TradeDate) FROM dbo.DailyPrice);
DECLARE @O decimal(19,6),@H decimal(19,6),@L decimal(19,6),@C decimal(19,6),@V bigint,@N int=(SELECT COUNT(*) FROM dbo.DailyPrice); SELECT @O=OpenPrice,@H=HighPrice,@L=LowPrice,@C=ClosePrice,@V=Volume FROM dbo.DailyPrice WHERE DatasetId=@D AND StockId=@S AND TradeDate=@DT; EXEC dbo.usp_InsertDailyPrice @D,@S,@DT,@O,@H,@L,@C,@V; IF (SELECT COUNT(*) FROM dbo.DailyPrice)<>@N THROW 51900,''Duplicate price'',1;';
GO

EXEC #RunTest N'SP price explicit update',N'DECLARE @D int=(SELECT MIN(DatasetId) FROM dbo.Dataset),@S int=(SELECT MIN(StockId) FROM dbo.Stock),
@R int=(SELECT MIN(RunId) FROM dbo.ModelRun),@DT date=(SELECT MIN(TradeDate) FROM dbo.DailyPrice);
DECLARE @O decimal(19,6),@H decimal(19,6),@L decimal(19,6),@C decimal(19,6),@V bigint; SELECT @O=OpenPrice,@H=HighPrice,@L=LowPrice,@C=ClosePrice,@V=Volume+1 FROM dbo.DailyPrice WHERE DatasetId=@D AND StockId=@S AND TradeDate=@DT; EXEC dbo.usp_InsertDailyPrice @D,@S,@DT,@O,@H,@L,@C,@V,1; IF (SELECT Volume FROM dbo.DailyPrice WHERE DatasetId=@D AND StockId=@S AND TradeDate=@DT)<>@V THROW 51900,''Update failed'',1;';
GO

EXEC #RunTest N'SP prediction insert then replay',N'DECLARE @D int=(SELECT MIN(DatasetId) FROM dbo.Dataset),@S int=(SELECT MIN(StockId) FROM dbo.Stock),
@R int=(SELECT MIN(RunId) FROM dbo.ModelRun),@DT date=(SELECT MIN(TradeDate) FROM dbo.DailyPrice);
DECLARE @Syn bit=(SELECT CASE WHEN DataKind=''SYNTHETIC'' THEN 1 ELSE 0 END FROM dbo.Dataset WHERE DatasetId=@D),@O date,@T date; SELECT TOP(1) @O=OriginDate,@T=TargetDate FROM dbo.ForecastOrigin WHERE RunId=@R; INSERT dbo.Stock(StockId,MarketId,Ticker,IsSynthetic) VALUES(90001,1,''ZZTEST'',@Syn); EXEC dbo.usp_AddPrediction @R,90001,@O,@T,0.4; EXEC dbo.usp_AddPrediction @R,90001,@O,@T,0.4; IF (SELECT COUNT(*) FROM dbo.Prediction WHERE StockId=90001)<>1 THROW 51900,''Prediction replay failed'',1;';
GO

EXEC #RunTest N'AsOf prevents future actuals',N'IF EXISTS(SELECT 1 FROM dbo.fn_EligiblePredictions(''19000101'')) THROW 51900,''Future leak'',1; DECLARE @Cut date=(SELECT MIN(TargetDate) FROM dbo.ForecastOrigin); IF EXISTS(SELECT 1 FROM dbo.fn_EligiblePredictions(@Cut) WHERE TargetDate>@Cut) THROW 51900,''AsOf leak'',1;';
GO

EXEC #RunTest N'Missing endpoint excluded',N'DECLARE @R int=1,@S int=1,@T date=(SELECT MIN(TargetDate) FROM dbo.ForecastOrigin WHERE RunId=1); DELETE dbo.DailyPrice WHERE StockId=@S AND TradeDate=@T; IF EXISTS(SELECT 1 FROM dbo.fn_EligiblePredictions(''20990101'') WHERE StockId=@S AND TargetDate=@T) THROW 51900,''Missing endpoint included'',1;';
GO

EXEC #RunTest N'SP performance returns evaluated rows',N'CREATE TABLE #P(RunId int,ModelCode varchar(70),DatasetId int,HorizonSessions int,EvaluationAsOf date,EvaluatedRows bigint,Accuracy decimal(38,10),BrierScore float); DECLARE @M varchar(70)=(SELECT ModelCode FROM dbo.ForecastModel WHERE ModelId=1),@H int=(SELECT HorizonSessions FROM dbo.TargetDefinition WHERE TargetId=1); INSERT #P EXEC dbo.usp_GetModelPerformance @M,1,@H,''20250101'',''20260101'',''20260701''; IF NOT EXISTS(SELECT 1 FROM #P WHERE EvaluatedRows>0) THROW 51900,''Performance empty'',1;';
GO

EXEC #RunTest N'SP comparison uses common observations',N'DECLARE @N int=(SELECT COUNT(*) FROM dbo.fn_EligiblePredictions(''20260701'') WHERE RunId=1); DELETE FROM dbo.Prediction WHERE RunId=2 AND StockId=1 AND OriginDate=(SELECT MIN(OriginDate) FROM dbo.Prediction); CREATE TABLE #C(RunId int,ModelCode varchar(70),CommonObservations bigint,EvaluationAsOf date,Accuracy decimal(38,10),BrierScore float); INSERT #C EXEC dbo.usp_CompareModels ''1,2'',''20250101'',''20260101'',''20260701''; IF (SELECT COUNT(*) FROM #C)<>2 OR EXISTS(SELECT 1 FROM #C WHERE CommonObservations<>@N-1) THROW 51900,''Unequal support compared'',1;';
GO

EXEC #RunTest N'COMMIT then ROLLBACK',N'-- A committed inner transaction remains part of the outer harness transaction.
BEGIN TRANSACTION; INSERT dbo.Industry VALUES(90002,''ZZCOMMIT'',N''Test'',N''Rollback by harness''); COMMIT; IF NOT EXISTS(SELECT 1 FROM dbo.Industry WHERE IndustryId=90002) THROW 51900,''Commit failed'',1; SAVE TRANSACTION TestSave; INSERT dbo.Industry VALUES(90003,''ZZROLLBACK'',N''Test'',N''Test''); ROLLBACK TRANSACTION TestSave; IF EXISTS(SELECT 1 FROM dbo.Industry WHERE IndustryId=90003) THROW 51900,''Savepoint rollback failed'',1;';
GO

EXEC #RunTest N'Views execute',N'DECLARE @N bigint; SELECT @N=COUNT_BIG(*) FROM dbo.vw_LatestStockPrice; IF @N=0 THROW 51900,''Latest empty'',1; SELECT @N=COUNT_BIG(*) FROM dbo.vw_StudyUniverse; SELECT @N=COUNT_BIG(*) FROM dbo.vw_VN30SnapshotJune2026; SELECT @N=COUNT_BIG(*) FROM dbo.vw_ModelPerformance;';
GO

SELECT TestName,Status,Evidence FROM #TestResults ORDER BY TestName;
SELECT Status,COUNT(*) AS Tests FROM #TestResults GROUP BY Status;
IF EXISTS(SELECT 1 FROM #TestResults WHERE Status='FAIL') THROW 51999,'Validation failed; inspect TestResults',1;
DROP PROCEDURE #RunTest; DROP TABLE #TestResults;
GO
