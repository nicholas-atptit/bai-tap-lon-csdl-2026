USE MarketLabVN30_Demo;
-- 3 Function: 2 scalar + 1 inline table-valued
SELECT name AS FunctionName, type_desc FROM sys.objects WHERE type IN ('FN','IF','TF') ORDER BY name;
-- Scalar function
SELECT dbo.fn_CalculateReturn(100, 110) AS ReturnPct;
-- Table-valued function: du bao du dieu kien danh gia tai AsOfDate
SELECT TOP (10) RunId, StockId, OriginDate, TargetDate, ProbabilityPositive, ActualLabel, PredictedLabel
FROM dbo.fn_EligiblePredictions('2026-07-01')
ORDER BY RunId, OriginDate, StockId;
