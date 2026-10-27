USE [MarketLabVN30_Demo];
GO
CREATE OR ALTER FUNCTION dbo.fn_CalculateReturn(@StartPrice decimal(19,6),@EndPrice decimal(19,6))
RETURNS decimal(19,8) AS
BEGIN
 RETURN CASE WHEN @StartPrice IS NULL OR @StartPrice<=0 OR @EndPrice IS NULL OR @EndPrice<=0 THEN NULL
 ELSE CONVERT(decimal(19,8),(@EndPrice-@StartPrice)/@StartPrice*100.0) END;
END;
GO
-- Three directions: negative, zero, positive. Zero matches only zero.
CREATE OR ALTER FUNCTION dbo.fn_CheckPredictionDirection(@PredictedReturn decimal(19,8),@ActualReturn decimal(19,8))
RETURNS bit AS
BEGIN
 RETURN CASE WHEN @PredictedReturn IS NULL OR @ActualReturn IS NULL THEN NULL
 WHEN SIGN(@PredictedReturn)=SIGN(@ActualReturn) THEN 1 ELSE 0 END;
END;
GO
CREATE OR ALTER FUNCTION dbo.fn_EligiblePredictions(@AsOfDate date)
RETURNS TABLE AS RETURN
 SELECT p.RunId,r.ModelId,r.DatasetId,r.TargetId,p.StockId,p.OriginDate,f.TargetDate,
 t.HorizonSessions,p.ProbabilityPositive,r.Threshold,
 CONVERT(bit,CASE WHEN z.ClosePrice>a.ClosePrice THEN 1 ELSE 0 END) AS ActualLabel,
 CONVERT(bit,CASE WHEN p.ProbabilityPositive>=r.Threshold THEN 1 ELSE 0 END) AS PredictedLabel,
 dbo.fn_CalculateReturn(a.ClosePrice,z.ClosePrice) AS ActualSourceCloseReturnPct
 FROM dbo.Prediction p JOIN dbo.ModelRun r ON r.RunId=p.RunId
 JOIN dbo.ForecastOrigin f ON f.RunId=p.RunId AND f.OriginDate=p.OriginDate
 JOIN dbo.TargetDefinition t ON t.TargetId=r.TargetId JOIN dbo.Dataset d ON d.DatasetId=r.DatasetId
 JOIN dbo.DailyPrice a ON a.DatasetId=r.DatasetId AND a.StockId=p.StockId AND a.TradeDate=p.OriginDate
 JOIN dbo.DailyPrice z ON z.DatasetId=r.DatasetId AND z.StockId=p.StockId AND z.TradeDate=f.TargetDate
 WHERE f.TargetDate<=@AsOfDate AND f.TargetDate<=d.ObservedThrough AND p.OriginDate>r.ValidationEnd;
GO
