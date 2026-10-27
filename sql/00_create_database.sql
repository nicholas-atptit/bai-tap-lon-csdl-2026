-- MarketLab VN30. SQL Server 2016 SP1+ / Express. No DROP, no reset.
USE master;
GO
SET NOCOUNT ON;
IF DB_ID(N'MarketLabVN30_Demo') IS NULL
    EXEC(N'CREATE DATABASE [MarketLabVN30_Demo]');
GO
USE [MarketLabVN30_Demo];
GO
-- Refuse to adopt an unrelated populated database, including in SSMS.
IF EXISTS(SELECT 1 FROM sys.tables WHERE is_ms_shipped=0)
   AND NOT EXISTS(SELECT 1 FROM sys.extended_properties WHERE class=0 AND name=N'MarketLabSchema' AND CONVERT(nvarchar(50),value)=N'1.0')
BEGIN
    RAISERROR(N'Database co san khong thuoc MarketLab 1.0. Dung trien khai.',16,1);
    SET NOEXEC ON;
END;
GO
IF NOT EXISTS(SELECT 1 FROM sys.extended_properties WHERE class=0 AND name=N'MarketLabSchema')
    EXEC sys.sp_addextendedproperty @name=N'MarketLabSchema',@value=N'1.0';
GO
