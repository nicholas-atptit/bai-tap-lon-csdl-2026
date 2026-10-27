USE [MarketLabVN30_Demo];
GO
-- Cross-table rules cannot be expressed using SQL Server CHECK alone.
CREATE OR ALTER TRIGGER dbo.tr_DailyPrice_Scope ON dbo.DailyPrice AFTER INSERT,UPDATE AS
BEGIN
 SET NOCOUNT ON;
 IF EXISTS(SELECT 1 FROM inserted i JOIN dbo.Stock s ON s.StockId=i.StockId JOIN dbo.Dataset d ON d.DatasetId=i.DatasetId
 WHERE s.MarketId<>d.MarketId OR s.IsSynthetic<>CASE WHEN d.DataKind='SYNTHETIC' THEN 1 ELSE 0 END OR i.TradeDate>d.ObservedThrough)
 THROW 51001,N'Gia khong cung thi truong/loai du lieu hoac vuot ngay quan sat.',1;
END;
GO
CREATE OR ALTER TRIGGER dbo.tr_Prediction_Eligibility ON dbo.Prediction AFTER INSERT,UPDATE AS
BEGIN
 SET NOCOUNT ON;
 IF EXISTS(SELECT 1 FROM inserted i JOIN dbo.ModelRun r ON r.RunId=i.RunId
 JOIN dbo.TargetDefinition t ON t.TargetId=r.TargetId JOIN dbo.Dataset d ON d.DatasetId=r.DatasetId JOIN dbo.Stock s ON s.StockId=i.StockId
 WHERE i.OriginDate<=r.ValidationEnd OR s.MarketId<>d.MarketId
 OR s.IsSynthetic<>CASE WHEN d.DataKind='SYNTHETIC' THEN 1 ELSE 0 END
 OR NOT EXISTS(SELECT 1 FROM dbo.TradingDay td WHERE td.DatasetId=r.DatasetId AND td.TradeDate=i.OriginDate)
 OR NOT EXISTS(SELECT 1 FROM dbo.TradingDay td WHERE td.DatasetId=r.DatasetId AND td.TradeDate=i.TargetDate)
 OR (SELECT COUNT(*) FROM dbo.TradingDay td WHERE td.DatasetId=r.DatasetId AND td.TradeDate>i.OriginDate AND td.TradeDate<=i.TargetDate)<>t.HorizonSessions)
 THROW 51002,N'Du bao sai lich phien, horizon, pham vi hoac khong ngoai mau.',1;
END;
GO
CREATE OR ALTER TRIGGER dbo.tr_IndexMembership_Overlap ON dbo.IndexMembership AFTER INSERT,UPDATE AS
BEGIN
 SET NOCOUNT ON;
 IF EXISTS(SELECT 1 FROM inserted i JOIN dbo.Stock s ON s.StockId=i.StockId JOIN dbo.StockIndex x ON x.IndexId=i.IndexId WHERE s.MarketId<>x.MarketId)
 THROW 51003,N'Thanh phan chi so sai thi truong.',1;
 -- Range locks prevent concurrent overlapping intervals.
 IF EXISTS(SELECT 1 FROM inserted i JOIN dbo.IndexMembership m WITH(UPDLOCK,HOLDLOCK)
 ON m.IndexId=i.IndexId AND m.StockId=i.StockId AND m.ValidFrom<>i.ValidFrom AND m.ValidFrom<=i.ValidTo AND m.ValidTo>=i.ValidFrom)
 THROW 51004,N'Khoang hieu luc thanh phan chi so bi chong lan.',1;
END;
GO
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.DailyPrice') AND name='IX_DailyPrice_Date')
 CREATE INDEX IX_DailyPrice_Date ON dbo.DailyPrice(DatasetId,TradeDate,StockId) INCLUDE(ClosePrice,Volume);
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.IndexMembership') AND name='IX_IndexMembership_Stock')
 CREATE INDEX IX_IndexMembership_Stock ON dbo.IndexMembership(StockId,ValidFrom) INCLUDE(IndexId,ValidTo);
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.ModelRun') AND name='IX_ModelRun_Model')
 CREATE INDEX IX_ModelRun_Model ON dbo.ModelRun(ModelId,DatasetId,TargetId);
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.Prediction') AND name='IX_Prediction_Date')
 CREATE INDEX IX_Prediction_Date ON dbo.Prediction(OriginDate,RunId,StockId) INCLUDE(TargetDate,ProbabilityPositive);
GO
