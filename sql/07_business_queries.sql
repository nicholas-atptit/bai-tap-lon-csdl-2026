USE [MarketLabVN30_Demo];
GO
SET NOCOUNT ON;
-- Q01 | SELECT: Danh muc co phieu va tinh trang metadata.
SELECT StockId,Ticker,CompanyName,IndustryId,IsSynthetic FROM dbo.Stock ORDER BY Ticker;
GO
-- Q02 | INNER JOIN: Gia gan nhat kem don vi va pham vi nguon.
SELECT s.Ticker,p.TradeDate,p.ClosePrice,d.PriceUnit FROM dbo.vw_LatestStockPrice p INNER JOIN dbo.Stock s ON s.StockId=p.StockId INNER JOIN dbo.Dataset d ON d.DatasetId=p.DatasetId ORDER BY s.Ticker;
GO
-- Q03 | LEFT JOIN: Co phieu chua co thong tin phan nganh.
SELECT s.Ticker,i.IndustryName FROM dbo.Stock s LEFT JOIN dbo.Industry i ON i.IndustryId=s.IndustryId WHERE i.IndustryId IS NULL ORDER BY s.Ticker;
GO
-- Q04 | FULL JOIN: Doi chieu pham vi co gia va pham vi co du bao.
WITH P AS(SELECT DISTINCT StockId FROM dbo.DailyPrice),F AS(SELECT DISTINCT StockId FROM dbo.Prediction)
SELECT COALESCE(P.StockId,F.StockId) AS StockId,CASE WHEN P.StockId IS NULL THEN 0 ELSE 1 END AS HasPrice,CASE WHEN F.StockId IS NULL THEN 0 ELSE 1 END AS HasForecast FROM P FULL JOIN F ON F.StockId=P.StockId ORDER BY StockId;
GO
-- Q05 | GROUP BY: Khoi luong trung binh theo nganh; UNKNOWN khong duoc xem la 0.
SELECT COALESCE(i.IndustryName,N'Chua co metadata nganh') AS IndustryName,COUNT_BIG(*) AS PriceRows,AVG(CONVERT(decimal(25,2),p.Volume)) AS AverageVolume
FROM dbo.DailyPrice p JOIN dbo.Stock s ON s.StockId=p.StockId LEFT JOIN dbo.Industry i ON i.IndustryId=s.IndustryId GROUP BY i.IndustryName;
GO
-- Q06 | HAVING: Ma co it nhat 20 phien gia trong dataset.
SELECT DatasetId,StockId,COUNT(*) AS ObservedSessions FROM dbo.DailyPrice GROUP BY DatasetId,StockId HAVING COUNT(*)>=20 ORDER BY DatasetId,StockId;
GO
-- Q07 | Subquery: Phien co khoi luong cao hon trung binh cung ma/dataset.
SELECT p.DatasetId,p.StockId,p.TradeDate,p.Volume FROM dbo.DailyPrice p WHERE p.Volume>(SELECT AVG(CONVERT(decimal(25,2),q.Volume)) FROM dbo.DailyPrice q WHERE q.DatasetId=p.DatasetId AND q.StockId=p.StockId) ORDER BY p.StockId,p.TradeDate;
GO
-- Q08 | UNION: Tap ma can quan ly tu gia hoac du bao (loai trung).
SELECT StockId FROM dbo.DailyPrice UNION SELECT StockId FROM dbo.Prediction;
GO
-- Q09 | INTERSECT: Co phieu duoc ca hai run dau tien du bao.
SELECT StockId FROM dbo.Prediction WHERE RunId=(SELECT MIN(RunId) FROM dbo.ModelRun)
INTERSECT SELECT StockId FROM dbo.Prediction WHERE RunId=(SELECT MAX(RunId) FROM dbo.ModelRun);
GO
-- Q10 | EXCEPT: Ma co gia nhung khong co du bao.
SELECT StockId FROM dbo.DailyPrice EXCEPT SELECT StockId FROM dbo.Prediction;
GO
-- Q11 | LIKE: Tim ma theo ky tu A trong danh muc.
SELECT StockId,Ticker FROM dbo.Stock WHERE Ticker LIKE '%A%' ORDER BY Ticker;
GO
-- Q12 | BETWEEN: Gia trong 7 ngay lich dau tien cua tap du lieu.
SELECT p.StockId,p.TradeDate,p.ClosePrice FROM dbo.DailyPrice p WHERE p.TradeDate BETWEEN (SELECT MIN(TradeDate) FROM dbo.DailyPrice) AND DATEADD(day,6,(SELECT MIN(TradeDate) FROM dbo.DailyPrice)) ORDER BY p.StockId,p.TradeDate;
GO
-- Q13 | TOP / function: 5 ma tang gia nguon manh nhat tu dau den cuoi tap.
WITH R AS(SELECT DatasetId,StockId,MIN(TradeDate) AS D0,MAX(TradeDate) AS D1 FROM dbo.DailyPrice GROUP BY DatasetId,StockId)
SELECT TOP(5) s.Ticker,dbo.fn_CalculateReturn(a.ClosePrice,z.ClosePrice) AS SourceCloseReturnPct
FROM R JOIN dbo.Stock s ON s.StockId=R.StockId JOIN dbo.DailyPrice a ON a.DatasetId=R.DatasetId AND a.StockId=R.StockId AND a.TradeDate=R.D0
JOIN dbo.DailyPrice z ON z.DatasetId=R.DatasetId AND z.StockId=R.StockId AND z.TradeDate=R.D1 ORDER BY SourceCloseReturnPct DESC,s.Ticker;
GO
-- Q14 | Ham huong: Minh hoa du bao huong loi suat 3 trang thai; khong thay the Brier.
SELECT dbo.fn_CheckPredictionDirection(1.0,2.0) AS PositiveMatch,dbo.fn_CheckPredictionDirection(0,0) AS FlatMatch,dbo.fn_CheckPredictionDirection(0,1) AS FlatMismatch;
GO
-- Q15 | View: Ket qua phan loai theo run va horizon, chi du lieu da truong thanh.
SELECT r.RunCode,m.ModelCode,p.* FROM dbo.vw_ModelPerformance p JOIN dbo.ModelRun r ON r.RunId=p.RunId JOIN dbo.ForecastModel m ON m.ModelId=p.ModelId ORDER BY p.RunId;
GO
-- Q16 | LEFT JOIN: Kiem tra thieu gia tren lich dataset trong pham vi da quan sat.
SELECT u.DatasetId,u.StockId,t.TradeDate FROM dbo.vw_StudyUniverse u JOIN dbo.TradingDay t ON t.DatasetId=u.DatasetId
JOIN dbo.Dataset d ON d.DatasetId=t.DatasetId LEFT JOIN dbo.DailyPrice p ON p.DatasetId=u.DatasetId AND p.StockId=u.StockId AND p.TradeDate=t.TradeDate
WHERE t.TradeDate BETWEEN u.FirstObservedDate AND d.ObservedThrough AND p.StockId IS NULL ORDER BY u.StockId,t.TradeDate;
GO
