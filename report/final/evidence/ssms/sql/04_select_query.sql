-- Q01 | SELECT: Danh muc co phieu va tinh trang metadata
USE MarketLabVN30_Demo;
SELECT StockId, Ticker, CompanyName, IndustryId, IsSynthetic
FROM dbo.Stock
ORDER BY Ticker;
