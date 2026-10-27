USE [MarketLabVN30_Demo];
GO
CREATE OR ALTER TRIGGER dbo.tr_ModelRun_Guard ON dbo.ModelRun AFTER INSERT,UPDATE AS
BEGIN
 SET NOCOUNT ON;
 IF EXISTS(SELECT 1 FROM inserted i JOIN dbo.Dataset d ON d.DatasetId=i.DatasetId
 WHERE (d.DataKind='SYNTHETIC' AND i.EvaluationClass<>'SYNTHETIC_TEST') OR (d.DataKind='REAL_PRIVATE' AND i.EvaluationClass<>'RETROSPECTIVE_OOS'))
 THROW 51005,N'Loai model run khong khop dataset.',1;
 IF EXISTS(SELECT 1 FROM inserted i JOIN deleted o ON o.RunId=i.RunId WHERE EXISTS(SELECT 1 FROM dbo.ForecastOrigin p WHERE p.RunId=i.RunId)
 AND EXISTS(SELECT i.RunCode,i.ModelId,i.DatasetId,i.TargetId,i.TrainStart,i.TrainEnd,i.ValidationEnd,i.SelectedC,i.Threshold,i.EvaluationClass,i.SourceRun,i.CompletedAt
 EXCEPT SELECT o.RunCode,o.ModelId,o.DatasetId,o.TargetId,o.TrainStart,o.TrainEnd,o.ValidationEnd,o.SelectedC,o.Threshold,o.EvaluationClass,o.SourceRun,o.CompletedAt))
 THROW 51006,N'Run da co du bao la bat bien; tao run moi.',1;
END;
GO
CREATE OR ALTER TRIGGER dbo.tr_Dataset_Guard ON dbo.Dataset AFTER UPDATE AS
BEGIN
 SET NOCOUNT ON;
 IF EXISTS(SELECT 1 FROM inserted i JOIN deleted o ON o.DatasetId=i.DatasetId
 WHERE (EXISTS(SELECT 1 FROM dbo.DailyPrice p WHERE p.DatasetId=i.DatasetId) OR EXISTS(SELECT 1 FROM dbo.ModelRun r WHERE r.DatasetId=i.DatasetId))
 AND EXISTS(SELECT i.MarketId,i.DataKind,i.PriceBasis,i.PriceUnit,i.ObservedThrough EXCEPT SELECT o.MarketId,o.DataKind,o.PriceBasis,o.PriceUnit,o.ObservedThrough))
 THROW 51007,N'Ngu nghia dataset da su dung la bat bien; tao dataset moi.',1;
END;
GO
CREATE OR ALTER TRIGGER dbo.tr_Stock_Guard ON dbo.Stock AFTER UPDATE AS
BEGIN
 SET NOCOUNT ON;
 IF EXISTS(SELECT 1 FROM inserted i JOIN deleted o ON o.StockId=i.StockId WHERE (i.MarketId<>o.MarketId OR i.IsSynthetic<>o.IsSynthetic)
 AND (EXISTS(SELECT 1 FROM dbo.DailyPrice p WHERE p.StockId=i.StockId) OR EXISTS(SELECT 1 FROM dbo.Prediction p WHERE p.StockId=i.StockId) OR EXISTS(SELECT 1 FROM dbo.IndexMembership m WHERE m.StockId=i.StockId)))
 THROW 51008,N'Khong doi thi truong/loai ma da su dung.',1;
END;
GO
CREATE OR ALTER TRIGGER dbo.tr_TargetDefinition_Guard ON dbo.TargetDefinition AFTER UPDATE AS
BEGIN
 SET NOCOUNT ON;
 IF EXISTS(SELECT 1 FROM inserted i JOIN deleted o ON o.TargetId=i.TargetId WHERE EXISTS(SELECT 1 FROM dbo.ModelRun r WHERE r.TargetId=i.TargetId)
 AND EXISTS(SELECT i.TargetCode,i.HorizonSessions,i.OutputType,i.LabelRule EXCEPT SELECT o.TargetCode,o.HorizonSessions,o.OutputType,o.LabelRule))
 THROW 51009,N'Dinh nghia muc tieu da su dung la bat bien.',1;
END;
GO
CREATE OR ALTER TRIGGER dbo.tr_TradingDay_Guard ON dbo.TradingDay AFTER INSERT,UPDATE,DELETE AS
BEGIN
 SET NOCOUNT ON;
 IF EXISTS(SELECT 1 FROM dbo.ForecastOrigin p JOIN dbo.ModelRun r ON r.RunId=p.RunId JOIN dbo.TargetDefinition t ON t.TargetId=r.TargetId
 WHERE r.DatasetId IN(SELECT DatasetId FROM inserted UNION SELECT DatasetId FROM deleted)
 AND (NOT EXISTS(SELECT 1 FROM dbo.TradingDay td WHERE td.DatasetId=r.DatasetId AND td.TradeDate=p.OriginDate)
 OR NOT EXISTS(SELECT 1 FROM dbo.TradingDay td WHERE td.DatasetId=r.DatasetId AND td.TradeDate=p.TargetDate)
 OR (SELECT COUNT(*) FROM dbo.TradingDay td WHERE td.DatasetId=r.DatasetId AND td.TradeDate>p.OriginDate AND td.TradeDate<=p.TargetDate)<>t.HorizonSessions))
 THROW 51022,N'Thay doi lich lam sai horizon cua du bao da luu.',1;
END;
GO
CREATE OR ALTER TRIGGER dbo.tr_StockIndex_Guard ON dbo.StockIndex AFTER UPDATE AS
BEGIN
 SET NOCOUNT ON;
 IF EXISTS(SELECT 1 FROM inserted i JOIN dbo.IndexMembership m ON m.IndexId=i.IndexId JOIN dbo.Stock s ON s.StockId=m.StockId WHERE s.MarketId<>i.MarketId)
 THROW 51003,N'Chi so khong cung thi truong voi thanh phan.',1;
END;
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
CREATE OR ALTER TRIGGER dbo.tr_ForecastOrigin_Eligibility ON dbo.ForecastOrigin AFTER INSERT,UPDATE AS
BEGIN
 SET NOCOUNT ON;
 IF EXISTS(SELECT 1 FROM inserted i JOIN dbo.ModelRun r ON r.RunId=i.RunId
 JOIN dbo.TargetDefinition t ON t.TargetId=r.TargetId JOIN dbo.Dataset d ON d.DatasetId=r.DatasetId
 WHERE i.OriginDate<=r.ValidationEnd
 OR NOT EXISTS(SELECT 1 FROM dbo.TradingDay td WHERE td.DatasetId=r.DatasetId AND td.TradeDate=i.OriginDate)
 OR NOT EXISTS(SELECT 1 FROM dbo.TradingDay td WHERE td.DatasetId=r.DatasetId AND td.TradeDate=i.TargetDate)
 OR (SELECT COUNT(*) FROM dbo.TradingDay td WHERE td.DatasetId=r.DatasetId AND td.TradeDate>i.OriginDate AND td.TradeDate<=i.TargetDate)<>t.HorizonSessions)
 THROW 51002,N'Du bao sai lich phien, horizon, pham vi hoac khong ngoai mau.',1;
END;
GO
CREATE OR ALTER TRIGGER dbo.tr_Prediction_Eligibility ON dbo.Prediction AFTER INSERT,UPDATE AS
BEGIN
 SET NOCOUNT ON;
 IF EXISTS(SELECT 1 FROM inserted i JOIN dbo.ModelRun r ON r.RunId=i.RunId JOIN dbo.Dataset d ON d.DatasetId=r.DatasetId JOIN dbo.Stock s ON s.StockId=i.StockId
 WHERE s.MarketId<>d.MarketId OR s.IsSynthetic<>CASE WHEN d.DataKind='SYNTHETIC' THEN 1 ELSE 0 END)
 THROW 51002,N'Du bao sai thi truong hoac loai du lieu.',1;
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
 CREATE INDEX IX_Prediction_Date ON dbo.Prediction(OriginDate,RunId,StockId) INCLUDE(ProbabilityPositive);
GO
