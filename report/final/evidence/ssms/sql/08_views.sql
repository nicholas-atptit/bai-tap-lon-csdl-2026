USE MarketLabVN30_Demo;
-- 4 View cua he thong
SELECT name AS ViewName, create_date FROM sys.views ORDER BY name;
-- View tieu bieu: hieu nang mo hinh tren du bao da du dieu kien
SELECT RunId, EvaluatedRows, Accuracy, BrierScore, NaturalLogLoss
FROM dbo.vw_ModelPerformance
ORDER BY RunId;
