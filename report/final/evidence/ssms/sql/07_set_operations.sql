USE MarketLabVN30_Demo;
-- Q08 | UNION: Tap ma tu gia hoac du bao (loai trung)
SELECT StockId FROM dbo.DailyPrice UNION SELECT StockId FROM dbo.Prediction;
-- Q09 | INTERSECT: Co phieu duoc ca hai run du bao
SELECT StockId FROM dbo.Prediction WHERE RunId = (SELECT MIN(RunId) FROM dbo.ModelRun)
INTERSECT
SELECT StockId FROM dbo.Prediction WHERE RunId = (SELECT MAX(RunId) FROM dbo.ModelRun);
-- Q10 | EXCEPT: Ma co gia nhung khong co du bao (0 dong la hop le)
SELECT StockId FROM dbo.DailyPrice EXCEPT SELECT StockId FROM dbo.Prediction;
