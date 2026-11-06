USE MarketLabVN30_Demo;
-- Q02 | INNER JOIN: Gia gan nhat kem don vi va pham vi nguon
SELECT s.Ticker, p.TradeDate, p.ClosePrice, d.PriceUnit
FROM dbo.vw_LatestStockPrice p
INNER JOIN dbo.Stock s ON s.StockId = p.StockId
INNER JOIN dbo.Dataset d ON d.DatasetId = p.DatasetId
ORDER BY s.Ticker;
-- Q03 | LEFT JOIN: Co phieu chua co thong tin phan nganh
SELECT s.Ticker, i.IndustryName
FROM dbo.Stock s
LEFT JOIN dbo.Industry i ON i.IndustryId = s.IndustryId
WHERE i.IndustryId IS NULL
ORDER BY s.Ticker;
