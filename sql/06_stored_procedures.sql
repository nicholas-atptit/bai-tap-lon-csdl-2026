USE [MarketLabVN30_Demo];
GO
CREATE OR ALTER PROCEDURE dbo.usp_InsertDailyPrice
 @DatasetId int,@StockId int,@TradeDate date,@OpenPrice decimal(19,6),@HighPrice decimal(19,6),
 @LowPrice decimal(19,6),@ClosePrice decimal(19,6),@Volume bigint,@AllowUpdate bit=0
AS
BEGIN
 SET NOCOUNT ON; SET XACT_ABORT ON;
 IF @TradeDate IS NULL OR @OpenPrice IS NULL OR @HighPrice IS NULL OR @LowPrice IS NULL OR @ClosePrice IS NULL OR @Volume IS NULL
 OR @OpenPrice<=0 OR @ClosePrice<=0 OR @LowPrice<=0 OR @HighPrice<@OpenPrice OR @HighPrice<@ClosePrice OR @HighPrice<@LowPrice
 OR @LowPrice>@OpenPrice OR @LowPrice>@ClosePrice OR @Volume<0
 THROW 51010,N'OHLCV khong hop le.',1;
 IF NOT EXISTS(SELECT 1 FROM dbo.TradingDay WHERE DatasetId=@DatasetId AND TradeDate=@TradeDate)
 THROW 51011,N'Ngay khong thuoc lich phien cua dataset.',1;
 DECLARE @Own bit=CASE WHEN @@TRANCOUNT=0 THEN 1 ELSE 0 END;
 BEGIN TRY
  IF @Own=1 BEGIN TRANSACTION; ELSE SAVE TRANSACTION PriceSave;
  IF EXISTS(SELECT 1 FROM dbo.DailyPrice WITH(UPDLOCK,HOLDLOCK) WHERE DatasetId=@DatasetId AND StockId=@StockId AND TradeDate=@TradeDate)
  BEGIN
   IF EXISTS(SELECT @OpenPrice,@HighPrice,@LowPrice,@ClosePrice,@Volume EXCEPT
    SELECT OpenPrice,HighPrice,LowPrice,ClosePrice,Volume FROM dbo.DailyPrice WHERE DatasetId=@DatasetId AND StockId=@StockId AND TradeDate=@TradeDate)
   BEGIN
    IF ISNULL(@AllowUpdate,0)=0 THROW 51012,N'Khoa gia da ton tai voi gia tri khac. Can @AllowUpdate=1.',1;
    UPDATE dbo.DailyPrice SET OpenPrice=@OpenPrice,HighPrice=@HighPrice,LowPrice=@LowPrice,ClosePrice=@ClosePrice,Volume=@Volume
    WHERE DatasetId=@DatasetId AND StockId=@StockId AND TradeDate=@TradeDate;
   END;
  END
  ELSE INSERT dbo.DailyPrice(DatasetId,StockId,TradeDate,OpenPrice,HighPrice,LowPrice,ClosePrice,Volume)
   VALUES(@DatasetId,@StockId,@TradeDate,@OpenPrice,@HighPrice,@LowPrice,@ClosePrice,@Volume);
  IF @Own=1 COMMIT;
 END TRY
 BEGIN CATCH
  IF @Own=1 AND XACT_STATE()<>0 ROLLBACK;
  ELSE IF @Own=0 AND XACT_STATE()=1 ROLLBACK TRANSACTION PriceSave;
  THROW;
 END CATCH;
END;
GO
CREATE OR ALTER PROCEDURE dbo.usp_AddPrediction
 @RunId int,@StockId int,@OriginDate date,@TargetDate date,@ProbabilityPositive decimal(19,16)
AS
BEGIN
 SET NOCOUNT ON; SET XACT_ABORT ON;
 IF @OriginDate IS NULL OR @TargetDate IS NULL OR @TargetDate<=@OriginDate OR @ProbabilityPositive IS NULL OR @ProbabilityPositive NOT BETWEEN 0 AND 1
 THROW 51013,N'Ngay hoac xac suat du bao khong hop le.',1;
 IF NOT EXISTS(SELECT 1 FROM dbo.ModelRun WHERE RunId=@RunId) OR NOT EXISTS(SELECT 1 FROM dbo.Stock WHERE StockId=@StockId)
 THROW 51014,N'Ma co phieu hoac model run khong ton tai.',1;
 DECLARE @Own bit=CASE WHEN @@TRANCOUNT=0 THEN 1 ELSE 0 END;
 BEGIN TRY
  IF @Own=1 BEGIN TRANSACTION; ELSE SAVE TRANSACTION PredictionSave;
  IF EXISTS(SELECT 1 FROM dbo.ForecastOrigin WITH(UPDLOCK,HOLDLOCK) WHERE RunId=@RunId AND OriginDate=@OriginDate)
  BEGIN
   IF EXISTS(SELECT 1 FROM dbo.ForecastOrigin WHERE RunId=@RunId AND OriginDate=@OriginDate AND TargetDate<>@TargetDate)
    THROW 51015,N'Ngay muc tieu khac ngay da luu cua lan chay.',1;
  END
  ELSE INSERT dbo.ForecastOrigin(RunId,OriginDate,TargetDate) VALUES(@RunId,@OriginDate,@TargetDate);
  IF EXISTS(SELECT 1 FROM dbo.Prediction WITH(UPDLOCK,HOLDLOCK) WHERE RunId=@RunId AND StockId=@StockId AND OriginDate=@OriginDate)
  BEGIN
   IF EXISTS(SELECT @ProbabilityPositive EXCEPT SELECT ProbabilityPositive FROM dbo.Prediction WHERE RunId=@RunId AND StockId=@StockId AND OriginDate=@OriginDate)
    THROW 51015,N'Du bao trung khoa nhung khac gia tri.',1;
  END
  ELSE INSERT dbo.Prediction(RunId,StockId,OriginDate,ProbabilityPositive)
   VALUES(@RunId,@StockId,@OriginDate,@ProbabilityPositive);
  IF @Own=1 COMMIT;
 END TRY
 BEGIN CATCH
  IF @Own=1 AND XACT_STATE()<>0 ROLLBACK;
  ELSE IF @Own=0 AND XACT_STATE()=1 ROLLBACK TRANSACTION PredictionSave;
  THROW;
 END CATCH;
END;
GO
CREATE OR ALTER PROCEDURE dbo.usp_GetModelPerformance
 @ModelCode varchar(70),@DatasetId int,@HorizonSessions int,@FromDate date,@ToDate date,@AsOfDate date
AS
BEGIN
 SET NOCOUNT ON;
 IF @FromDate IS NULL OR @ToDate IS NULL OR @AsOfDate IS NULL OR @FromDate>@ToDate OR @HorizonSessions IS NULL OR @HorizonSessions<=0
 THROW 51016,N'Bo loc ngay/horizon khong hop le.',1;
 IF NOT EXISTS(SELECT 1 FROM dbo.ForecastModel WHERE ModelCode=@ModelCode) OR NOT EXISTS(SELECT 1 FROM dbo.Dataset WHERE DatasetId=@DatasetId)
 THROW 51017,N'Model hoac dataset khong ton tai.',1;
 SELECT e.RunId,m.ModelCode,e.DatasetId,e.HorizonSessions,@AsOfDate AS EvaluationAsOf,COUNT_BIG(*) AS EvaluatedRows,
 AVG(CONVERT(decimal(19,10),CASE WHEN ActualLabel=PredictedLabel THEN 1.0 ELSE 0.0 END)) AS Accuracy,
 AVG(POWER(CONVERT(float,ProbabilityPositive)-CONVERT(int,ActualLabel),2)) AS BrierScore
 FROM dbo.fn_EligiblePredictions(@AsOfDate) e JOIN dbo.ForecastModel m ON m.ModelId=e.ModelId
 WHERE m.ModelCode=@ModelCode AND e.DatasetId=@DatasetId AND e.HorizonSessions=@HorizonSessions AND e.OriginDate BETWEEN @FromDate AND @ToDate
 GROUP BY e.RunId,m.ModelCode,e.DatasetId,e.HorizonSessions;
END;
GO
CREATE OR ALTER PROCEDURE dbo.usp_CompareModels
 @RunIds varchar(200),@FromDate date,@ToDate date,@AsOfDate date
AS
BEGIN
 SET NOCOUNT ON;
 IF @FromDate IS NULL OR @ToDate IS NULL OR @AsOfDate IS NULL OR @FromDate>@ToDate OR NULLIF(LTRIM(RTRIM(@RunIds)),'') IS NULL
 THROW 51018,N'Danh sach run hoac khoang ngay khong hop le.',1;
 IF EXISTS(SELECT 1 FROM STRING_SPLIT(@RunIds,',') WHERE TRY_CONVERT(int,value) IS NULL)
 THROW 51018,N'RunId phai la so nguyen.',1;
 DECLARE @Runs TABLE(RunId int PRIMARY KEY);
 INSERT @Runs SELECT DISTINCT CONVERT(int,value) FROM STRING_SPLIT(@RunIds,',');
 DECLARE @N int=(SELECT COUNT(*) FROM @Runs);
 IF @N<2 OR @N>8 OR EXISTS(SELECT 1 FROM @Runs q LEFT JOIN dbo.ModelRun r ON r.RunId=q.RunId WHERE r.RunId IS NULL)
 THROW 51019,N'Can 2 den 8 run ton tai.',1;
 IF (SELECT COUNT(*) FROM(SELECT r.DatasetId,r.TargetId FROM dbo.ModelRun r JOIN @Runs q ON q.RunId=r.RunId GROUP BY r.DatasetId,r.TargetId) t)<>1
 THROW 51020,N'Khong so sanh khac dataset hoac dinh nghia bien muc tieu.',1;
 SELECT e.* INTO #Eligible FROM dbo.fn_EligiblePredictions(@AsOfDate) e JOIN @Runs q ON q.RunId=e.RunId
 WHERE e.OriginDate BETWEEN @FromDate AND @ToDate;
 SELECT StockId,OriginDate,TargetDate INTO #Common FROM #Eligible GROUP BY StockId,OriginDate,TargetDate HAVING COUNT(*)=@N;
 IF NOT EXISTS(SELECT 1 FROM #Common) THROW 51021,N'Khong co quan sat da truong thanh chung cho tat ca run.',1;
 SELECT e.RunId,m.ModelCode,COUNT_BIG(*) AS CommonObservations,@AsOfDate AS EvaluationAsOf,
 AVG(CONVERT(decimal(19,10),CASE WHEN e.ActualLabel=e.PredictedLabel THEN 1.0 ELSE 0.0 END)) AS Accuracy,
 AVG(POWER(CONVERT(float,e.ProbabilityPositive)-CONVERT(int,e.ActualLabel),2)) AS BrierScore
 FROM #Eligible e JOIN #Common c ON c.StockId=e.StockId AND c.OriginDate=e.OriginDate AND c.TargetDate=e.TargetDate
 JOIN dbo.ForecastModel m ON m.ModelId=e.ModelId
 GROUP BY e.RunId,m.ModelCode ORDER BY e.RunId;
END;
GO
