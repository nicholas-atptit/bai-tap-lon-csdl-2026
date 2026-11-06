USE MarketLabVN30_Demo;
-- Q05 | GROUP BY: Khoi luong trung binh theo nganh
SELECT COALESCE(i.IndustryName, N'Chua co metadata nganh') AS IndustryName,
       COUNT_BIG(*) AS PriceRows, AVG(CONVERT(decimal(25,2), p.Volume)) AS AverageVolume
FROM dbo.DailyPrice p JOIN dbo.Stock s ON s.StockId = p.StockId
LEFT JOIN dbo.Industry i ON i.IndustryId = s.IndustryId
GROUP BY i.IndustryName;
-- Q06 | HAVING: Ma co it nhat 20 phien gia trong dataset
SELECT DatasetId, StockId, COUNT(*) AS ObservedSessions
FROM dbo.DailyPrice GROUP BY DatasetId, StockId
HAVING COUNT(*) >= 20 ORDER BY DatasetId, StockId;
-- Q07 | Subquery: Phien co khoi luong cao hon trung binh cung ma/dataset
SELECT p.DatasetId, p.StockId, p.TradeDate, p.Volume FROM dbo.DailyPrice p
WHERE p.Volume > (SELECT AVG(CONVERT(decimal(25,2), q.Volume)) FROM dbo.DailyPrice q
                  WHERE q.DatasetId = p.DatasetId AND q.StockId = p.StockId)
ORDER BY p.StockId, p.TradeDate;
