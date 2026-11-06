-- 12. Kiem thu CHECK tren DEMO: Volume am bi tu choi, transaction duoc hoan tac
USE MarketLabVN30_Demo;
SELECT Volume AS VolumeTruoc FROM dbo.DailyPrice WHERE DatasetId = 1 AND StockId = 1 AND TradeDate = '2025-02-19';
BEGIN TRY
    BEGIN TRANSACTION;
    UPDATE dbo.DailyPrice SET Volume = -1
    WHERE DatasetId = 1 AND StockId = 1 AND TradeDate = '2025-02-19';
    ROLLBACK TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0 ROLLBACK TRANSACTION;
    SELECT ERROR_NUMBER() AS ErrorNumber,
           SUBSTRING(ERROR_MESSAGE(), CHARINDEX('CK_', ERROR_MESSAGE()), 20) AS ConstraintName,
           ERROR_MESSAGE() AS ErrorMessage;
END CATCH;
SELECT Volume AS VolumeSau, @@TRANCOUNT AS OpenTransactions FROM dbo.DailyPrice WHERE DatasetId = 1 AND StockId = 1 AND TradeDate = '2025-02-19';
