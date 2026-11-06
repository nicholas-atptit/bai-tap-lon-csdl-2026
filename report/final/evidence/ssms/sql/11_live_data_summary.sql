-- 11. Du lieu that MarketLabVN30_Live (chi doc, chi so lieu tong hop - khong hien thi gia)
USE MarketLabVN30_Live;
SELECT COUNT_BIG(*) AS OhlcvRows, COUNT(DISTINCT StockId) AS Tickers, COUNT(DISTINCT TradeDate) AS Sessions,
       MIN(TradeDate) AS FirstDate, MAX(TradeDate) AS LastDate
FROM dbo.DailyPrice;
SELECT YEAR(TradeDate) AS [Year], COUNT(DISTINCT TradeDate) AS Sessions, COUNT_BIG(*) AS OhlcvRows
FROM dbo.DailyPrice GROUP BY YEAR(TradeDate) ORDER BY [Year];
SELECT s.Ticker, COUNT(*) AS Sessions, MIN(p.TradeDate) AS FirstDate, MAX(p.TradeDate) AS LastDate
FROM dbo.DailyPrice p JOIN dbo.Stock s ON s.StockId = p.StockId
GROUP BY s.Ticker HAVING COUNT(*) < (SELECT COUNT(*) FROM dbo.TradingDay);
