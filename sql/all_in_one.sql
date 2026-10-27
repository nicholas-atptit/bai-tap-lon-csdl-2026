-- FILE: 00_create_database.sql
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

-- FILE: 01_create_tables.sql
USE [MarketLabVN30_Demo];
GO
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO
IF OBJECT_ID(N'dbo.Market',N'U') IS NULL
CREATE TABLE dbo.Market(
 MarketId int NOT NULL CONSTRAINT PK_Market PRIMARY KEY,
 MarketCode varchar(12) NOT NULL CONSTRAINT UQ_Market_Code UNIQUE,
 MarketName nvarchar(120) NOT NULL,
 CurrencyCode char(3) NOT NULL
);
IF OBJECT_ID(N'dbo.Industry',N'U') IS NULL
CREATE TABLE dbo.Industry(
 IndustryId int NOT NULL CONSTRAINT PK_Industry PRIMARY KEY,
 IndustryCode varchar(30) NOT NULL CONSTRAINT UQ_Industry_Code UNIQUE,
 IndustryName nvarchar(120) NOT NULL,
 EvidenceNote nvarchar(400) NOT NULL
);
IF OBJECT_ID(N'dbo.Stock',N'U') IS NULL
CREATE TABLE dbo.Stock(
 StockId int NOT NULL CONSTRAINT PK_Stock PRIMARY KEY,
 MarketId int NOT NULL CONSTRAINT FK_Stock_Market REFERENCES dbo.Market(MarketId),
 Ticker varchar(20) NOT NULL,
 CompanyName nvarchar(200) NULL,
 IndustryId int NULL CONSTRAINT FK_Stock_Industry REFERENCES dbo.Industry(IndustryId),
 IsSynthetic bit NOT NULL CONSTRAINT DF_Stock_Synthetic DEFAULT(0),
 CONSTRAINT UQ_Stock_MarketTicker UNIQUE(MarketId,Ticker)
);
IF OBJECT_ID(N'dbo.Dataset',N'U') IS NULL
CREATE TABLE dbo.Dataset(
 DatasetId int NOT NULL CONSTRAINT PK_Dataset PRIMARY KEY,
 DatasetCode varchar(80) NOT NULL CONSTRAINT UQ_Dataset_Code UNIQUE,
 MarketId int NOT NULL CONSTRAINT FK_Dataset_Market REFERENCES dbo.Market(MarketId),
 DataKind varchar(20) NOT NULL CONSTRAINT CK_Dataset_Kind CHECK(DataKind IN ('SYNTHETIC','REAL_PRIVATE')),
 PriceBasis varchar(40) NOT NULL CONSTRAINT CK_Dataset_Basis CHECK(PriceBasis='SOURCE_CLOSE'),
 PriceUnit nvarchar(100) NOT NULL,
 ObservedThrough date NOT NULL,
 ManifestPath nvarchar(400) NOT NULL,
 ProvenanceNote nvarchar(1000) NOT NULL
);
IF OBJECT_ID(N'dbo.TradingDay',N'U') IS NULL
CREATE TABLE dbo.TradingDay(
 DatasetId int NOT NULL CONSTRAINT FK_TradingDay_Dataset REFERENCES dbo.Dataset(DatasetId),
 TradeDate date NOT NULL,
 CONSTRAINT PK_TradingDay PRIMARY KEY(DatasetId,TradeDate)
);
IF OBJECT_ID(N'dbo.DailyPrice',N'U') IS NULL
CREATE TABLE dbo.DailyPrice(
 DatasetId int NOT NULL,
 StockId int NOT NULL CONSTRAINT FK_DailyPrice_Stock REFERENCES dbo.Stock(StockId),
 TradeDate date NOT NULL,
 OpenPrice decimal(19,6) NOT NULL,
 HighPrice decimal(19,6) NOT NULL,
 LowPrice decimal(19,6) NOT NULL,
 ClosePrice decimal(19,6) NOT NULL,
 Volume bigint NOT NULL,
 LoadedAt datetime2(0) NOT NULL CONSTRAINT DF_DailyPrice_LoadedAt DEFAULT(SYSUTCDATETIME()),
 CONSTRAINT PK_DailyPrice PRIMARY KEY(DatasetId,StockId,TradeDate),
 CONSTRAINT FK_DailyPrice_TradingDay FOREIGN KEY(DatasetId,TradeDate) REFERENCES dbo.TradingDay(DatasetId,TradeDate),
 CONSTRAINT CK_DailyPrice_Positive CHECK(OpenPrice>0 AND HighPrice>0 AND LowPrice>0 AND ClosePrice>0),
 CONSTRAINT CK_DailyPrice_OHLC CHECK(HighPrice>=OpenPrice AND HighPrice>=ClosePrice AND HighPrice>=LowPrice AND LowPrice<=OpenPrice AND LowPrice<=ClosePrice),
 CONSTRAINT CK_DailyPrice_Volume CHECK(Volume>=0)
);
IF OBJECT_ID(N'dbo.StockIndex',N'U') IS NULL
CREATE TABLE dbo.StockIndex(
 IndexId int NOT NULL CONSTRAINT PK_StockIndex PRIMARY KEY,
 MarketId int NOT NULL CONSTRAINT FK_StockIndex_Market REFERENCES dbo.Market(MarketId),
 IndexCode varchar(20) NOT NULL,
 IndexName nvarchar(150) NOT NULL,
 CONSTRAINT UQ_StockIndex_Code UNIQUE(MarketId,IndexCode)
);
IF OBJECT_ID(N'dbo.IndexMembership',N'U') IS NULL
CREATE TABLE dbo.IndexMembership(
 IndexId int NOT NULL CONSTRAINT FK_IndexMembership_Index REFERENCES dbo.StockIndex(IndexId),
 StockId int NOT NULL CONSTRAINT FK_IndexMembership_Stock REFERENCES dbo.Stock(StockId),
 ValidFrom date NOT NULL,
 ValidTo date NOT NULL,
 EvidenceNote nvarchar(500) NOT NULL,
 CONSTRAINT PK_IndexMembership PRIMARY KEY(IndexId,StockId,ValidFrom),
 CONSTRAINT CK_IndexMembership_Dates CHECK(ValidTo>=ValidFrom)
);
IF OBJECT_ID(N'dbo.ForecastModel',N'U') IS NULL
CREATE TABLE dbo.ForecastModel(
 ModelId int NOT NULL CONSTRAINT PK_ForecastModel PRIMARY KEY,
 ModelCode varchar(70) NOT NULL CONSTRAINT UQ_ForecastModel_Code UNIQUE,
 ModelName nvarchar(160) NOT NULL,
 MethodNote nvarchar(500) NOT NULL
);
IF OBJECT_ID(N'dbo.TargetDefinition',N'U') IS NULL
CREATE TABLE dbo.TargetDefinition(
 TargetId int NOT NULL CONSTRAINT PK_TargetDefinition PRIMARY KEY,
 TargetCode varchar(50) NOT NULL CONSTRAINT UQ_TargetDefinition_Code UNIQUE,
 HorizonSessions int NOT NULL CONSTRAINT CK_Target_Horizon CHECK(HorizonSessions>0),
 OutputType varchar(40) NOT NULL CONSTRAINT CK_Target_Output CHECK(OutputType='PROBABILITY_CLOSE_UP'),
 LabelRule varchar(80) NOT NULL CONSTRAINT CK_Target_Rule CHECK(LabelRule='CLOSE_TARGET_GT_CLOSE_ORIGIN_ELSE_ZERO'),
 CONSTRAINT UQ_Target_Definition UNIQUE(HorizonSessions,OutputType,LabelRule)
);
IF OBJECT_ID(N'dbo.ModelRun',N'U') IS NULL
CREATE TABLE dbo.ModelRun(
 RunId int NOT NULL CONSTRAINT PK_ModelRun PRIMARY KEY,
 RunCode varchar(100) NOT NULL CONSTRAINT UQ_ModelRun_Code UNIQUE,
 ModelId int NOT NULL CONSTRAINT FK_ModelRun_Model REFERENCES dbo.ForecastModel(ModelId),
 DatasetId int NOT NULL CONSTRAINT FK_ModelRun_Dataset REFERENCES dbo.Dataset(DatasetId),
 TargetId int NOT NULL CONSTRAINT FK_ModelRun_Target REFERENCES dbo.TargetDefinition(TargetId),
 TrainStart date NOT NULL,
 TrainEnd date NOT NULL,
 ValidationEnd date NOT NULL,
 SelectedC decimal(12,6) NULL,
 Threshold decimal(9,8) NOT NULL CONSTRAINT DF_ModelRun_Threshold DEFAULT(0.5),
 EvaluationClass varchar(40) NOT NULL CONSTRAINT CK_ModelRun_Class CHECK(EvaluationClass IN ('SYNTHETIC_TEST','RETROSPECTIVE_OOS')),
 SourceRun nvarchar(200) NOT NULL,
 CompletedAt datetime2(0) NULL,
 CONSTRAINT CK_ModelRun_Dates CHECK(TrainStart<=TrainEnd AND TrainEnd<ValidationEnd),
 CONSTRAINT CK_ModelRun_Threshold CHECK(Threshold>0 AND Threshold<1),
 CONSTRAINT CK_ModelRun_C CHECK(SelectedC IS NULL OR SelectedC>0)
);
-- Refuse ambiguous legacy data before creating even an empty new table.
-- Dynamic SQL avoids binding the legacy-only TargetDate column in fresh/current schemas.
IF COL_LENGTH(N'dbo.Prediction',N'TargetDate') IS NOT NULL
 EXEC(N'IF EXISTS(SELECT RunId,OriginDate FROM dbo.Prediction GROUP BY RunId,OriginDate HAVING COUNT(DISTINCT TargetDate)>1)
 THROW 51200,''Ambiguous target date; migration refused before schema changes'',1;');
IF OBJECT_ID(N'dbo.ForecastOrigin',N'U') IS NULL
CREATE TABLE dbo.ForecastOrigin(
 RunId int NOT NULL CONSTRAINT FK_ForecastOrigin_Run REFERENCES dbo.ModelRun(RunId),
 OriginDate date NOT NULL,
 TargetDate date NOT NULL,
 CONSTRAINT PK_ForecastOrigin PRIMARY KEY(RunId,OriginDate),
 CONSTRAINT CK_ForecastOrigin_Dates CHECK(TargetDate>OriginDate)
);
IF OBJECT_ID(N'dbo.Prediction',N'U') IS NULL
CREATE TABLE dbo.Prediction(
 RunId int NOT NULL CONSTRAINT FK_Prediction_Run REFERENCES dbo.ModelRun(RunId),
 StockId int NOT NULL CONSTRAINT FK_Prediction_Stock REFERENCES dbo.Stock(StockId),
 OriginDate date NOT NULL,
 ProbabilityPositive decimal(19,16) NOT NULL,
 LoadedAt datetime2(0) NOT NULL CONSTRAINT DF_Prediction_LoadedAt DEFAULT(SYSUTCDATETIME()),
 CONSTRAINT PK_Prediction PRIMARY KEY(RunId,StockId,OriginDate),
 CONSTRAINT FK_Prediction_ForecastOrigin FOREIGN KEY(RunId,OriginDate) REFERENCES dbo.ForecastOrigin(RunId,OriginDate),
 CONSTRAINT CK_Prediction_Probability CHECK(ProbabilityPositive BETWEEN 0 AND 1)
);
GO
-- Lossless migration for databases created by the initial build in this task.
-- All target dates are copied and verified before removing the redundant field.
IF COL_LENGTH('dbo.Prediction','TargetDate') IS NOT NULL
BEGIN
 EXEC(N'SET XACT_ABORT ON; BEGIN TRY BEGIN TRANSACTION;
 IF EXISTS(SELECT RunId,OriginDate FROM dbo.Prediction GROUP BY RunId,OriginDate HAVING COUNT(DISTINCT TargetDate)>1)
 THROW 51200,''Ambiguous target date; migration refused'',1;
 INSERT dbo.ForecastOrigin(RunId,OriginDate,TargetDate)
 SELECT DISTINCT p.RunId,p.OriginDate,p.TargetDate FROM dbo.Prediction p WHERE NOT EXISTS(SELECT 1 FROM dbo.ForecastOrigin f WHERE f.RunId=p.RunId AND f.OriginDate=p.OriginDate);
 IF EXISTS(SELECT RunId,OriginDate,TargetDate FROM dbo.Prediction EXCEPT SELECT RunId,OriginDate,TargetDate FROM dbo.ForecastOrigin)
 THROW 51201,''Target-date copy incomplete; migration refused'',1;
 IF EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(''dbo.Prediction'') AND name=''IX_Prediction_Date'') DROP INDEX IX_Prediction_Date ON dbo.Prediction;
 ALTER TABLE dbo.Prediction DROP CONSTRAINT CK_Prediction_Dates;
 ALTER TABLE dbo.Prediction DROP COLUMN TargetDate;
 ALTER TABLE dbo.Prediction ADD CONSTRAINT FK_Prediction_ForecastOrigin FOREIGN KEY(RunId,OriginDate) REFERENCES dbo.ForecastOrigin(RunId,OriginDate);
 COMMIT; END TRY BEGIN CATCH IF XACT_STATE()<>0 ROLLBACK; THROW; END CATCH;');
END;
GO

-- FILE: 02_constraints_indexes.sql
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

-- FILE: 03_insert_sample_data.sql
-- SYNTHETIC DATA ONLY. No actual VN30 prices or forecasts.
USE [MarketLabVN30_Demo];
GO
SET NOCOUNT ON; SET XACT_ABORT ON;
BEGIN TRY
 BEGIN TRANSACTION;
 CREATE TABLE #ImportReceipt(TableName sysname,RowsInput int,RowsInserted int);
 DECLARE @Added int;
 SET @Added=0;
 IF EXISTS(SELECT 1 FROM dbo.[Market] d JOIN (VALUES
(1,N'DEMO',N'Thị trường mô phỏng',N'VND')
) v([MarketId],[MarketCode],[MarketName],[CurrencyCode]) ON d.[MarketId]=v.[MarketId] WHERE EXISTS(SELECT d.[MarketId],d.[MarketCode],d.[MarketName],d.[CurrencyCode] EXCEPT SELECT v.[MarketId],v.[MarketCode],v.[MarketName],v.[CurrencyCode])) THROW 51100,N'Import conflict: Market',1;
 INSERT dbo.[Market]([MarketId],[MarketCode],[MarketName],[CurrencyCode]) SELECT v.[MarketId],v.[MarketCode],v.[MarketName],v.[CurrencyCode] FROM (VALUES
(1,N'DEMO',N'Thị trường mô phỏng',N'VND')
) v([MarketId],[MarketCode],[MarketName],[CurrencyCode]) WHERE NOT EXISTS(SELECT 1 FROM dbo.[Market] d WITH(UPDLOCK,HOLDLOCK) WHERE d.[MarketId]=v.[MarketId]);
 SET @Added=@Added+@@ROWCOUNT;
 INSERT #ImportReceipt VALUES(N'Market',1,@Added);
 SET @Added=0;
 IF EXISTS(SELECT 1 FROM dbo.[Industry] d JOIN (VALUES
(1,N'DEMO_SECTOR_1',N'Ngành mô phỏng 1',N'Dữ liệu danh mục mô phỏng, không ánh xạ ngành thực.'),
(2,N'DEMO_SECTOR_2',N'Ngành mô phỏng 2',N'Dữ liệu danh mục mô phỏng, không ánh xạ ngành thực.')
) v([IndustryId],[IndustryCode],[IndustryName],[EvidenceNote]) ON d.[IndustryId]=v.[IndustryId] WHERE EXISTS(SELECT d.[IndustryId],d.[IndustryCode],d.[IndustryName],d.[EvidenceNote] EXCEPT SELECT v.[IndustryId],v.[IndustryCode],v.[IndustryName],v.[EvidenceNote])) THROW 51100,N'Import conflict: Industry',1;
 INSERT dbo.[Industry]([IndustryId],[IndustryCode],[IndustryName],[EvidenceNote]) SELECT v.[IndustryId],v.[IndustryCode],v.[IndustryName],v.[EvidenceNote] FROM (VALUES
(1,N'DEMO_SECTOR_1',N'Ngành mô phỏng 1',N'Dữ liệu danh mục mô phỏng, không ánh xạ ngành thực.'),
(2,N'DEMO_SECTOR_2',N'Ngành mô phỏng 2',N'Dữ liệu danh mục mô phỏng, không ánh xạ ngành thực.')
) v([IndustryId],[IndustryCode],[IndustryName],[EvidenceNote]) WHERE NOT EXISTS(SELECT 1 FROM dbo.[Industry] d WITH(UPDLOCK,HOLDLOCK) WHERE d.[IndustryId]=v.[IndustryId]);
 SET @Added=@Added+@@ROWCOUNT;
 INSERT #ImportReceipt VALUES(N'Industry',2,@Added);
 SET @Added=0;
 IF EXISTS(SELECT 1 FROM dbo.[Stock] d JOIN (VALUES
(1,1,N'DEMO01',N'Công ty mô phỏng 1',1,1),
(2,1,N'DEMO02',N'Công ty mô phỏng 2',1,1),
(3,1,N'DEMO03',N'Công ty mô phỏng 3',1,1),
(4,1,N'DEMO04',N'Công ty mô phỏng 4',1,1),
(5,1,N'DEMO05',N'Công ty mô phỏng 5',2,1),
(6,1,N'DEMO06',N'Công ty mô phỏng 6',2,1),
(7,1,N'DEMO07',N'Công ty mô phỏng 7',2,1),
(8,1,N'DEMO08',N'Công ty mô phỏng 8',2,1)
) v([StockId],[MarketId],[Ticker],[CompanyName],[IndustryId],[IsSynthetic]) ON d.[StockId]=v.[StockId] WHERE EXISTS(SELECT d.[StockId],d.[MarketId],d.[Ticker],d.[CompanyName],d.[IndustryId],d.[IsSynthetic] EXCEPT SELECT v.[StockId],v.[MarketId],v.[Ticker],v.[CompanyName],v.[IndustryId],v.[IsSynthetic])) THROW 51100,N'Import conflict: Stock',1;
 INSERT dbo.[Stock]([StockId],[MarketId],[Ticker],[CompanyName],[IndustryId],[IsSynthetic]) SELECT v.[StockId],v.[MarketId],v.[Ticker],v.[CompanyName],v.[IndustryId],v.[IsSynthetic] FROM (VALUES
(1,1,N'DEMO01',N'Công ty mô phỏng 1',1,1),
(2,1,N'DEMO02',N'Công ty mô phỏng 2',1,1),
(3,1,N'DEMO03',N'Công ty mô phỏng 3',1,1),
(4,1,N'DEMO04',N'Công ty mô phỏng 4',1,1),
(5,1,N'DEMO05',N'Công ty mô phỏng 5',2,1),
(6,1,N'DEMO06',N'Công ty mô phỏng 6',2,1),
(7,1,N'DEMO07',N'Công ty mô phỏng 7',2,1),
(8,1,N'DEMO08',N'Công ty mô phỏng 8',2,1)
) v([StockId],[MarketId],[Ticker],[CompanyName],[IndustryId],[IsSynthetic]) WHERE NOT EXISTS(SELECT 1 FROM dbo.[Stock] d WITH(UPDLOCK,HOLDLOCK) WHERE d.[StockId]=v.[StockId]);
 SET @Added=@Added+@@ROWCOUNT;
 INSERT #ImportReceipt VALUES(N'Stock',8,@Added);
 SET @Added=0;
 IF EXISTS(SELECT 1 FROM dbo.[Dataset] d JOIN (VALUES
(1,N'SYNTHETIC_DEMO_V1',1,N'SYNTHETIC',N'SOURCE_CLOSE',N'Đơn vị mô phỏng',N'2025-02-19',N'data/sample/tables.json',N'DỮ LIỆU MÔ PHỎNG, không phải giao dịch hay kết quả nghiên cứu.')
) v([DatasetId],[DatasetCode],[MarketId],[DataKind],[PriceBasis],[PriceUnit],[ObservedThrough],[ManifestPath],[ProvenanceNote]) ON d.[DatasetId]=v.[DatasetId] WHERE EXISTS(SELECT d.[DatasetId],d.[DatasetCode],d.[MarketId],d.[DataKind],d.[PriceBasis],d.[PriceUnit],d.[ObservedThrough],d.[ManifestPath],d.[ProvenanceNote] EXCEPT SELECT v.[DatasetId],v.[DatasetCode],v.[MarketId],v.[DataKind],v.[PriceBasis],v.[PriceUnit],v.[ObservedThrough],v.[ManifestPath],v.[ProvenanceNote])) THROW 51100,N'Import conflict: Dataset',1;
 INSERT dbo.[Dataset]([DatasetId],[DatasetCode],[MarketId],[DataKind],[PriceBasis],[PriceUnit],[ObservedThrough],[ManifestPath],[ProvenanceNote]) SELECT v.[DatasetId],v.[DatasetCode],v.[MarketId],v.[DataKind],v.[PriceBasis],v.[PriceUnit],v.[ObservedThrough],v.[ManifestPath],v.[ProvenanceNote] FROM (VALUES
(1,N'SYNTHETIC_DEMO_V1',1,N'SYNTHETIC',N'SOURCE_CLOSE',N'Đơn vị mô phỏng',N'2025-02-19',N'data/sample/tables.json',N'DỮ LIỆU MÔ PHỎNG, không phải giao dịch hay kết quả nghiên cứu.')
) v([DatasetId],[DatasetCode],[MarketId],[DataKind],[PriceBasis],[PriceUnit],[ObservedThrough],[ManifestPath],[ProvenanceNote]) WHERE NOT EXISTS(SELECT 1 FROM dbo.[Dataset] d WITH(UPDLOCK,HOLDLOCK) WHERE d.[DatasetId]=v.[DatasetId]);
 SET @Added=@Added+@@ROWCOUNT;
 INSERT #ImportReceipt VALUES(N'Dataset',1,@Added);
 SET @Added=0;
 IF EXISTS(SELECT 1 FROM dbo.[TradingDay] d JOIN (VALUES
(1,N'2025-01-02'),
(1,N'2025-01-03'),
(1,N'2025-01-06'),
(1,N'2025-01-07'),
(1,N'2025-01-08'),
(1,N'2025-01-09'),
(1,N'2025-01-10'),
(1,N'2025-01-13'),
(1,N'2025-01-14'),
(1,N'2025-01-15'),
(1,N'2025-01-16'),
(1,N'2025-01-17'),
(1,N'2025-01-20'),
(1,N'2025-01-21'),
(1,N'2025-01-22'),
(1,N'2025-01-23'),
(1,N'2025-01-24'),
(1,N'2025-01-27'),
(1,N'2025-01-28'),
(1,N'2025-01-29'),
(1,N'2025-01-30'),
(1,N'2025-01-31'),
(1,N'2025-02-03'),
(1,N'2025-02-04'),
(1,N'2025-02-05'),
(1,N'2025-02-06'),
(1,N'2025-02-07'),
(1,N'2025-02-10'),
(1,N'2025-02-11'),
(1,N'2025-02-12'),
(1,N'2025-02-13'),
(1,N'2025-02-14'),
(1,N'2025-02-17'),
(1,N'2025-02-18'),
(1,N'2025-02-19'),
(1,N'2025-02-20'),
(1,N'2025-02-21'),
(1,N'2025-02-24'),
(1,N'2025-02-25'),
(1,N'2025-02-26'),
(1,N'2025-02-27'),
(1,N'2025-02-28')
) v([DatasetId],[TradeDate]) ON d.[DatasetId]=v.[DatasetId] AND d.[TradeDate]=v.[TradeDate] WHERE EXISTS(SELECT d.[DatasetId],d.[TradeDate] EXCEPT SELECT v.[DatasetId],v.[TradeDate])) THROW 51100,N'Import conflict: TradingDay',1;
 INSERT dbo.[TradingDay]([DatasetId],[TradeDate]) SELECT v.[DatasetId],v.[TradeDate] FROM (VALUES
(1,N'2025-01-02'),
(1,N'2025-01-03'),
(1,N'2025-01-06'),
(1,N'2025-01-07'),
(1,N'2025-01-08'),
(1,N'2025-01-09'),
(1,N'2025-01-10'),
(1,N'2025-01-13'),
(1,N'2025-01-14'),
(1,N'2025-01-15'),
(1,N'2025-01-16'),
(1,N'2025-01-17'),
(1,N'2025-01-20'),
(1,N'2025-01-21'),
(1,N'2025-01-22'),
(1,N'2025-01-23'),
(1,N'2025-01-24'),
(1,N'2025-01-27'),
(1,N'2025-01-28'),
(1,N'2025-01-29'),
(1,N'2025-01-30'),
(1,N'2025-01-31'),
(1,N'2025-02-03'),
(1,N'2025-02-04'),
(1,N'2025-02-05'),
(1,N'2025-02-06'),
(1,N'2025-02-07'),
(1,N'2025-02-10'),
(1,N'2025-02-11'),
(1,N'2025-02-12'),
(1,N'2025-02-13'),
(1,N'2025-02-14'),
(1,N'2025-02-17'),
(1,N'2025-02-18'),
(1,N'2025-02-19'),
(1,N'2025-02-20'),
(1,N'2025-02-21'),
(1,N'2025-02-24'),
(1,N'2025-02-25'),
(1,N'2025-02-26'),
(1,N'2025-02-27'),
(1,N'2025-02-28')
) v([DatasetId],[TradeDate]) WHERE NOT EXISTS(SELECT 1 FROM dbo.[TradingDay] d WITH(UPDLOCK,HOLDLOCK) WHERE d.[DatasetId]=v.[DatasetId] AND d.[TradeDate]=v.[TradeDate]);
 SET @Added=@Added+@@ROWCOUNT;
 INSERT #ImportReceipt VALUES(N'TradingDay',42,@Added);
 SET @Added=0;
 IF EXISTS(SELECT 1 FROM dbo.[DailyPrice] d JOIN (VALUES
(1,1,N'2025-01-02',N'23.2622',N'23.7622',N'22.5098',N'23.0098',11000),
(1,1,N'2025-01-03',N'23.5623',N'24.0623',N'22.7895',N'23.2895',11200),
(1,1,N'2025-01-06',N'23.1925',N'23.6925',N'22.6502',N'23.1502',11400),
(1,1,N'2025-01-07',N'22.445',N'23.172',N'21.945',N'22.672',11600),
(1,1,N'2025-01-08',N'21.7657',N'22.5534',N'21.2657',N'22.0534',11800),
(1,1,N'2025-01-09',N'21.458',N'22.0418',N'20.958',N'21.5418',12000),
(1,1,N'2025-01-10',N'21.5447',N'22.0447',N'20.8476',N'21.3476',12200),
(1,1,N'2025-01-13',N'21.8667',N'22.3667',N'21.0699',N'21.5699',12400),
(1,1,N'2025-01-14',N'22.2861',N'22.7861',N'21.6625',N'22.1625',12600),
(1,1,N'2025-01-15',N'22.7867',N'23.4499',N'22.2867',N'22.9499',12800),
(1,1,N'2025-01-16',N'23.3884',N'24.1884',N'22.8884',N'23.6884',13000),
(1,1,N'2025-01-17',N'23.9905',N'24.6515',N'23.4905',N'24.1515',13200),
(1,1,N'2025-01-20',N'24.335',N'24.835',N'23.7089',N'24.2089',13400),
(1,1,N'2025-01-21',N'24.1691',N'24.6691',N'23.3719',N'23.8719',13600),
(1,1,N'2025-01-22',N'23.4848',N'23.9848',N'22.7897',N'23.2897',13800),
(1,1,N'2025-01-23',N'22.6108',N'23.1972',N'22.1108',N'22.6972',14000),
(1,1,N'2025-01-24',N'22.0443',N'22.8327',N'21.5443',N'22.3327',14200),
(1,1,N'2025-01-27',N'22.1297',N'22.855',N'21.6297',N'22.355',14400),
(1,1,N'2025-01-28',N'22.8328',N'23.3328',N'22.2878',N'22.7878',14600),
(1,1,N'2025-01-29',N'23.7852',N'24.2852',N'23.0113',N'23.5113',14800),
(1,1,N'2025-01-30',N'24.5552',N'25.0552',N'23.8042',N'24.3042',15000),
(1,1,N'2025-01-31',N'24.9183',N'25.421',N'24.4183',N'24.921',15200),
(1,1,N'2025-02-03',N'24.9237',N'25.6776',N'24.4237',N'25.1776',15400),
(1,1,N'2025-02-04',N'24.7442',N'25.5159',N'24.2442',N'25.0159',15600),
(1,1,N'2025-02-05',N'24.484',N'25.0237',N'23.984',N'24.5237',15800),
(1,1,N'2025-02-06',N'24.1333',N'24.6333',N'23.4045',N'23.9045',16000),
(1,1,N'2025-02-07',N'23.6929',N'24.1929',N'22.906',N'23.406',16200),
(1,1,N'2025-02-10',N'23.315',N'23.815',N'22.7337',N'23.2337',16400),
(1,1,N'2025-02-11',N'23.2803',N'23.9794',N'22.7803',N'23.4794',16600),
(1,1,N'2025-02-12',N'23.7921',N'24.5885',N'23.2921',N'24.0885',16800),
(1,1,N'2025-02-13',N'24.7587',N'25.3799',N'24.2587',N'24.8799',17000),
(1,1,N'2025-02-14',N'25.7738',N'26.2738',N'25.1084',N'25.6084',17200),
(1,1,N'2025-02-17',N'26.351',N'26.851',N'25.551',N'26.051',17400),
(1,1,N'2025-02-18',N'26.2433',N'26.7433',N'25.5846',N'26.0846',17600),
(1,1,N'2025-02-19',N'25.6003',N'26.2288',N'25.1003',N'25.7288',17800),
(1,2,N'2025-01-02',N'25.364',N'25.864',N'24.5912',N'25.0912',12000),
(1,2,N'2025-01-03',N'24.7509',N'25.2509',N'24.2086',N'24.7086',12200),
(1,2,N'2025-01-06',N'23.883',N'24.61',N'23.383',N'24.11',12400),
(1,2,N'2025-01-07',N'23.2481',N'24.0358',N'22.7481',N'23.5358',12600),
(1,2,N'2025-01-08',N'23.1343',N'23.7181',N'22.6343',N'23.2181',12800),
(1,2,N'2025-01-09',N'23.4964',N'23.9964',N'22.7993',N'23.2993',13000),
(1,2,N'2025-01-10',N'24.0793',N'24.5793',N'23.2825',N'23.7825',13200),
(1,2,N'2025-01-13',N'24.6539',N'25.1539',N'24.0303',N'24.5303',13400),
(1,2,N'2025-01-14',N'25.1497',N'25.8129',N'24.6497',N'25.3129',13600),
(1,2,N'2025-01-15',N'25.5884',N'26.3884',N'25.0884',N'25.8884',13800),
(1,2,N'2025-01-16',N'25.9262',N'26.5872',N'25.4262',N'26.0872',14000),
(1,2,N'2025-01-17',N'25.9974',N'26.4974',N'25.3713',N'25.8713',14200),
(1,2,N'2025-01-20',N'25.6447',N'26.1447',N'24.8475',N'25.3475',14400),
(1,2,N'2025-01-21',N'24.9253',N'25.4253',N'24.2302',N'24.7302',14600),
(1,2,N'2025-01-22',N'24.1802',N'24.7666',N'23.6802',N'24.2666',14800),
(1,2,N'2025-01-23',N'23.8616',N'24.65',N'23.3616',N'24.15',15000),
(1,2,N'2025-01-24',N'24.2273',N'24.9526',N'23.7273',N'24.4526',15200),
(1,2,N'2025-01-27',N'25.1451',N'25.6451',N'24.6001',N'25.1001',15400),
(1,2,N'2025-01-28',N'26.1717',N'26.6717',N'25.3978',N'25.8978',15600),
(1,2,N'2025-01-29',N'26.8495',N'27.3495',N'26.0985',N'26.5985',15800),
(1,2,N'2025-01-30',N'26.986',N'27.4887',N'26.486',N'26.9887',16000),
(1,2,N'2025-01-31',N'26.7098',N'27.4637',N'26.2098',N'26.9637',16200),
(1,2,N'2025-02-03',N'26.292',N'27.0637',N'25.792',N'26.5637',16400),
(1,2,N'2025-02-04',N'25.92',N'26.4597',N'25.42',N'25.9597',16600),
(1,2,N'2025-02-05',N'25.6231',N'26.1231',N'24.8943',N'25.3943',16800),
(1,2,N'2025-02-06',N'25.3832',N'25.8832',N'24.5963',N'25.0963',17000),
(1,2,N'2025-02-07',N'25.2827',N'25.7827',N'24.7014',N'25.2014',17200),
(1,2,N'2025-02-10',N'25.5051',N'26.2042',N'25.0051',N'25.7042',17400),
(1,2,N'2025-02-11',N'26.1642',N'26.9606',N'25.6642',N'26.4606',17600),
(1,2,N'2025-02-12',N'27.1165',N'27.7377',N'26.6165',N'27.2377',17800),
(1,2,N'2025-02-13',N'27.9609',N'28.4609',N'27.2955',N'27.7955',18000),
(1,2,N'2025-02-14',N'28.2707',N'28.7707',N'27.4707',N'27.9707',18200),
(1,2,N'2025-02-17',N'27.8921',N'28.3921',N'27.2334',N'27.7334',18400),
(1,2,N'2025-02-18',N'27.0695',N'27.698',N'26.5695',N'27.198',18600),
(1,2,N'2025-02-19',N'26.2854',N'27.0829',N'25.7854',N'26.5829',18800),
(1,3,N'2025-01-02',N'26.2116',N'26.7116',N'25.6693',N'26.1693',13000),
(1,3,N'2025-01-03',N'25.332',N'26.059',N'24.832',N'25.559',13200),
(1,3,N'2025-01-06',N'24.8464',N'25.6341',N'24.3464',N'25.1341',13400),
(1,3,N'2025-01-07',N'24.9908',N'25.5746',N'24.4908',N'25.0746',13600),
(1,3,N'2025-01-08',N'25.6298',N'26.1298',N'24.9327',N'25.4327',13800),
(1,3,N'2025-01-09',N'26.4115',N'26.9115',N'25.6147',N'26.1147',14000),
(1,3,N'2025-01-10',N'27.0374',N'27.5374',N'26.4138',N'26.9138',14200),
(1,3,N'2025-01-13',N'27.4192',N'28.0824',N'26.9192',N'27.5824',14400),
(1,3,N'2025-01-14',N'27.6183',N'28.4183',N'27.1183',N'27.9183',14600),
(1,3,N'2025-01-15',N'27.6745',N'28.3355',N'27.1745',N'27.8355',14800),
(1,3,N'2025-01-16',N'27.5206',N'28.0206',N'26.8945',N'27.3945',15000),
(1,3,N'2025-01-17',N'27.078',N'27.578',N'26.2808',N'26.7808',15200),
(1,3,N'2025-01-20',N'26.4353',N'26.9353',N'25.7402',N'26.2402',15400),
(1,3,N'2025-01-21',N'25.9065',N'26.4929',N'25.4065',N'25.9929',15600),
(1,3,N'2025-01-22',N'25.8684',N'26.6568',N'25.3684',N'26.1568',15800),
(1,3,N'2025-01-23',N'26.4808',N'27.2061',N'25.9808',N'26.7061',16000),
(1,3,N'2025-01-24',N'27.5253',N'28.0253',N'26.9803',N'27.4803',16200),
(1,3,N'2025-01-27',N'28.5144',N'29.0144',N'27.7405',N'28.2405',16400),
(1,3,N'2025-01-28',N'29.0034',N'29.5034',N'28.2524',N'28.7524',16600),
(1,3,N'2025-01-29',N'28.8661',N'29.3688',N'28.3661',N'28.8688',16800),
(1,3,N'2025-01-30',N'28.3264',N'29.0803',N'27.8264',N'28.5803',17000),
(1,3,N'2025-01-31',N'27.7476',N'28.5193',N'27.2476',N'28.0193',17200),
(1,3,N'2025-02-03',N'27.3734',N'27.9131',N'26.8734',N'27.4131',17400),
(1,3,N'2025-02-04',N'27.2337',N'27.7337',N'26.5049',N'27.0049',17600),
(1,3,N'2025-02-05',N'27.2557',N'27.7557',N'26.4688',N'26.9688',17800),
(1,3,N'2025-02-06',N'27.4301',N'27.9301',N'26.8488',N'27.3488',18000),
(1,3,N'2025-02-07',N'27.8445',N'28.5436',N'27.3445',N'28.0436',18200),
(1,3,N'2025-02-10',N'28.5456',N'29.342',N'28.0456',N'28.842',18400),
(1,3,N'2025-02-11',N'29.3752',N'29.9964',N'28.8752',N'29.4964',18600),
(1,3,N'2025-02-12',N'29.9752',N'30.4752',N'29.3098',N'29.8098',18800),
(1,3,N'2025-02-13',N'30.004',N'30.504',N'29.204',N'29.704',19000),
(1,3,N'2025-02-14',N'29.4062',N'29.9062',N'28.7475',N'29.2475',19200),
(1,3,N'2025-02-17',N'28.5027',N'29.1312',N'28.0027',N'28.6312',19400),
(1,3,N'2025-02-18',N'27.8043',N'28.6018',N'27.3043',N'28.1018',19600),
(1,3,N'2025-02-19',N'27.6826',N'28.3757',N'27.1826',N'27.8757',19800),
(1,4,N'2025-01-02',N'26.8648',N'27.5918',N'26.3648',N'27.0918',14000),
(1,4,N'2025-01-03',N'26.6099',N'27.3976',N'26.1099',N'26.8976',14200),
(1,4,N'2025-01-06',N'27.0361',N'27.6199',N'26.5361',N'27.1199',14400),
(1,4,N'2025-01-07',N'27.9096',N'28.4096',N'27.2125',N'27.7125',14600),
(1,4,N'2025-01-08',N'28.7967',N'29.2967',N'27.9999',N'28.4999',14800),
(1,4,N'2025-01-09',N'29.362',N'29.862',N'28.7384',N'29.2384',15000),
(1,4,N'2025-01-10',N'29.5383',N'30.2015',N'29.0383',N'29.7015',15200),
(1,4,N'2025-01-13',N'29.4589',N'30.2589',N'28.9589',N'29.7589',15400),
(1,4,N'2025-01-14',N'29.2609',N'29.9219',N'28.7609',N'29.4219',15600),
(1,4,N'2025-01-15',N'28.9658',N'29.4658',N'28.3397',N'28.8397',15800),
(1,4,N'2025-01-16',N'28.5444',N'29.0444',N'27.7472',N'28.2472',16000),
(1,4,N'2025-01-17',N'28.0778',N'28.5778',N'27.3827',N'27.8827',16200),
(1,4,N'2025-01-20',N'27.8186',N'28.405',N'27.3186',N'27.905',16400),
(1,4,N'2025-01-21',N'28.0494',N'28.8378',N'27.5494',N'28.3378',16600),
(1,4,N'2025-01-22',N'28.836',N'29.5613',N'28.336',N'29.0613',16800),
(1,4,N'2025-01-23',N'29.8992',N'30.3992',N'29.3542',N'29.8542',17000),
(1,4,N'2025-01-24',N'30.7449',N'31.2449',N'29.971',N'30.471',17200),
(1,4,N'2025-01-27',N'30.9786',N'31.4786',N'30.2276',N'30.7276',17400),
(1,4,N'2025-01-28',N'30.5632',N'31.0659',N'30.0632',N'30.5659',17600),
(1,4,N'2025-01-29',N'29.8198',N'30.5737',N'29.3198',N'30.0737',17800),
(1,4,N'2025-01-30',N'29.1828',N'29.9545',N'28.6828',N'29.4545',18000),
(1,4,N'2025-01-31',N'28.9163',N'29.456',N'28.4163',N'28.956',18200),
(1,4,N'2025-02-03',N'29.0125',N'29.5125',N'28.2837',N'28.7837',18400),
(1,4,N'2025-02-04',N'29.3163',N'29.8163',N'28.5294',N'29.0294',18600),
(1,4,N'2025-02-05',N'29.7198',N'30.2198',N'29.1385',N'29.6385',18800),
(1,4,N'2025-02-06',N'30.2308',N'30.9299',N'29.7308',N'30.4299',19000),
(1,4,N'2025-02-07',N'30.862',N'31.6584',N'30.362',N'31.1584',19200),
(1,4,N'2025-02-10',N'31.4798',N'32.101',N'30.9798',N'31.601',19400),
(1,4,N'2025-02-11',N'31.8',N'32.3',N'31.1346',N'31.6346',19600),
(1,4,N'2025-02-12',N'31.5788',N'32.0788',N'30.7788',N'31.2788',19800),
(1,4,N'2025-02-13',N'30.8481',N'31.3481',N'30.1894',N'30.6894',20000),
(1,4,N'2025-02-14',N'29.9752',N'30.6037',N'29.4752',N'30.1037',20200),
(1,4,N'2025-02-17',N'29.4602',N'30.2577',N'28.9602',N'29.7577',20400),
(1,4,N'2025-02-18',N'29.6107',N'30.3038',N'29.1107',N'29.8038',20600),
(1,4,N'2025-02-19',N'30.3462',N'30.8462',N'29.7573',N'30.2573',20800),
(1,5,N'2025-01-02',N'28.5616',N'29.3493',N'28.0616',N'28.8493',15000),
(1,5,N'2025-01-03',N'29.2487',N'29.8325',N'28.7487',N'29.3325',15200),
(1,5,N'2025-01-06',N'30.2774',N'30.7774',N'29.5803',N'30.0803',15400),
(1,5,N'2025-01-07',N'31.1597',N'31.6597',N'30.3629',N'30.8629',15600),
(1,5,N'2025-01-08',N'31.562',N'32.062',N'30.9384',N'31.4384',15800),
(1,5,N'2025-01-09',N'31.474',N'32.1372',N'30.974',N'31.6372',16000),
(1,5,N'2025-01-10',N'31.1213',N'31.9213',N'30.6213',N'31.4213',16200),
(1,5,N'2025-01-13',N'30.7365',N'31.3975',N'30.2365',N'30.8975',16400),
(1,5,N'2025-01-14',N'30.4063',N'30.9063',N'29.7802',N'30.2802',16600),
(1,5,N'2025-01-15',N'30.1138',N'30.6138',N'29.3166',N'29.8166',16800),
(1,5,N'2025-01-16',N'29.8951',N'30.3951',N'29.2',N'29.7',17000),
(1,5,N'2025-01-17',N'29.9162',N'30.5026',N'29.4162',N'30.0026',17200),
(1,5,N'2025-01-20',N'30.3617',N'31.1501',N'29.8617',N'30.6501',17400),
(1,5,N'2025-01-21',N'31.2225',N'31.9478',N'30.7225',N'31.4478',17600),
(1,5,N'2025-01-22',N'32.1935',N'32.6935',N'31.6485',N'32.1485',17800),
(1,5,N'2025-01-23',N'32.8126',N'33.3126',N'32.0387',N'32.5387',18000),
(1,5,N'2025-01-24',N'32.7647',N'33.2647',N'32.0137',N'32.5137',18200),
(1,5,N'2025-01-27',N'32.111',N'32.6137',N'31.611',N'32.1137',18400),
(1,5,N'2025-01-28',N'31.2558',N'32.0097',N'30.7558',N'31.5097',18600),
(1,5,N'2025-01-29',N'30.6726',N'31.4443',N'30.1726',N'30.9443',18800),
(1,5,N'2025-01-30',N'30.6066',N'31.1463',N'30.1066',N'30.6463',19000),
(1,5,N'2025-01-31',N'30.9802',N'31.4802',N'30.2514',N'30.7514',19200),
(1,5,N'2025-02-03',N'31.5411',N'32.0411',N'30.7542',N'31.2542',19400),
(1,5,N'2025-02-04',N'32.0919',N'32.5919',N'31.5106',N'32.0106',19600),
(1,5,N'2025-02-05',N'32.5886',N'33.2877',N'32.0886',N'32.7877',19800),
(1,5,N'2025-02-06',N'33.0491',N'33.8455',N'32.5491',N'33.3455',20000),
(1,5,N'2025-02-07',N'33.3995',N'34.0207',N'32.8995',N'33.5207',20200),
(1,5,N'2025-02-10',N'33.4488',N'33.9488',N'32.7834',N'33.2834',20400),
(1,5,N'2025-02-11',N'33.048',N'33.548',N'32.248',N'32.748',20600),
(1,5,N'2025-02-12',N'32.2916',N'32.7916',N'31.6329',N'32.1329',20800),
(1,5,N'2025-02-13',N'31.556',N'32.1845',N'31.056',N'31.6845',21000),
(1,5,N'2025-02-14',N'31.2934',N'32.0909',N'30.7934',N'31.5909',21200),
(1,5,N'2025-02-17',N'31.723',N'32.4161',N'31.223',N'31.9161',21400),
(1,5,N'2025-02-18',N'32.6669',N'33.1669',N'32.078',N'32.578',21600),
(1,5,N'2025-02-19',N'33.666',N'34.166',N'32.8769',N'33.3769',21800),
(1,6,N'2025-01-02',N'31.5809',N'32.1647',N'31.0809',N'31.6647',16000),
(1,6,N'2025-01-03',N'32.6609',N'33.1609',N'31.9638',N'32.4638',16200),
(1,6,N'2025-01-06',N'33.4292',N'33.9292',N'32.6324',N'33.1324',16400),
(1,6,N'2025-01-07',N'33.5919',N'34.0919',N'32.9683',N'33.4683',16600),
(1,6,N'2025-01-08',N'33.2223',N'33.8855',N'32.7223',N'33.3855',16800),
(1,6,N'2025-01-09',N'32.6445',N'33.4445',N'32.1445',N'32.9445',17000),
(1,6,N'2025-01-10',N'32.1698',N'32.8308',N'31.6698',N'32.3308',17200),
(1,6,N'2025-01-13',N'31.9163',N'32.4163',N'31.2902',N'31.7902',17400),
(1,6,N'2025-01-14',N'31.8401',N'32.3401',N'31.0429',N'31.5429',17600),
(1,6,N'2025-01-15',N'31.9019',N'32.4019',N'31.2068',N'31.7068',17800),
(1,6,N'2025-01-16',N'32.1697',N'32.7561',N'31.6697',N'32.2561',18000),
(1,6,N'2025-01-17',N'32.7419',N'33.5303',N'32.2419',N'33.0303',18200),
(1,6,N'2025-01-20',N'33.5652',N'34.2905',N'33.0652',N'33.7905',18400),
(1,6,N'2025-01-21',N'34.3474',N'34.8474',N'33.8024',N'34.3024',18600),
(1,6,N'2025-01-22',N'34.6927',N'35.1927',N'33.9188',N'34.4188',18800),
(1,6,N'2025-01-23',N'34.3813',N'34.8813',N'33.6303',N'34.1303',19000),
(1,6,N'2025-01-24',N'33.5666',N'34.0693',N'33.0666',N'33.5693',19200),
(1,6,N'2025-01-27',N'32.7092',N'33.4631',N'32.2092',N'32.9631',19400),
(1,6,N'2025-01-28',N'32.2832',N'33.0549',N'31.7832',N'32.5549',19600),
(1,6,N'2025-01-29',N'32.4791',N'33.0188',N'31.9791',N'32.5188',19800),
(1,6,N'2025-01-30',N'33.1276',N'33.6276',N'32.3988',N'32.8988',20000),
(1,6,N'2025-01-31',N'33.8805',N'34.3805',N'33.0936',N'33.5936',20200),
(1,6,N'2025-02-03',N'34.4733',N'34.9733',N'33.892',N'34.392',20400),
(1,6,N'2025-02-04',N'34.8473',N'35.5464',N'34.3473',N'35.0464',20600),
(1,6,N'2025-02-05',N'35.0634',N'35.8598',N'34.5634',N'35.3598',20800)
) v([DatasetId],[StockId],[TradeDate],[OpenPrice],[HighPrice],[LowPrice],[ClosePrice],[Volume]) ON d.[DatasetId]=v.[DatasetId] AND d.[StockId]=v.[StockId] AND d.[TradeDate]=v.[TradeDate] WHERE EXISTS(SELECT d.[DatasetId],d.[StockId],d.[TradeDate],d.[OpenPrice],d.[HighPrice],d.[LowPrice],d.[ClosePrice],d.[Volume] EXCEPT SELECT v.[DatasetId],v.[StockId],v.[TradeDate],v.[OpenPrice],v.[HighPrice],v.[LowPrice],v.[ClosePrice],v.[Volume])) THROW 51100,N'Import conflict: DailyPrice',1;
 INSERT dbo.[DailyPrice]([DatasetId],[StockId],[TradeDate],[OpenPrice],[HighPrice],[LowPrice],[ClosePrice],[Volume]) SELECT v.[DatasetId],v.[StockId],v.[TradeDate],v.[OpenPrice],v.[HighPrice],v.[LowPrice],v.[ClosePrice],v.[Volume] FROM (VALUES
(1,1,N'2025-01-02',N'23.2622',N'23.7622',N'22.5098',N'23.0098',11000),
(1,1,N'2025-01-03',N'23.5623',N'24.0623',N'22.7895',N'23.2895',11200),
(1,1,N'2025-01-06',N'23.1925',N'23.6925',N'22.6502',N'23.1502',11400),
(1,1,N'2025-01-07',N'22.445',N'23.172',N'21.945',N'22.672',11600),
(1,1,N'2025-01-08',N'21.7657',N'22.5534',N'21.2657',N'22.0534',11800),
(1,1,N'2025-01-09',N'21.458',N'22.0418',N'20.958',N'21.5418',12000),
(1,1,N'2025-01-10',N'21.5447',N'22.0447',N'20.8476',N'21.3476',12200),
(1,1,N'2025-01-13',N'21.8667',N'22.3667',N'21.0699',N'21.5699',12400),
(1,1,N'2025-01-14',N'22.2861',N'22.7861',N'21.6625',N'22.1625',12600),
(1,1,N'2025-01-15',N'22.7867',N'23.4499',N'22.2867',N'22.9499',12800),
(1,1,N'2025-01-16',N'23.3884',N'24.1884',N'22.8884',N'23.6884',13000),
(1,1,N'2025-01-17',N'23.9905',N'24.6515',N'23.4905',N'24.1515',13200),
(1,1,N'2025-01-20',N'24.335',N'24.835',N'23.7089',N'24.2089',13400),
(1,1,N'2025-01-21',N'24.1691',N'24.6691',N'23.3719',N'23.8719',13600),
(1,1,N'2025-01-22',N'23.4848',N'23.9848',N'22.7897',N'23.2897',13800),
(1,1,N'2025-01-23',N'22.6108',N'23.1972',N'22.1108',N'22.6972',14000),
(1,1,N'2025-01-24',N'22.0443',N'22.8327',N'21.5443',N'22.3327',14200),
(1,1,N'2025-01-27',N'22.1297',N'22.855',N'21.6297',N'22.355',14400),
(1,1,N'2025-01-28',N'22.8328',N'23.3328',N'22.2878',N'22.7878',14600),
(1,1,N'2025-01-29',N'23.7852',N'24.2852',N'23.0113',N'23.5113',14800),
(1,1,N'2025-01-30',N'24.5552',N'25.0552',N'23.8042',N'24.3042',15000),
(1,1,N'2025-01-31',N'24.9183',N'25.421',N'24.4183',N'24.921',15200),
(1,1,N'2025-02-03',N'24.9237',N'25.6776',N'24.4237',N'25.1776',15400),
(1,1,N'2025-02-04',N'24.7442',N'25.5159',N'24.2442',N'25.0159',15600),
(1,1,N'2025-02-05',N'24.484',N'25.0237',N'23.984',N'24.5237',15800),
(1,1,N'2025-02-06',N'24.1333',N'24.6333',N'23.4045',N'23.9045',16000),
(1,1,N'2025-02-07',N'23.6929',N'24.1929',N'22.906',N'23.406',16200),
(1,1,N'2025-02-10',N'23.315',N'23.815',N'22.7337',N'23.2337',16400),
(1,1,N'2025-02-11',N'23.2803',N'23.9794',N'22.7803',N'23.4794',16600),
(1,1,N'2025-02-12',N'23.7921',N'24.5885',N'23.2921',N'24.0885',16800),
(1,1,N'2025-02-13',N'24.7587',N'25.3799',N'24.2587',N'24.8799',17000),
(1,1,N'2025-02-14',N'25.7738',N'26.2738',N'25.1084',N'25.6084',17200),
(1,1,N'2025-02-17',N'26.351',N'26.851',N'25.551',N'26.051',17400),
(1,1,N'2025-02-18',N'26.2433',N'26.7433',N'25.5846',N'26.0846',17600),
(1,1,N'2025-02-19',N'25.6003',N'26.2288',N'25.1003',N'25.7288',17800),
(1,2,N'2025-01-02',N'25.364',N'25.864',N'24.5912',N'25.0912',12000),
(1,2,N'2025-01-03',N'24.7509',N'25.2509',N'24.2086',N'24.7086',12200),
(1,2,N'2025-01-06',N'23.883',N'24.61',N'23.383',N'24.11',12400),
(1,2,N'2025-01-07',N'23.2481',N'24.0358',N'22.7481',N'23.5358',12600),
(1,2,N'2025-01-08',N'23.1343',N'23.7181',N'22.6343',N'23.2181',12800),
(1,2,N'2025-01-09',N'23.4964',N'23.9964',N'22.7993',N'23.2993',13000),
(1,2,N'2025-01-10',N'24.0793',N'24.5793',N'23.2825',N'23.7825',13200),
(1,2,N'2025-01-13',N'24.6539',N'25.1539',N'24.0303',N'24.5303',13400),
(1,2,N'2025-01-14',N'25.1497',N'25.8129',N'24.6497',N'25.3129',13600),
(1,2,N'2025-01-15',N'25.5884',N'26.3884',N'25.0884',N'25.8884',13800),
(1,2,N'2025-01-16',N'25.9262',N'26.5872',N'25.4262',N'26.0872',14000),
(1,2,N'2025-01-17',N'25.9974',N'26.4974',N'25.3713',N'25.8713',14200),
(1,2,N'2025-01-20',N'25.6447',N'26.1447',N'24.8475',N'25.3475',14400),
(1,2,N'2025-01-21',N'24.9253',N'25.4253',N'24.2302',N'24.7302',14600),
(1,2,N'2025-01-22',N'24.1802',N'24.7666',N'23.6802',N'24.2666',14800),
(1,2,N'2025-01-23',N'23.8616',N'24.65',N'23.3616',N'24.15',15000),
(1,2,N'2025-01-24',N'24.2273',N'24.9526',N'23.7273',N'24.4526',15200),
(1,2,N'2025-01-27',N'25.1451',N'25.6451',N'24.6001',N'25.1001',15400),
(1,2,N'2025-01-28',N'26.1717',N'26.6717',N'25.3978',N'25.8978',15600),
(1,2,N'2025-01-29',N'26.8495',N'27.3495',N'26.0985',N'26.5985',15800),
(1,2,N'2025-01-30',N'26.986',N'27.4887',N'26.486',N'26.9887',16000),
(1,2,N'2025-01-31',N'26.7098',N'27.4637',N'26.2098',N'26.9637',16200),
(1,2,N'2025-02-03',N'26.292',N'27.0637',N'25.792',N'26.5637',16400),
(1,2,N'2025-02-04',N'25.92',N'26.4597',N'25.42',N'25.9597',16600),
(1,2,N'2025-02-05',N'25.6231',N'26.1231',N'24.8943',N'25.3943',16800),
(1,2,N'2025-02-06',N'25.3832',N'25.8832',N'24.5963',N'25.0963',17000),
(1,2,N'2025-02-07',N'25.2827',N'25.7827',N'24.7014',N'25.2014',17200),
(1,2,N'2025-02-10',N'25.5051',N'26.2042',N'25.0051',N'25.7042',17400),
(1,2,N'2025-02-11',N'26.1642',N'26.9606',N'25.6642',N'26.4606',17600),
(1,2,N'2025-02-12',N'27.1165',N'27.7377',N'26.6165',N'27.2377',17800),
(1,2,N'2025-02-13',N'27.9609',N'28.4609',N'27.2955',N'27.7955',18000),
(1,2,N'2025-02-14',N'28.2707',N'28.7707',N'27.4707',N'27.9707',18200),
(1,2,N'2025-02-17',N'27.8921',N'28.3921',N'27.2334',N'27.7334',18400),
(1,2,N'2025-02-18',N'27.0695',N'27.698',N'26.5695',N'27.198',18600),
(1,2,N'2025-02-19',N'26.2854',N'27.0829',N'25.7854',N'26.5829',18800),
(1,3,N'2025-01-02',N'26.2116',N'26.7116',N'25.6693',N'26.1693',13000),
(1,3,N'2025-01-03',N'25.332',N'26.059',N'24.832',N'25.559',13200),
(1,3,N'2025-01-06',N'24.8464',N'25.6341',N'24.3464',N'25.1341',13400),
(1,3,N'2025-01-07',N'24.9908',N'25.5746',N'24.4908',N'25.0746',13600),
(1,3,N'2025-01-08',N'25.6298',N'26.1298',N'24.9327',N'25.4327',13800),
(1,3,N'2025-01-09',N'26.4115',N'26.9115',N'25.6147',N'26.1147',14000),
(1,3,N'2025-01-10',N'27.0374',N'27.5374',N'26.4138',N'26.9138',14200),
(1,3,N'2025-01-13',N'27.4192',N'28.0824',N'26.9192',N'27.5824',14400),
(1,3,N'2025-01-14',N'27.6183',N'28.4183',N'27.1183',N'27.9183',14600),
(1,3,N'2025-01-15',N'27.6745',N'28.3355',N'27.1745',N'27.8355',14800),
(1,3,N'2025-01-16',N'27.5206',N'28.0206',N'26.8945',N'27.3945',15000),
(1,3,N'2025-01-17',N'27.078',N'27.578',N'26.2808',N'26.7808',15200),
(1,3,N'2025-01-20',N'26.4353',N'26.9353',N'25.7402',N'26.2402',15400),
(1,3,N'2025-01-21',N'25.9065',N'26.4929',N'25.4065',N'25.9929',15600),
(1,3,N'2025-01-22',N'25.8684',N'26.6568',N'25.3684',N'26.1568',15800),
(1,3,N'2025-01-23',N'26.4808',N'27.2061',N'25.9808',N'26.7061',16000),
(1,3,N'2025-01-24',N'27.5253',N'28.0253',N'26.9803',N'27.4803',16200),
(1,3,N'2025-01-27',N'28.5144',N'29.0144',N'27.7405',N'28.2405',16400),
(1,3,N'2025-01-28',N'29.0034',N'29.5034',N'28.2524',N'28.7524',16600),
(1,3,N'2025-01-29',N'28.8661',N'29.3688',N'28.3661',N'28.8688',16800),
(1,3,N'2025-01-30',N'28.3264',N'29.0803',N'27.8264',N'28.5803',17000),
(1,3,N'2025-01-31',N'27.7476',N'28.5193',N'27.2476',N'28.0193',17200),
(1,3,N'2025-02-03',N'27.3734',N'27.9131',N'26.8734',N'27.4131',17400),
(1,3,N'2025-02-04',N'27.2337',N'27.7337',N'26.5049',N'27.0049',17600),
(1,3,N'2025-02-05',N'27.2557',N'27.7557',N'26.4688',N'26.9688',17800),
(1,3,N'2025-02-06',N'27.4301',N'27.9301',N'26.8488',N'27.3488',18000),
(1,3,N'2025-02-07',N'27.8445',N'28.5436',N'27.3445',N'28.0436',18200),
(1,3,N'2025-02-10',N'28.5456',N'29.342',N'28.0456',N'28.842',18400),
(1,3,N'2025-02-11',N'29.3752',N'29.9964',N'28.8752',N'29.4964',18600),
(1,3,N'2025-02-12',N'29.9752',N'30.4752',N'29.3098',N'29.8098',18800),
(1,3,N'2025-02-13',N'30.004',N'30.504',N'29.204',N'29.704',19000),
(1,3,N'2025-02-14',N'29.4062',N'29.9062',N'28.7475',N'29.2475',19200),
(1,3,N'2025-02-17',N'28.5027',N'29.1312',N'28.0027',N'28.6312',19400),
(1,3,N'2025-02-18',N'27.8043',N'28.6018',N'27.3043',N'28.1018',19600),
(1,3,N'2025-02-19',N'27.6826',N'28.3757',N'27.1826',N'27.8757',19800),
(1,4,N'2025-01-02',N'26.8648',N'27.5918',N'26.3648',N'27.0918',14000),
(1,4,N'2025-01-03',N'26.6099',N'27.3976',N'26.1099',N'26.8976',14200),
(1,4,N'2025-01-06',N'27.0361',N'27.6199',N'26.5361',N'27.1199',14400),
(1,4,N'2025-01-07',N'27.9096',N'28.4096',N'27.2125',N'27.7125',14600),
(1,4,N'2025-01-08',N'28.7967',N'29.2967',N'27.9999',N'28.4999',14800),
(1,4,N'2025-01-09',N'29.362',N'29.862',N'28.7384',N'29.2384',15000),
(1,4,N'2025-01-10',N'29.5383',N'30.2015',N'29.0383',N'29.7015',15200),
(1,4,N'2025-01-13',N'29.4589',N'30.2589',N'28.9589',N'29.7589',15400),
(1,4,N'2025-01-14',N'29.2609',N'29.9219',N'28.7609',N'29.4219',15600),
(1,4,N'2025-01-15',N'28.9658',N'29.4658',N'28.3397',N'28.8397',15800),
(1,4,N'2025-01-16',N'28.5444',N'29.0444',N'27.7472',N'28.2472',16000),
(1,4,N'2025-01-17',N'28.0778',N'28.5778',N'27.3827',N'27.8827',16200),
(1,4,N'2025-01-20',N'27.8186',N'28.405',N'27.3186',N'27.905',16400),
(1,4,N'2025-01-21',N'28.0494',N'28.8378',N'27.5494',N'28.3378',16600),
(1,4,N'2025-01-22',N'28.836',N'29.5613',N'28.336',N'29.0613',16800),
(1,4,N'2025-01-23',N'29.8992',N'30.3992',N'29.3542',N'29.8542',17000),
(1,4,N'2025-01-24',N'30.7449',N'31.2449',N'29.971',N'30.471',17200),
(1,4,N'2025-01-27',N'30.9786',N'31.4786',N'30.2276',N'30.7276',17400),
(1,4,N'2025-01-28',N'30.5632',N'31.0659',N'30.0632',N'30.5659',17600),
(1,4,N'2025-01-29',N'29.8198',N'30.5737',N'29.3198',N'30.0737',17800),
(1,4,N'2025-01-30',N'29.1828',N'29.9545',N'28.6828',N'29.4545',18000),
(1,4,N'2025-01-31',N'28.9163',N'29.456',N'28.4163',N'28.956',18200),
(1,4,N'2025-02-03',N'29.0125',N'29.5125',N'28.2837',N'28.7837',18400),
(1,4,N'2025-02-04',N'29.3163',N'29.8163',N'28.5294',N'29.0294',18600),
(1,4,N'2025-02-05',N'29.7198',N'30.2198',N'29.1385',N'29.6385',18800),
(1,4,N'2025-02-06',N'30.2308',N'30.9299',N'29.7308',N'30.4299',19000),
(1,4,N'2025-02-07',N'30.862',N'31.6584',N'30.362',N'31.1584',19200),
(1,4,N'2025-02-10',N'31.4798',N'32.101',N'30.9798',N'31.601',19400),
(1,4,N'2025-02-11',N'31.8',N'32.3',N'31.1346',N'31.6346',19600),
(1,4,N'2025-02-12',N'31.5788',N'32.0788',N'30.7788',N'31.2788',19800),
(1,4,N'2025-02-13',N'30.8481',N'31.3481',N'30.1894',N'30.6894',20000),
(1,4,N'2025-02-14',N'29.9752',N'30.6037',N'29.4752',N'30.1037',20200),
(1,4,N'2025-02-17',N'29.4602',N'30.2577',N'28.9602',N'29.7577',20400),
(1,4,N'2025-02-18',N'29.6107',N'30.3038',N'29.1107',N'29.8038',20600),
(1,4,N'2025-02-19',N'30.3462',N'30.8462',N'29.7573',N'30.2573',20800),
(1,5,N'2025-01-02',N'28.5616',N'29.3493',N'28.0616',N'28.8493',15000),
(1,5,N'2025-01-03',N'29.2487',N'29.8325',N'28.7487',N'29.3325',15200),
(1,5,N'2025-01-06',N'30.2774',N'30.7774',N'29.5803',N'30.0803',15400),
(1,5,N'2025-01-07',N'31.1597',N'31.6597',N'30.3629',N'30.8629',15600),
(1,5,N'2025-01-08',N'31.562',N'32.062',N'30.9384',N'31.4384',15800),
(1,5,N'2025-01-09',N'31.474',N'32.1372',N'30.974',N'31.6372',16000),
(1,5,N'2025-01-10',N'31.1213',N'31.9213',N'30.6213',N'31.4213',16200),
(1,5,N'2025-01-13',N'30.7365',N'31.3975',N'30.2365',N'30.8975',16400),
(1,5,N'2025-01-14',N'30.4063',N'30.9063',N'29.7802',N'30.2802',16600),
(1,5,N'2025-01-15',N'30.1138',N'30.6138',N'29.3166',N'29.8166',16800),
(1,5,N'2025-01-16',N'29.8951',N'30.3951',N'29.2',N'29.7',17000),
(1,5,N'2025-01-17',N'29.9162',N'30.5026',N'29.4162',N'30.0026',17200),
(1,5,N'2025-01-20',N'30.3617',N'31.1501',N'29.8617',N'30.6501',17400),
(1,5,N'2025-01-21',N'31.2225',N'31.9478',N'30.7225',N'31.4478',17600),
(1,5,N'2025-01-22',N'32.1935',N'32.6935',N'31.6485',N'32.1485',17800),
(1,5,N'2025-01-23',N'32.8126',N'33.3126',N'32.0387',N'32.5387',18000),
(1,5,N'2025-01-24',N'32.7647',N'33.2647',N'32.0137',N'32.5137',18200),
(1,5,N'2025-01-27',N'32.111',N'32.6137',N'31.611',N'32.1137',18400),
(1,5,N'2025-01-28',N'31.2558',N'32.0097',N'30.7558',N'31.5097',18600),
(1,5,N'2025-01-29',N'30.6726',N'31.4443',N'30.1726',N'30.9443',18800),
(1,5,N'2025-01-30',N'30.6066',N'31.1463',N'30.1066',N'30.6463',19000),
(1,5,N'2025-01-31',N'30.9802',N'31.4802',N'30.2514',N'30.7514',19200),
(1,5,N'2025-02-03',N'31.5411',N'32.0411',N'30.7542',N'31.2542',19400),
(1,5,N'2025-02-04',N'32.0919',N'32.5919',N'31.5106',N'32.0106',19600),
(1,5,N'2025-02-05',N'32.5886',N'33.2877',N'32.0886',N'32.7877',19800),
(1,5,N'2025-02-06',N'33.0491',N'33.8455',N'32.5491',N'33.3455',20000),
(1,5,N'2025-02-07',N'33.3995',N'34.0207',N'32.8995',N'33.5207',20200),
(1,5,N'2025-02-10',N'33.4488',N'33.9488',N'32.7834',N'33.2834',20400),
(1,5,N'2025-02-11',N'33.048',N'33.548',N'32.248',N'32.748',20600),
(1,5,N'2025-02-12',N'32.2916',N'32.7916',N'31.6329',N'32.1329',20800),
(1,5,N'2025-02-13',N'31.556',N'32.1845',N'31.056',N'31.6845',21000),
(1,5,N'2025-02-14',N'31.2934',N'32.0909',N'30.7934',N'31.5909',21200),
(1,5,N'2025-02-17',N'31.723',N'32.4161',N'31.223',N'31.9161',21400),
(1,5,N'2025-02-18',N'32.6669',N'33.1669',N'32.078',N'32.578',21600),
(1,5,N'2025-02-19',N'33.666',N'34.166',N'32.8769',N'33.3769',21800),
(1,6,N'2025-01-02',N'31.5809',N'32.1647',N'31.0809',N'31.6647',16000),
(1,6,N'2025-01-03',N'32.6609',N'33.1609',N'31.9638',N'32.4638',16200),
(1,6,N'2025-01-06',N'33.4292',N'33.9292',N'32.6324',N'33.1324',16400),
(1,6,N'2025-01-07',N'33.5919',N'34.0919',N'32.9683',N'33.4683',16600),
(1,6,N'2025-01-08',N'33.2223',N'33.8855',N'32.7223',N'33.3855',16800),
(1,6,N'2025-01-09',N'32.6445',N'33.4445',N'32.1445',N'32.9445',17000),
(1,6,N'2025-01-10',N'32.1698',N'32.8308',N'31.6698',N'32.3308',17200),
(1,6,N'2025-01-13',N'31.9163',N'32.4163',N'31.2902',N'31.7902',17400),
(1,6,N'2025-01-14',N'31.8401',N'32.3401',N'31.0429',N'31.5429',17600),
(1,6,N'2025-01-15',N'31.9019',N'32.4019',N'31.2068',N'31.7068',17800),
(1,6,N'2025-01-16',N'32.1697',N'32.7561',N'31.6697',N'32.2561',18000),
(1,6,N'2025-01-17',N'32.7419',N'33.5303',N'32.2419',N'33.0303',18200),
(1,6,N'2025-01-20',N'33.5652',N'34.2905',N'33.0652',N'33.7905',18400),
(1,6,N'2025-01-21',N'34.3474',N'34.8474',N'33.8024',N'34.3024',18600),
(1,6,N'2025-01-22',N'34.6927',N'35.1927',N'33.9188',N'34.4188',18800),
(1,6,N'2025-01-23',N'34.3813',N'34.8813',N'33.6303',N'34.1303',19000),
(1,6,N'2025-01-24',N'33.5666',N'34.0693',N'33.0666',N'33.5693',19200),
(1,6,N'2025-01-27',N'32.7092',N'33.4631',N'32.2092',N'32.9631',19400),
(1,6,N'2025-01-28',N'32.2832',N'33.0549',N'31.7832',N'32.5549',19600),
(1,6,N'2025-01-29',N'32.4791',N'33.0188',N'31.9791',N'32.5188',19800),
(1,6,N'2025-01-30',N'33.1276',N'33.6276',N'32.3988',N'32.8988',20000),
(1,6,N'2025-01-31',N'33.8805',N'34.3805',N'33.0936',N'33.5936',20200),
(1,6,N'2025-02-03',N'34.4733',N'34.9733',N'33.892',N'34.392',20400),
(1,6,N'2025-02-04',N'34.8473',N'35.5464',N'34.3473',N'35.0464',20600),
(1,6,N'2025-02-05',N'35.0634',N'35.8598',N'34.5634',N'35.3598',20800)
) v([DatasetId],[StockId],[TradeDate],[OpenPrice],[HighPrice],[LowPrice],[ClosePrice],[Volume]) WHERE NOT EXISTS(SELECT 1 FROM dbo.[DailyPrice] d WITH(UPDLOCK,HOLDLOCK) WHERE d.[DatasetId]=v.[DatasetId] AND d.[StockId]=v.[StockId] AND d.[TradeDate]=v.[TradeDate]);
 SET @Added=@Added+@@ROWCOUNT;
 IF EXISTS(SELECT 1 FROM dbo.[DailyPrice] d JOIN (VALUES
(1,6,N'2025-02-06',N'35.1328',N'35.754',N'34.6328',N'35.254',21000),
(1,6,N'2025-02-07',N'34.9629',N'35.4629',N'34.2975',N'34.7975',21200),
(1,6,N'2025-02-10',N'34.4812',N'34.9812',N'33.6812',N'34.1812',21400),
(1,6,N'2025-02-11',N'33.8105',N'34.3105',N'33.1518',N'33.6518',21600),
(1,6,N'2025-02-12',N'33.2972',N'33.9257',N'32.7972',N'33.4257',21800),
(1,6,N'2025-02-13',N'33.3158',N'34.1133',N'32.8158',N'33.6133',22000),
(1,6,N'2025-02-14',N'33.9874',N'34.6805',N'33.4874',N'34.1805',22200),
(1,6,N'2025-02-17',N'35.0495',N'35.5495',N'34.4606',N'34.9606',22400),
(1,6,N'2025-02-18',N'36.0017',N'36.5017',N'35.2126',N'35.7126',22600),
(1,6,N'2025-02-19',N'36.4286',N'36.9286',N'35.7051',N'36.2051',22800),
(1,7,N'2025-01-02',N'34.9855',N'35.4855',N'34.2884',N'34.7884',17000),
(1,7,N'2025-01-03',N'35.5483',N'36.0483',N'34.7515',N'35.2515',17200),
(1,7,N'2025-01-06',N'35.4325',N'35.9325',N'34.8089',N'35.3089',17400),
(1,7,N'2025-01-07',N'34.8087',N'35.4719',N'34.3087',N'34.9719',17600),
(1,7,N'2025-01-08',N'34.0897',N'34.8897',N'33.5897',N'34.3897',17800),
(1,7,N'2025-01-09',N'33.6362',N'34.2972',N'33.1362',N'33.7972',18000),
(1,7,N'2025-01-10',N'33.5588',N'34.0588',N'32.9327',N'33.4327',18200),
(1,7,N'2025-01-13',N'33.7522',N'34.2522',N'32.955',N'33.455',18400),
(1,7,N'2025-01-14',N'34.0829',N'34.5829',N'33.3878',N'33.8878',18600),
(1,7,N'2025-01-15',N'34.5249',N'35.1113',N'34.0249',N'34.6113',18800),
(1,7,N'2025-01-16',N'35.1158',N'35.9042',N'34.6158',N'35.4042',19000),
(1,7,N'2025-01-17',N'35.7957',N'36.521',N'35.2957',N'36.021',19200),
(1,7,N'2025-01-20',N'36.3226',N'36.8226',N'35.7776',N'36.2776',19400),
(1,7,N'2025-01-21',N'36.3898',N'36.8898',N'35.6159',N'36.1159',19600),
(1,7,N'2025-01-22',N'35.8747',N'36.3747',N'35.1237',N'35.6237',19800),
(1,7,N'2025-01-23',N'35.0018',N'35.5045',N'34.5018',N'35.0045',20000),
(1,7,N'2025-01-24',N'34.2521',N'35.006',N'33.7521',N'34.506',20200),
(1,7,N'2025-01-27',N'34.062',N'34.8337',N'33.562',N'34.3337',20400),
(1,7,N'2025-01-28',N'34.5397',N'35.0794',N'34.0397',N'34.5794',20600),
(1,7,N'2025-01-29',N'35.4173',N'35.9173',N'34.6885',N'35.1885',20800),
(1,7,N'2025-01-30',N'36.2668',N'36.7668',N'35.4799',N'35.9799',21000),
(1,7,N'2025-01-31',N'36.7897',N'37.2897',N'36.2084',N'36.7084',21200),
(1,7,N'2025-02-03',N'36.9519',N'37.651',N'36.4519',N'37.151',21400),
(1,7,N'2025-02-04',N'36.8882',N'37.6846',N'36.3882',N'37.1846',21600),
(1,7,N'2025-02-05',N'36.7076',N'37.3288',N'36.2076',N'36.8288',21800),
(1,7,N'2025-02-06',N'36.4048',N'36.9048',N'35.7394',N'36.2394',22000),
(1,7,N'2025-02-07',N'35.9537',N'36.4537',N'35.1537',N'35.6537',22200),
(1,7,N'2025-02-10',N'35.4664',N'35.9664',N'34.8077',N'35.3077',22400),
(1,7,N'2025-02-11',N'35.2253',N'35.8538',N'34.7253',N'35.3538',22600),
(1,7,N'2025-02-12',N'35.5098',N'36.3073',N'35.0098',N'35.8073',22800),
(1,7,N'2025-02-13',N'36.3481',N'37.0412',N'35.8481',N'36.5412',23000),
(1,7,N'2025-02-14',N'37.4194',N'37.9194',N'36.8305',N'37.3305',23200),
(1,7,N'2025-02-17',N'38.2202',N'38.7202',N'37.4311',N'37.9311',23400),
(1,7,N'2025-02-18',N'38.3879',N'38.8879',N'37.6644',N'38.1644',23600),
(1,7,N'2025-02-19',N'37.9329',N'38.4805',N'37.4329',N'37.9805',23800),
(1,8,N'2025-01-02',N'37.484',N'37.984',N'36.6872',N'37.1872',18000),
(1,8,N'2025-01-03',N'37.0949',N'37.5949',N'36.4713',N'36.9713',18200),
(1,8,N'2025-01-06',N'36.2843',N'36.9475',N'35.7843',N'36.4475',18400),
(1,8,N'2025-01-07',N'35.5302',N'36.3302',N'35.0302',N'35.8302',18600),
(1,8,N'2025-01-08',N'35.2056',N'35.8666',N'34.7056',N'35.3666',18800),
(1,8,N'2025-01-09',N'35.3761',N'35.8761',N'34.75',N'35.25',19000),
(1,8,N'2025-01-10',N'35.8498',N'36.3498',N'35.0526',N'35.5526',19200),
(1,8,N'2025-01-13',N'36.3952',N'36.8952',N'35.7001',N'36.2001',19400),
(1,8,N'2025-01-14',N'36.9114',N'37.4978',N'36.4114',N'36.9978',19600),
(1,8,N'2025-01-15',N'37.4101',N'38.1985',N'36.9101',N'37.6985',19800),
(1,8,N'2025-01-16',N'37.8634',N'38.5887',N'37.3634',N'38.0887',20000),
(1,8,N'2025-01-17',N'38.1087',N'38.6087',N'37.5637',N'38.0637',20200),
(1,8,N'2025-01-20',N'37.9376',N'38.4376',N'37.1637',N'37.6637',20400),
(1,8,N'2025-01-21',N'37.3107',N'37.8107',N'36.5597',N'37.0597',20600),
(1,8,N'2025-01-22',N'36.4916',N'36.9943',N'35.9916',N'36.4943',20800),
(1,8,N'2025-01-23',N'35.9424',N'36.6963',N'35.4424',N'36.1963',21000),
(1,8,N'2025-01-24',N'36.0297',N'36.8014',N'35.5297',N'36.3014',21200),
(1,8,N'2025-01-27',N'36.7645',N'37.3042',N'36.2645',N'36.8042',21400),
(1,8,N'2025-01-28',N'37.7894',N'38.2894',N'37.0606',N'37.5606',21600),
(1,8,N'2025-01-29',N'38.6246',N'39.1246',N'37.8377',N'38.3377',21800),
(1,8,N'2025-01-30',N'38.9768',N'39.4768',N'38.3955',N'38.8955',22000),
(1,8,N'2025-01-31',N'38.8716',N'39.5707',N'38.3716',N'39.0707',22200),
(1,8,N'2025-02-03',N'38.537',N'39.3334',N'38.037',N'38.8334',22400),
(1,8,N'2025-02-04',N'38.1768',N'38.798',N'37.6768',N'38.298',22600),
(1,8,N'2025-02-05',N'37.8483',N'38.3483',N'37.1829',N'37.6829',22800),
(1,8,N'2025-02-06',N'37.5345',N'38.0345',N'36.7345',N'37.2345',23000),
(1,8,N'2025-02-07',N'37.2996',N'37.7996',N'36.6409',N'37.1409',23200),
(1,8,N'2025-02-10',N'37.3376',N'37.9661',N'36.8376',N'37.4661',23400),
(1,8,N'2025-02-11',N'37.8305',N'38.628',N'37.3305',N'38.128',23600),
(1,8,N'2025-02-12',N'38.7338',N'39.4269',N'38.2338',N'38.9269',23800),
(1,8,N'2025-02-13',N'39.704',N'40.204',N'39.1151',N'39.6151',24000),
(1,8,N'2025-02-14',N'40.2727',N'40.7727',N'39.4836',N'39.9836',24200),
(1,8,N'2025-02-17',N'40.1586',N'40.6586',N'39.4351',N'39.9351',24400),
(1,8,N'2025-02-18',N'39.4705',N'40.0181',N'38.9705',N'39.5181',24600),
(1,8,N'2025-02-19',N'38.6346',N'39.4096',N'38.1346',N'38.9096',24800)
) v([DatasetId],[StockId],[TradeDate],[OpenPrice],[HighPrice],[LowPrice],[ClosePrice],[Volume]) ON d.[DatasetId]=v.[DatasetId] AND d.[StockId]=v.[StockId] AND d.[TradeDate]=v.[TradeDate] WHERE EXISTS(SELECT d.[DatasetId],d.[StockId],d.[TradeDate],d.[OpenPrice],d.[HighPrice],d.[LowPrice],d.[ClosePrice],d.[Volume] EXCEPT SELECT v.[DatasetId],v.[StockId],v.[TradeDate],v.[OpenPrice],v.[HighPrice],v.[LowPrice],v.[ClosePrice],v.[Volume])) THROW 51100,N'Import conflict: DailyPrice',1;
 INSERT dbo.[DailyPrice]([DatasetId],[StockId],[TradeDate],[OpenPrice],[HighPrice],[LowPrice],[ClosePrice],[Volume]) SELECT v.[DatasetId],v.[StockId],v.[TradeDate],v.[OpenPrice],v.[HighPrice],v.[LowPrice],v.[ClosePrice],v.[Volume] FROM (VALUES
(1,6,N'2025-02-06',N'35.1328',N'35.754',N'34.6328',N'35.254',21000),
(1,6,N'2025-02-07',N'34.9629',N'35.4629',N'34.2975',N'34.7975',21200),
(1,6,N'2025-02-10',N'34.4812',N'34.9812',N'33.6812',N'34.1812',21400),
(1,6,N'2025-02-11',N'33.8105',N'34.3105',N'33.1518',N'33.6518',21600),
(1,6,N'2025-02-12',N'33.2972',N'33.9257',N'32.7972',N'33.4257',21800),
(1,6,N'2025-02-13',N'33.3158',N'34.1133',N'32.8158',N'33.6133',22000),
(1,6,N'2025-02-14',N'33.9874',N'34.6805',N'33.4874',N'34.1805',22200),
(1,6,N'2025-02-17',N'35.0495',N'35.5495',N'34.4606',N'34.9606',22400),
(1,6,N'2025-02-18',N'36.0017',N'36.5017',N'35.2126',N'35.7126',22600),
(1,6,N'2025-02-19',N'36.4286',N'36.9286',N'35.7051',N'36.2051',22800),
(1,7,N'2025-01-02',N'34.9855',N'35.4855',N'34.2884',N'34.7884',17000),
(1,7,N'2025-01-03',N'35.5483',N'36.0483',N'34.7515',N'35.2515',17200),
(1,7,N'2025-01-06',N'35.4325',N'35.9325',N'34.8089',N'35.3089',17400),
(1,7,N'2025-01-07',N'34.8087',N'35.4719',N'34.3087',N'34.9719',17600),
(1,7,N'2025-01-08',N'34.0897',N'34.8897',N'33.5897',N'34.3897',17800),
(1,7,N'2025-01-09',N'33.6362',N'34.2972',N'33.1362',N'33.7972',18000),
(1,7,N'2025-01-10',N'33.5588',N'34.0588',N'32.9327',N'33.4327',18200),
(1,7,N'2025-01-13',N'33.7522',N'34.2522',N'32.955',N'33.455',18400),
(1,7,N'2025-01-14',N'34.0829',N'34.5829',N'33.3878',N'33.8878',18600),
(1,7,N'2025-01-15',N'34.5249',N'35.1113',N'34.0249',N'34.6113',18800),
(1,7,N'2025-01-16',N'35.1158',N'35.9042',N'34.6158',N'35.4042',19000),
(1,7,N'2025-01-17',N'35.7957',N'36.521',N'35.2957',N'36.021',19200),
(1,7,N'2025-01-20',N'36.3226',N'36.8226',N'35.7776',N'36.2776',19400),
(1,7,N'2025-01-21',N'36.3898',N'36.8898',N'35.6159',N'36.1159',19600),
(1,7,N'2025-01-22',N'35.8747',N'36.3747',N'35.1237',N'35.6237',19800),
(1,7,N'2025-01-23',N'35.0018',N'35.5045',N'34.5018',N'35.0045',20000),
(1,7,N'2025-01-24',N'34.2521',N'35.006',N'33.7521',N'34.506',20200),
(1,7,N'2025-01-27',N'34.062',N'34.8337',N'33.562',N'34.3337',20400),
(1,7,N'2025-01-28',N'34.5397',N'35.0794',N'34.0397',N'34.5794',20600),
(1,7,N'2025-01-29',N'35.4173',N'35.9173',N'34.6885',N'35.1885',20800),
(1,7,N'2025-01-30',N'36.2668',N'36.7668',N'35.4799',N'35.9799',21000),
(1,7,N'2025-01-31',N'36.7897',N'37.2897',N'36.2084',N'36.7084',21200),
(1,7,N'2025-02-03',N'36.9519',N'37.651',N'36.4519',N'37.151',21400),
(1,7,N'2025-02-04',N'36.8882',N'37.6846',N'36.3882',N'37.1846',21600),
(1,7,N'2025-02-05',N'36.7076',N'37.3288',N'36.2076',N'36.8288',21800),
(1,7,N'2025-02-06',N'36.4048',N'36.9048',N'35.7394',N'36.2394',22000),
(1,7,N'2025-02-07',N'35.9537',N'36.4537',N'35.1537',N'35.6537',22200),
(1,7,N'2025-02-10',N'35.4664',N'35.9664',N'34.8077',N'35.3077',22400),
(1,7,N'2025-02-11',N'35.2253',N'35.8538',N'34.7253',N'35.3538',22600),
(1,7,N'2025-02-12',N'35.5098',N'36.3073',N'35.0098',N'35.8073',22800),
(1,7,N'2025-02-13',N'36.3481',N'37.0412',N'35.8481',N'36.5412',23000),
(1,7,N'2025-02-14',N'37.4194',N'37.9194',N'36.8305',N'37.3305',23200),
(1,7,N'2025-02-17',N'38.2202',N'38.7202',N'37.4311',N'37.9311',23400),
(1,7,N'2025-02-18',N'38.3879',N'38.8879',N'37.6644',N'38.1644',23600),
(1,7,N'2025-02-19',N'37.9329',N'38.4805',N'37.4329',N'37.9805',23800),
(1,8,N'2025-01-02',N'37.484',N'37.984',N'36.6872',N'37.1872',18000),
(1,8,N'2025-01-03',N'37.0949',N'37.5949',N'36.4713',N'36.9713',18200),
(1,8,N'2025-01-06',N'36.2843',N'36.9475',N'35.7843',N'36.4475',18400),
(1,8,N'2025-01-07',N'35.5302',N'36.3302',N'35.0302',N'35.8302',18600),
(1,8,N'2025-01-08',N'35.2056',N'35.8666',N'34.7056',N'35.3666',18800),
(1,8,N'2025-01-09',N'35.3761',N'35.8761',N'34.75',N'35.25',19000),
(1,8,N'2025-01-10',N'35.8498',N'36.3498',N'35.0526',N'35.5526',19200),
(1,8,N'2025-01-13',N'36.3952',N'36.8952',N'35.7001',N'36.2001',19400),
(1,8,N'2025-01-14',N'36.9114',N'37.4978',N'36.4114',N'36.9978',19600),
(1,8,N'2025-01-15',N'37.4101',N'38.1985',N'36.9101',N'37.6985',19800),
(1,8,N'2025-01-16',N'37.8634',N'38.5887',N'37.3634',N'38.0887',20000),
(1,8,N'2025-01-17',N'38.1087',N'38.6087',N'37.5637',N'38.0637',20200),
(1,8,N'2025-01-20',N'37.9376',N'38.4376',N'37.1637',N'37.6637',20400),
(1,8,N'2025-01-21',N'37.3107',N'37.8107',N'36.5597',N'37.0597',20600),
(1,8,N'2025-01-22',N'36.4916',N'36.9943',N'35.9916',N'36.4943',20800),
(1,8,N'2025-01-23',N'35.9424',N'36.6963',N'35.4424',N'36.1963',21000),
(1,8,N'2025-01-24',N'36.0297',N'36.8014',N'35.5297',N'36.3014',21200),
(1,8,N'2025-01-27',N'36.7645',N'37.3042',N'36.2645',N'36.8042',21400),
(1,8,N'2025-01-28',N'37.7894',N'38.2894',N'37.0606',N'37.5606',21600),
(1,8,N'2025-01-29',N'38.6246',N'39.1246',N'37.8377',N'38.3377',21800),
(1,8,N'2025-01-30',N'38.9768',N'39.4768',N'38.3955',N'38.8955',22000),
(1,8,N'2025-01-31',N'38.8716',N'39.5707',N'38.3716',N'39.0707',22200),
(1,8,N'2025-02-03',N'38.537',N'39.3334',N'38.037',N'38.8334',22400),
(1,8,N'2025-02-04',N'38.1768',N'38.798',N'37.6768',N'38.298',22600),
(1,8,N'2025-02-05',N'37.8483',N'38.3483',N'37.1829',N'37.6829',22800),
(1,8,N'2025-02-06',N'37.5345',N'38.0345',N'36.7345',N'37.2345',23000),
(1,8,N'2025-02-07',N'37.2996',N'37.7996',N'36.6409',N'37.1409',23200),
(1,8,N'2025-02-10',N'37.3376',N'37.9661',N'36.8376',N'37.4661',23400),
(1,8,N'2025-02-11',N'37.8305',N'38.628',N'37.3305',N'38.128',23600),
(1,8,N'2025-02-12',N'38.7338',N'39.4269',N'38.2338',N'38.9269',23800),
(1,8,N'2025-02-13',N'39.704',N'40.204',N'39.1151',N'39.6151',24000),
(1,8,N'2025-02-14',N'40.2727',N'40.7727',N'39.4836',N'39.9836',24200),
(1,8,N'2025-02-17',N'40.1586',N'40.6586',N'39.4351',N'39.9351',24400),
(1,8,N'2025-02-18',N'39.4705',N'40.0181',N'38.9705',N'39.5181',24600),
(1,8,N'2025-02-19',N'38.6346',N'39.4096',N'38.1346',N'38.9096',24800)
) v([DatasetId],[StockId],[TradeDate],[OpenPrice],[HighPrice],[LowPrice],[ClosePrice],[Volume]) WHERE NOT EXISTS(SELECT 1 FROM dbo.[DailyPrice] d WITH(UPDLOCK,HOLDLOCK) WHERE d.[DatasetId]=v.[DatasetId] AND d.[StockId]=v.[StockId] AND d.[TradeDate]=v.[TradeDate]);
 SET @Added=@Added+@@ROWCOUNT;
 INSERT #ImportReceipt VALUES(N'DailyPrice',280,@Added);
 SET @Added=0;
 IF EXISTS(SELECT 1 FROM dbo.[StockIndex] d JOIN (VALUES
(1,1,N'DEMO8',N'Chỉ số mô phỏng 8 mã')
) v([IndexId],[MarketId],[IndexCode],[IndexName]) ON d.[IndexId]=v.[IndexId] WHERE EXISTS(SELECT d.[IndexId],d.[MarketId],d.[IndexCode],d.[IndexName] EXCEPT SELECT v.[IndexId],v.[MarketId],v.[IndexCode],v.[IndexName])) THROW 51100,N'Import conflict: StockIndex',1;
 INSERT dbo.[StockIndex]([IndexId],[MarketId],[IndexCode],[IndexName]) SELECT v.[IndexId],v.[MarketId],v.[IndexCode],v.[IndexName] FROM (VALUES
(1,1,N'DEMO8',N'Chỉ số mô phỏng 8 mã')
) v([IndexId],[MarketId],[IndexCode],[IndexName]) WHERE NOT EXISTS(SELECT 1 FROM dbo.[StockIndex] d WITH(UPDLOCK,HOLDLOCK) WHERE d.[IndexId]=v.[IndexId]);
 SET @Added=@Added+@@ROWCOUNT;
 INSERT #ImportReceipt VALUES(N'StockIndex',1,@Added);
 SET @Added=0;
 IF EXISTS(SELECT 1 FROM dbo.[IndexMembership] d JOIN (VALUES
(1,1,N'2025-01-02',N'2025-02-28',N'Khoảng hiệu lực mô phỏng'),
(1,2,N'2025-01-02',N'2025-02-28',N'Khoảng hiệu lực mô phỏng'),
(1,3,N'2025-01-02',N'2025-02-28',N'Khoảng hiệu lực mô phỏng'),
(1,4,N'2025-01-02',N'2025-02-28',N'Khoảng hiệu lực mô phỏng'),
(1,5,N'2025-01-02',N'2025-02-28',N'Khoảng hiệu lực mô phỏng'),
(1,6,N'2025-01-02',N'2025-02-28',N'Khoảng hiệu lực mô phỏng'),
(1,7,N'2025-01-02',N'2025-02-28',N'Khoảng hiệu lực mô phỏng'),
(1,8,N'2025-01-02',N'2025-02-28',N'Khoảng hiệu lực mô phỏng')
) v([IndexId],[StockId],[ValidFrom],[ValidTo],[EvidenceNote]) ON d.[IndexId]=v.[IndexId] AND d.[StockId]=v.[StockId] AND d.[ValidFrom]=v.[ValidFrom] WHERE EXISTS(SELECT d.[IndexId],d.[StockId],d.[ValidFrom],d.[ValidTo],d.[EvidenceNote] EXCEPT SELECT v.[IndexId],v.[StockId],v.[ValidFrom],v.[ValidTo],v.[EvidenceNote])) THROW 51100,N'Import conflict: IndexMembership',1;
 INSERT dbo.[IndexMembership]([IndexId],[StockId],[ValidFrom],[ValidTo],[EvidenceNote]) SELECT v.[IndexId],v.[StockId],v.[ValidFrom],v.[ValidTo],v.[EvidenceNote] FROM (VALUES
(1,1,N'2025-01-02',N'2025-02-28',N'Khoảng hiệu lực mô phỏng'),
(1,2,N'2025-01-02',N'2025-02-28',N'Khoảng hiệu lực mô phỏng'),
(1,3,N'2025-01-02',N'2025-02-28',N'Khoảng hiệu lực mô phỏng'),
(1,4,N'2025-01-02',N'2025-02-28',N'Khoảng hiệu lực mô phỏng'),
(1,5,N'2025-01-02',N'2025-02-28',N'Khoảng hiệu lực mô phỏng'),
(1,6,N'2025-01-02',N'2025-02-28',N'Khoảng hiệu lực mô phỏng'),
(1,7,N'2025-01-02',N'2025-02-28',N'Khoảng hiệu lực mô phỏng'),
(1,8,N'2025-01-02',N'2025-02-28',N'Khoảng hiệu lực mô phỏng')
) v([IndexId],[StockId],[ValidFrom],[ValidTo],[EvidenceNote]) WHERE NOT EXISTS(SELECT 1 FROM dbo.[IndexMembership] d WITH(UPDLOCK,HOLDLOCK) WHERE d.[IndexId]=v.[IndexId] AND d.[StockId]=v.[StockId] AND d.[ValidFrom]=v.[ValidFrom]);
 SET @Added=@Added+@@ROWCOUNT;
 INSERT #ImportReceipt VALUES(N'IndexMembership',8,@Added);
 SET @Added=0;
 IF EXISTS(SELECT 1 FROM dbo.[ForecastModel] d JOIN (VALUES
(1,N'demo_baseline',N'Baseline mô phỏng',N'Mô phỏng phục vụ kiểm thử'),
(2,N'demo_model_b',N'Mô hình B mô phỏng',N'Mô phỏng phục vụ kiểm thử')
) v([ModelId],[ModelCode],[ModelName],[MethodNote]) ON d.[ModelId]=v.[ModelId] WHERE EXISTS(SELECT d.[ModelId],d.[ModelCode],d.[ModelName],d.[MethodNote] EXCEPT SELECT v.[ModelId],v.[ModelCode],v.[ModelName],v.[MethodNote])) THROW 51100,N'Import conflict: ForecastModel',1;
 INSERT dbo.[ForecastModel]([ModelId],[ModelCode],[ModelName],[MethodNote]) SELECT v.[ModelId],v.[ModelCode],v.[ModelName],v.[MethodNote] FROM (VALUES
(1,N'demo_baseline',N'Baseline mô phỏng',N'Mô phỏng phục vụ kiểm thử'),
(2,N'demo_model_b',N'Mô hình B mô phỏng',N'Mô phỏng phục vụ kiểm thử')
) v([ModelId],[ModelCode],[ModelName],[MethodNote]) WHERE NOT EXISTS(SELECT 1 FROM dbo.[ForecastModel] d WITH(UPDLOCK,HOLDLOCK) WHERE d.[ModelId]=v.[ModelId]);
 SET @Added=@Added+@@ROWCOUNT;
 INSERT #ImportReceipt VALUES(N'ForecastModel',2,@Added);
 SET @Added=0;
 IF EXISTS(SELECT 1 FROM dbo.[TargetDefinition] d JOIN (VALUES
(1,N'CLOSE_UP_5',5,N'PROBABILITY_CLOSE_UP',N'CLOSE_TARGET_GT_CLOSE_ORIGIN_ELSE_ZERO')
) v([TargetId],[TargetCode],[HorizonSessions],[OutputType],[LabelRule]) ON d.[TargetId]=v.[TargetId] WHERE EXISTS(SELECT d.[TargetId],d.[TargetCode],d.[HorizonSessions],d.[OutputType],d.[LabelRule] EXCEPT SELECT v.[TargetId],v.[TargetCode],v.[HorizonSessions],v.[OutputType],v.[LabelRule])) THROW 51100,N'Import conflict: TargetDefinition',1;
 INSERT dbo.[TargetDefinition]([TargetId],[TargetCode],[HorizonSessions],[OutputType],[LabelRule]) SELECT v.[TargetId],v.[TargetCode],v.[HorizonSessions],v.[OutputType],v.[LabelRule] FROM (VALUES
(1,N'CLOSE_UP_5',5,N'PROBABILITY_CLOSE_UP',N'CLOSE_TARGET_GT_CLOSE_ORIGIN_ELSE_ZERO')
) v([TargetId],[TargetCode],[HorizonSessions],[OutputType],[LabelRule]) WHERE NOT EXISTS(SELECT 1 FROM dbo.[TargetDefinition] d WITH(UPDLOCK,HOLDLOCK) WHERE d.[TargetId]=v.[TargetId]);
 SET @Added=@Added+@@ROWCOUNT;
 INSERT #ImportReceipt VALUES(N'TargetDefinition',1,@Added);
 SET @Added=0;
 IF EXISTS(SELECT 1 FROM dbo.[ModelRun] d JOIN (VALUES
(1,N'DEMO_MODEL1_H5',1,1,1,N'2022-01-01',N'2023-12-31',N'2024-12-31',NULL,N'0.5',N'SYNTHETIC_TEST',N'generated deterministic synthetic fixture',NULL),
(2,N'DEMO_MODEL2_H5',2,1,1,N'2022-01-01',N'2023-12-31',N'2024-12-31',NULL,N'0.5',N'SYNTHETIC_TEST',N'generated deterministic synthetic fixture',NULL)
) v([RunId],[RunCode],[ModelId],[DatasetId],[TargetId],[TrainStart],[TrainEnd],[ValidationEnd],[SelectedC],[Threshold],[EvaluationClass],[SourceRun],[CompletedAt]) ON d.[RunId]=v.[RunId] WHERE EXISTS(SELECT d.[RunId],d.[RunCode],d.[ModelId],d.[DatasetId],d.[TargetId],d.[TrainStart],d.[TrainEnd],d.[ValidationEnd],d.[SelectedC],d.[Threshold],d.[EvaluationClass],d.[SourceRun],d.[CompletedAt] EXCEPT SELECT v.[RunId],v.[RunCode],v.[ModelId],v.[DatasetId],v.[TargetId],v.[TrainStart],v.[TrainEnd],v.[ValidationEnd],v.[SelectedC],v.[Threshold],v.[EvaluationClass],v.[SourceRun],v.[CompletedAt])) THROW 51100,N'Import conflict: ModelRun',1;
 INSERT dbo.[ModelRun]([RunId],[RunCode],[ModelId],[DatasetId],[TargetId],[TrainStart],[TrainEnd],[ValidationEnd],[SelectedC],[Threshold],[EvaluationClass],[SourceRun],[CompletedAt]) SELECT v.[RunId],v.[RunCode],v.[ModelId],v.[DatasetId],v.[TargetId],v.[TrainStart],v.[TrainEnd],v.[ValidationEnd],v.[SelectedC],v.[Threshold],v.[EvaluationClass],v.[SourceRun],v.[CompletedAt] FROM (VALUES
(1,N'DEMO_MODEL1_H5',1,1,1,N'2022-01-01',N'2023-12-31',N'2024-12-31',NULL,N'0.5',N'SYNTHETIC_TEST',N'generated deterministic synthetic fixture',NULL),
(2,N'DEMO_MODEL2_H5',2,1,1,N'2022-01-01',N'2023-12-31',N'2024-12-31',NULL,N'0.5',N'SYNTHETIC_TEST',N'generated deterministic synthetic fixture',NULL)
) v([RunId],[RunCode],[ModelId],[DatasetId],[TargetId],[TrainStart],[TrainEnd],[ValidationEnd],[SelectedC],[Threshold],[EvaluationClass],[SourceRun],[CompletedAt]) WHERE NOT EXISTS(SELECT 1 FROM dbo.[ModelRun] d WITH(UPDLOCK,HOLDLOCK) WHERE d.[RunId]=v.[RunId]);
 SET @Added=@Added+@@ROWCOUNT;
 INSERT #ImportReceipt VALUES(N'ModelRun',2,@Added);
 SET @Added=0;
 IF EXISTS(SELECT 1 FROM dbo.[ForecastOrigin] d JOIN (VALUES
(1,N'2025-01-02',N'2025-01-09'),
(1,N'2025-01-03',N'2025-01-10'),
(1,N'2025-01-06',N'2025-01-13'),
(1,N'2025-01-07',N'2025-01-14'),
(1,N'2025-01-08',N'2025-01-15'),
(1,N'2025-01-09',N'2025-01-16'),
(1,N'2025-01-10',N'2025-01-17'),
(1,N'2025-01-13',N'2025-01-20'),
(1,N'2025-01-14',N'2025-01-21'),
(1,N'2025-01-15',N'2025-01-22'),
(1,N'2025-01-16',N'2025-01-23'),
(1,N'2025-01-17',N'2025-01-24'),
(1,N'2025-01-20',N'2025-01-27'),
(1,N'2025-01-21',N'2025-01-28'),
(1,N'2025-01-22',N'2025-01-29'),
(1,N'2025-01-23',N'2025-01-30'),
(1,N'2025-02-17',N'2025-02-24'),
(2,N'2025-01-02',N'2025-01-09'),
(2,N'2025-01-03',N'2025-01-10'),
(2,N'2025-01-06',N'2025-01-13'),
(2,N'2025-01-07',N'2025-01-14'),
(2,N'2025-01-08',N'2025-01-15'),
(2,N'2025-01-09',N'2025-01-16'),
(2,N'2025-01-10',N'2025-01-17'),
(2,N'2025-01-13',N'2025-01-20'),
(2,N'2025-01-14',N'2025-01-21'),
(2,N'2025-01-15',N'2025-01-22'),
(2,N'2025-01-16',N'2025-01-23'),
(2,N'2025-01-17',N'2025-01-24'),
(2,N'2025-01-20',N'2025-01-27'),
(2,N'2025-01-21',N'2025-01-28'),
(2,N'2025-01-22',N'2025-01-29'),
(2,N'2025-01-23',N'2025-01-30'),
(2,N'2025-02-17',N'2025-02-24')
) v([RunId],[OriginDate],[TargetDate]) ON d.[RunId]=v.[RunId] AND d.[OriginDate]=v.[OriginDate] WHERE EXISTS(SELECT d.[RunId],d.[OriginDate],d.[TargetDate] EXCEPT SELECT v.[RunId],v.[OriginDate],v.[TargetDate])) THROW 51100,N'Import conflict: ForecastOrigin',1;
 INSERT dbo.[ForecastOrigin]([RunId],[OriginDate],[TargetDate]) SELECT v.[RunId],v.[OriginDate],v.[TargetDate] FROM (VALUES
(1,N'2025-01-02',N'2025-01-09'),
(1,N'2025-01-03',N'2025-01-10'),
(1,N'2025-01-06',N'2025-01-13'),
(1,N'2025-01-07',N'2025-01-14'),
(1,N'2025-01-08',N'2025-01-15'),
(1,N'2025-01-09',N'2025-01-16'),
(1,N'2025-01-10',N'2025-01-17'),
(1,N'2025-01-13',N'2025-01-20'),
(1,N'2025-01-14',N'2025-01-21'),
(1,N'2025-01-15',N'2025-01-22'),
(1,N'2025-01-16',N'2025-01-23'),
(1,N'2025-01-17',N'2025-01-24'),
(1,N'2025-01-20',N'2025-01-27'),
(1,N'2025-01-21',N'2025-01-28'),
(1,N'2025-01-22',N'2025-01-29'),
(1,N'2025-01-23',N'2025-01-30'),
(1,N'2025-02-17',N'2025-02-24'),
(2,N'2025-01-02',N'2025-01-09'),
(2,N'2025-01-03',N'2025-01-10'),
(2,N'2025-01-06',N'2025-01-13'),
(2,N'2025-01-07',N'2025-01-14'),
(2,N'2025-01-08',N'2025-01-15'),
(2,N'2025-01-09',N'2025-01-16'),
(2,N'2025-01-10',N'2025-01-17'),
(2,N'2025-01-13',N'2025-01-20'),
(2,N'2025-01-14',N'2025-01-21'),
(2,N'2025-01-15',N'2025-01-22'),
(2,N'2025-01-16',N'2025-01-23'),
(2,N'2025-01-17',N'2025-01-24'),
(2,N'2025-01-20',N'2025-01-27'),
(2,N'2025-01-21',N'2025-01-28'),
(2,N'2025-01-22',N'2025-01-29'),
(2,N'2025-01-23',N'2025-01-30'),
(2,N'2025-02-17',N'2025-02-24')
) v([RunId],[OriginDate],[TargetDate]) WHERE NOT EXISTS(SELECT 1 FROM dbo.[ForecastOrigin] d WITH(UPDLOCK,HOLDLOCK) WHERE d.[RunId]=v.[RunId] AND d.[OriginDate]=v.[OriginDate]);
 SET @Added=@Added+@@ROWCOUNT;
 INSERT #ImportReceipt VALUES(N'ForecastOrigin',34,@Added);
 SET @Added=0;
 IF EXISTS(SELECT 1 FROM dbo.[Prediction] d JOIN (VALUES
(1,1,N'2025-01-02',N'0.5'),
(1,1,N'2025-01-03',N'0.5'),
(1,1,N'2025-01-06',N'0.5'),
(1,1,N'2025-01-07',N'0.5'),
(1,1,N'2025-01-08',N'0.5'),
(1,1,N'2025-01-09',N'0.5'),
(1,1,N'2025-01-10',N'0.5'),
(1,1,N'2025-01-13',N'0.5'),
(1,1,N'2025-01-14',N'0.5'),
(1,1,N'2025-01-15',N'0.5'),
(1,1,N'2025-01-16',N'0.5'),
(1,1,N'2025-01-17',N'0.5'),
(1,1,N'2025-01-20',N'0.5'),
(1,1,N'2025-01-21',N'0.5'),
(1,1,N'2025-01-22',N'0.5'),
(1,1,N'2025-01-23',N'0.5'),
(2,1,N'2025-01-02',N'0.73561188'),
(2,1,N'2025-01-03',N'0.7792986'),
(2,1,N'2025-01-06',N'0.75460328'),
(2,1,N'2025-01-07',N'0.6675722'),
(2,1,N'2025-01-08',N'0.5395136'),
(2,1,N'2025-01-09',N'0.4017807'),
(2,1,N'2025-01-10',N'0.2880953'),
(2,1,N'2025-01-13',N'0.22629157'),
(2,1,N'2025-01-14',N'0.2315012'),
(2,1,N'2025-01-15',N'0.30244871'),
(2,1,N'2025-01-16',N'0.42176366'),
(2,1,N'2025-01-17',N'0.5602336'),
(2,1,N'2025-01-20',N'0.68395625'),
(2,1,N'2025-01-21',N'0.76263999'),
(2,1,N'2025-01-22',N'0.77702031'),
(2,1,N'2025-01-23',N'0.72357639'),
(1,2,N'2025-01-02',N'0.5'),
(1,2,N'2025-01-03',N'0.5'),
(1,2,N'2025-01-06',N'0.5'),
(1,2,N'2025-01-07',N'0.5'),
(1,2,N'2025-01-08',N'0.5'),
(1,2,N'2025-01-09',N'0.5'),
(1,2,N'2025-01-10',N'0.5'),
(1,2,N'2025-01-13',N'0.5'),
(1,2,N'2025-01-14',N'0.5'),
(1,2,N'2025-01-15',N'0.5'),
(1,2,N'2025-01-16',N'0.5'),
(1,2,N'2025-01-17',N'0.5'),
(1,2,N'2025-01-20',N'0.5'),
(1,2,N'2025-01-21',N'0.5'),
(1,2,N'2025-01-22',N'0.5'),
(1,2,N'2025-01-23',N'0.5'),
(2,2,N'2025-01-02',N'0.75460328'),
(2,2,N'2025-01-03',N'0.6675722'),
(2,2,N'2025-01-06',N'0.5395136'),
(2,2,N'2025-01-07',N'0.4017807'),
(2,2,N'2025-01-08',N'0.2880953'),
(2,2,N'2025-01-09',N'0.22629157'),
(2,2,N'2025-01-10',N'0.2315012'),
(2,2,N'2025-01-13',N'0.30244871'),
(2,2,N'2025-01-14',N'0.42176366'),
(2,2,N'2025-01-15',N'0.5602336'),
(2,2,N'2025-01-16',N'0.68395625'),
(2,2,N'2025-01-17',N'0.76263999'),
(2,2,N'2025-01-20',N'0.77702031'),
(2,2,N'2025-01-21',N'0.72357639'),
(2,2,N'2025-01-22',N'0.61539318'),
(2,2,N'2025-01-23',N'0.47895769'),
(1,3,N'2025-01-02',N'0.5'),
(1,3,N'2025-01-03',N'0.5'),
(1,3,N'2025-01-06',N'0.5'),
(1,3,N'2025-01-07',N'0.5'),
(1,3,N'2025-01-08',N'0.5'),
(1,3,N'2025-01-09',N'0.5'),
(1,3,N'2025-01-10',N'0.5'),
(1,3,N'2025-01-13',N'0.5'),
(1,3,N'2025-01-14',N'0.5'),
(1,3,N'2025-01-15',N'0.5'),
(1,3,N'2025-01-16',N'0.5'),
(1,3,N'2025-01-17',N'0.5'),
(1,3,N'2025-01-20',N'0.5'),
(1,3,N'2025-01-21',N'0.5'),
(1,3,N'2025-01-22',N'0.5'),
(1,3,N'2025-01-23',N'0.5'),
(2,3,N'2025-01-02',N'0.5395136'),
(2,3,N'2025-01-03',N'0.4017807'),
(2,3,N'2025-01-06',N'0.2880953'),
(2,3,N'2025-01-07',N'0.22629157'),
(2,3,N'2025-01-08',N'0.2315012'),
(2,3,N'2025-01-09',N'0.30244871'),
(2,3,N'2025-01-10',N'0.42176366'),
(2,3,N'2025-01-13',N'0.5602336'),
(2,3,N'2025-01-14',N'0.68395625'),
(2,3,N'2025-01-15',N'0.76263999'),
(2,3,N'2025-01-16',N'0.77702031'),
(2,3,N'2025-01-17',N'0.72357639'),
(2,3,N'2025-01-20',N'0.61539318'),
(2,3,N'2025-01-21',N'0.47895769'),
(2,3,N'2025-01-22',N'0.34767409'),
(2,3,N'2025-01-23',N'0.25368519'),
(1,4,N'2025-01-02',N'0.5'),
(1,4,N'2025-01-03',N'0.5'),
(1,4,N'2025-01-06',N'0.5'),
(1,4,N'2025-01-07',N'0.5'),
(1,4,N'2025-01-08',N'0.5'),
(1,4,N'2025-01-09',N'0.5'),
(1,4,N'2025-01-10',N'0.5'),
(1,4,N'2025-01-13',N'0.5'),
(1,4,N'2025-01-14',N'0.5'),
(1,4,N'2025-01-15',N'0.5'),
(1,4,N'2025-01-16',N'0.5'),
(1,4,N'2025-01-17',N'0.5'),
(1,4,N'2025-01-20',N'0.5'),
(1,4,N'2025-01-21',N'0.5'),
(1,4,N'2025-01-22',N'0.5'),
(1,4,N'2025-01-23',N'0.5'),
(2,4,N'2025-01-02',N'0.2880953'),
(2,4,N'2025-01-03',N'0.22629157'),
(2,4,N'2025-01-06',N'0.2315012'),
(2,4,N'2025-01-07',N'0.30244871'),
(2,4,N'2025-01-08',N'0.42176366'),
(2,4,N'2025-01-09',N'0.5602336'),
(2,4,N'2025-01-10',N'0.68395625'),
(2,4,N'2025-01-13',N'0.76263999'),
(2,4,N'2025-01-14',N'0.77702031'),
(2,4,N'2025-01-15',N'0.72357639'),
(2,4,N'2025-01-16',N'0.61539318'),
(2,4,N'2025-01-17',N'0.47895769'),
(2,4,N'2025-01-20',N'0.34767409'),
(2,4,N'2025-01-21',N'0.25368519'),
(2,4,N'2025-01-22',N'0.22000274'),
(2,4,N'2025-01-23',N'0.25487339'),
(1,5,N'2025-01-02',N'0.5'),
(1,5,N'2025-01-03',N'0.5'),
(1,5,N'2025-01-06',N'0.5'),
(1,5,N'2025-01-07',N'0.5'),
(1,5,N'2025-01-08',N'0.5'),
(1,5,N'2025-01-09',N'0.5'),
(1,5,N'2025-01-10',N'0.5'),
(1,5,N'2025-01-13',N'0.5'),
(1,5,N'2025-01-14',N'0.5'),
(1,5,N'2025-01-15',N'0.5'),
(1,5,N'2025-01-16',N'0.5'),
(1,5,N'2025-01-17',N'0.5'),
(1,5,N'2025-01-20',N'0.5'),
(1,5,N'2025-01-21',N'0.5'),
(1,5,N'2025-01-22',N'0.5'),
(1,5,N'2025-01-23',N'0.5'),
(2,5,N'2025-01-02',N'0.2315012'),
(2,5,N'2025-01-03',N'0.30244871'),
(2,5,N'2025-01-06',N'0.42176366'),
(2,5,N'2025-01-07',N'0.5602336'),
(2,5,N'2025-01-08',N'0.68395625'),
(2,5,N'2025-01-09',N'0.76263999'),
(2,5,N'2025-01-10',N'0.77702031'),
(2,5,N'2025-01-13',N'0.72357639'),
(2,5,N'2025-01-14',N'0.61539318'),
(2,5,N'2025-01-15',N'0.47895769'),
(2,5,N'2025-01-16',N'0.34767409'),
(2,5,N'2025-01-17',N'0.25368519'),
(2,5,N'2025-01-20',N'0.22000274'),
(2,5,N'2025-01-21',N'0.25487339'),
(2,5,N'2025-01-22',N'0.34975958'),
(2,5,N'2025-01-23',N'0.48142987'),
(1,6,N'2025-01-02',N'0.5'),
(1,6,N'2025-01-03',N'0.5'),
(1,6,N'2025-01-06',N'0.5'),
(1,6,N'2025-01-07',N'0.5'),
(1,6,N'2025-01-08',N'0.5'),
(1,6,N'2025-01-09',N'0.5'),
(1,6,N'2025-01-10',N'0.5'),
(1,6,N'2025-01-13',N'0.5'),
(1,6,N'2025-01-14',N'0.5'),
(1,6,N'2025-01-15',N'0.5'),
(1,6,N'2025-01-16',N'0.5'),
(1,6,N'2025-01-17',N'0.5'),
(1,6,N'2025-01-20',N'0.5'),
(1,6,N'2025-01-21',N'0.5'),
(1,6,N'2025-01-22',N'0.5'),
(1,6,N'2025-01-23',N'0.5'),
(2,6,N'2025-01-02',N'0.42176366'),
(2,6,N'2025-01-03',N'0.5602336'),
(2,6,N'2025-01-06',N'0.68395625'),
(2,6,N'2025-01-07',N'0.76263999'),
(2,6,N'2025-01-08',N'0.77702031'),
(2,6,N'2025-01-09',N'0.72357639'),
(2,6,N'2025-01-10',N'0.61539318'),
(2,6,N'2025-01-13',N'0.47895769'),
(2,6,N'2025-01-14',N'0.34767409'),
(2,6,N'2025-01-15',N'0.25368519'),
(2,6,N'2025-01-16',N'0.22000274'),
(2,6,N'2025-01-17',N'0.25487339'),
(2,6,N'2025-01-20',N'0.34975958'),
(2,6,N'2025-01-21',N'0.48142987'),
(2,6,N'2025-01-22',N'0.61764677'),
(2,6,N'2025-01-23',N'0.72505964'),
(1,7,N'2025-01-02',N'0.5'),
(1,7,N'2025-01-03',N'0.5'),
(1,7,N'2025-01-06',N'0.5'),
(1,7,N'2025-01-07',N'0.5'),
(1,7,N'2025-01-08',N'0.5'),
(1,7,N'2025-01-09',N'0.5'),
(1,7,N'2025-01-10',N'0.5'),
(1,7,N'2025-01-13',N'0.5')
) v([RunId],[StockId],[OriginDate],[ProbabilityPositive]) ON d.[RunId]=v.[RunId] AND d.[StockId]=v.[StockId] AND d.[OriginDate]=v.[OriginDate] WHERE EXISTS(SELECT d.[RunId],d.[StockId],d.[OriginDate],d.[ProbabilityPositive] EXCEPT SELECT v.[RunId],v.[StockId],v.[OriginDate],v.[ProbabilityPositive])) THROW 51100,N'Import conflict: Prediction',1;
 INSERT dbo.[Prediction]([RunId],[StockId],[OriginDate],[ProbabilityPositive]) SELECT v.[RunId],v.[StockId],v.[OriginDate],v.[ProbabilityPositive] FROM (VALUES
(1,1,N'2025-01-02',N'0.5'),
(1,1,N'2025-01-03',N'0.5'),
(1,1,N'2025-01-06',N'0.5'),
(1,1,N'2025-01-07',N'0.5'),
(1,1,N'2025-01-08',N'0.5'),
(1,1,N'2025-01-09',N'0.5'),
(1,1,N'2025-01-10',N'0.5'),
(1,1,N'2025-01-13',N'0.5'),
(1,1,N'2025-01-14',N'0.5'),
(1,1,N'2025-01-15',N'0.5'),
(1,1,N'2025-01-16',N'0.5'),
(1,1,N'2025-01-17',N'0.5'),
(1,1,N'2025-01-20',N'0.5'),
(1,1,N'2025-01-21',N'0.5'),
(1,1,N'2025-01-22',N'0.5'),
(1,1,N'2025-01-23',N'0.5'),
(2,1,N'2025-01-02',N'0.73561188'),
(2,1,N'2025-01-03',N'0.7792986'),
(2,1,N'2025-01-06',N'0.75460328'),
(2,1,N'2025-01-07',N'0.6675722'),
(2,1,N'2025-01-08',N'0.5395136'),
(2,1,N'2025-01-09',N'0.4017807'),
(2,1,N'2025-01-10',N'0.2880953'),
(2,1,N'2025-01-13',N'0.22629157'),
(2,1,N'2025-01-14',N'0.2315012'),
(2,1,N'2025-01-15',N'0.30244871'),
(2,1,N'2025-01-16',N'0.42176366'),
(2,1,N'2025-01-17',N'0.5602336'),
(2,1,N'2025-01-20',N'0.68395625'),
(2,1,N'2025-01-21',N'0.76263999'),
(2,1,N'2025-01-22',N'0.77702031'),
(2,1,N'2025-01-23',N'0.72357639'),
(1,2,N'2025-01-02',N'0.5'),
(1,2,N'2025-01-03',N'0.5'),
(1,2,N'2025-01-06',N'0.5'),
(1,2,N'2025-01-07',N'0.5'),
(1,2,N'2025-01-08',N'0.5'),
(1,2,N'2025-01-09',N'0.5'),
(1,2,N'2025-01-10',N'0.5'),
(1,2,N'2025-01-13',N'0.5'),
(1,2,N'2025-01-14',N'0.5'),
(1,2,N'2025-01-15',N'0.5'),
(1,2,N'2025-01-16',N'0.5'),
(1,2,N'2025-01-17',N'0.5'),
(1,2,N'2025-01-20',N'0.5'),
(1,2,N'2025-01-21',N'0.5'),
(1,2,N'2025-01-22',N'0.5'),
(1,2,N'2025-01-23',N'0.5'),
(2,2,N'2025-01-02',N'0.75460328'),
(2,2,N'2025-01-03',N'0.6675722'),
(2,2,N'2025-01-06',N'0.5395136'),
(2,2,N'2025-01-07',N'0.4017807'),
(2,2,N'2025-01-08',N'0.2880953'),
(2,2,N'2025-01-09',N'0.22629157'),
(2,2,N'2025-01-10',N'0.2315012'),
(2,2,N'2025-01-13',N'0.30244871'),
(2,2,N'2025-01-14',N'0.42176366'),
(2,2,N'2025-01-15',N'0.5602336'),
(2,2,N'2025-01-16',N'0.68395625'),
(2,2,N'2025-01-17',N'0.76263999'),
(2,2,N'2025-01-20',N'0.77702031'),
(2,2,N'2025-01-21',N'0.72357639'),
(2,2,N'2025-01-22',N'0.61539318'),
(2,2,N'2025-01-23',N'0.47895769'),
(1,3,N'2025-01-02',N'0.5'),
(1,3,N'2025-01-03',N'0.5'),
(1,3,N'2025-01-06',N'0.5'),
(1,3,N'2025-01-07',N'0.5'),
(1,3,N'2025-01-08',N'0.5'),
(1,3,N'2025-01-09',N'0.5'),
(1,3,N'2025-01-10',N'0.5'),
(1,3,N'2025-01-13',N'0.5'),
(1,3,N'2025-01-14',N'0.5'),
(1,3,N'2025-01-15',N'0.5'),
(1,3,N'2025-01-16',N'0.5'),
(1,3,N'2025-01-17',N'0.5'),
(1,3,N'2025-01-20',N'0.5'),
(1,3,N'2025-01-21',N'0.5'),
(1,3,N'2025-01-22',N'0.5'),
(1,3,N'2025-01-23',N'0.5'),
(2,3,N'2025-01-02',N'0.5395136'),
(2,3,N'2025-01-03',N'0.4017807'),
(2,3,N'2025-01-06',N'0.2880953'),
(2,3,N'2025-01-07',N'0.22629157'),
(2,3,N'2025-01-08',N'0.2315012'),
(2,3,N'2025-01-09',N'0.30244871'),
(2,3,N'2025-01-10',N'0.42176366'),
(2,3,N'2025-01-13',N'0.5602336'),
(2,3,N'2025-01-14',N'0.68395625'),
(2,3,N'2025-01-15',N'0.76263999'),
(2,3,N'2025-01-16',N'0.77702031'),
(2,3,N'2025-01-17',N'0.72357639'),
(2,3,N'2025-01-20',N'0.61539318'),
(2,3,N'2025-01-21',N'0.47895769'),
(2,3,N'2025-01-22',N'0.34767409'),
(2,3,N'2025-01-23',N'0.25368519'),
(1,4,N'2025-01-02',N'0.5'),
(1,4,N'2025-01-03',N'0.5'),
(1,4,N'2025-01-06',N'0.5'),
(1,4,N'2025-01-07',N'0.5'),
(1,4,N'2025-01-08',N'0.5'),
(1,4,N'2025-01-09',N'0.5'),
(1,4,N'2025-01-10',N'0.5'),
(1,4,N'2025-01-13',N'0.5'),
(1,4,N'2025-01-14',N'0.5'),
(1,4,N'2025-01-15',N'0.5'),
(1,4,N'2025-01-16',N'0.5'),
(1,4,N'2025-01-17',N'0.5'),
(1,4,N'2025-01-20',N'0.5'),
(1,4,N'2025-01-21',N'0.5'),
(1,4,N'2025-01-22',N'0.5'),
(1,4,N'2025-01-23',N'0.5'),
(2,4,N'2025-01-02',N'0.2880953'),
(2,4,N'2025-01-03',N'0.22629157'),
(2,4,N'2025-01-06',N'0.2315012'),
(2,4,N'2025-01-07',N'0.30244871'),
(2,4,N'2025-01-08',N'0.42176366'),
(2,4,N'2025-01-09',N'0.5602336'),
(2,4,N'2025-01-10',N'0.68395625'),
(2,4,N'2025-01-13',N'0.76263999'),
(2,4,N'2025-01-14',N'0.77702031'),
(2,4,N'2025-01-15',N'0.72357639'),
(2,4,N'2025-01-16',N'0.61539318'),
(2,4,N'2025-01-17',N'0.47895769'),
(2,4,N'2025-01-20',N'0.34767409'),
(2,4,N'2025-01-21',N'0.25368519'),
(2,4,N'2025-01-22',N'0.22000274'),
(2,4,N'2025-01-23',N'0.25487339'),
(1,5,N'2025-01-02',N'0.5'),
(1,5,N'2025-01-03',N'0.5'),
(1,5,N'2025-01-06',N'0.5'),
(1,5,N'2025-01-07',N'0.5'),
(1,5,N'2025-01-08',N'0.5'),
(1,5,N'2025-01-09',N'0.5'),
(1,5,N'2025-01-10',N'0.5'),
(1,5,N'2025-01-13',N'0.5'),
(1,5,N'2025-01-14',N'0.5'),
(1,5,N'2025-01-15',N'0.5'),
(1,5,N'2025-01-16',N'0.5'),
(1,5,N'2025-01-17',N'0.5'),
(1,5,N'2025-01-20',N'0.5'),
(1,5,N'2025-01-21',N'0.5'),
(1,5,N'2025-01-22',N'0.5'),
(1,5,N'2025-01-23',N'0.5'),
(2,5,N'2025-01-02',N'0.2315012'),
(2,5,N'2025-01-03',N'0.30244871'),
(2,5,N'2025-01-06',N'0.42176366'),
(2,5,N'2025-01-07',N'0.5602336'),
(2,5,N'2025-01-08',N'0.68395625'),
(2,5,N'2025-01-09',N'0.76263999'),
(2,5,N'2025-01-10',N'0.77702031'),
(2,5,N'2025-01-13',N'0.72357639'),
(2,5,N'2025-01-14',N'0.61539318'),
(2,5,N'2025-01-15',N'0.47895769'),
(2,5,N'2025-01-16',N'0.34767409'),
(2,5,N'2025-01-17',N'0.25368519'),
(2,5,N'2025-01-20',N'0.22000274'),
(2,5,N'2025-01-21',N'0.25487339'),
(2,5,N'2025-01-22',N'0.34975958'),
(2,5,N'2025-01-23',N'0.48142987'),
(1,6,N'2025-01-02',N'0.5'),
(1,6,N'2025-01-03',N'0.5'),
(1,6,N'2025-01-06',N'0.5'),
(1,6,N'2025-01-07',N'0.5'),
(1,6,N'2025-01-08',N'0.5'),
(1,6,N'2025-01-09',N'0.5'),
(1,6,N'2025-01-10',N'0.5'),
(1,6,N'2025-01-13',N'0.5'),
(1,6,N'2025-01-14',N'0.5'),
(1,6,N'2025-01-15',N'0.5'),
(1,6,N'2025-01-16',N'0.5'),
(1,6,N'2025-01-17',N'0.5'),
(1,6,N'2025-01-20',N'0.5'),
(1,6,N'2025-01-21',N'0.5'),
(1,6,N'2025-01-22',N'0.5'),
(1,6,N'2025-01-23',N'0.5'),
(2,6,N'2025-01-02',N'0.42176366'),
(2,6,N'2025-01-03',N'0.5602336'),
(2,6,N'2025-01-06',N'0.68395625'),
(2,6,N'2025-01-07',N'0.76263999'),
(2,6,N'2025-01-08',N'0.77702031'),
(2,6,N'2025-01-09',N'0.72357639'),
(2,6,N'2025-01-10',N'0.61539318'),
(2,6,N'2025-01-13',N'0.47895769'),
(2,6,N'2025-01-14',N'0.34767409'),
(2,6,N'2025-01-15',N'0.25368519'),
(2,6,N'2025-01-16',N'0.22000274'),
(2,6,N'2025-01-17',N'0.25487339'),
(2,6,N'2025-01-20',N'0.34975958'),
(2,6,N'2025-01-21',N'0.48142987'),
(2,6,N'2025-01-22',N'0.61764677'),
(2,6,N'2025-01-23',N'0.72505964'),
(1,7,N'2025-01-02',N'0.5'),
(1,7,N'2025-01-03',N'0.5'),
(1,7,N'2025-01-06',N'0.5'),
(1,7,N'2025-01-07',N'0.5'),
(1,7,N'2025-01-08',N'0.5'),
(1,7,N'2025-01-09',N'0.5'),
(1,7,N'2025-01-10',N'0.5'),
(1,7,N'2025-01-13',N'0.5')
) v([RunId],[StockId],[OriginDate],[ProbabilityPositive]) WHERE NOT EXISTS(SELECT 1 FROM dbo.[Prediction] d WITH(UPDLOCK,HOLDLOCK) WHERE d.[RunId]=v.[RunId] AND d.[StockId]=v.[StockId] AND d.[OriginDate]=v.[OriginDate]);
 SET @Added=@Added+@@ROWCOUNT;
 IF EXISTS(SELECT 1 FROM dbo.[Prediction] d JOIN (VALUES
(1,7,N'2025-01-14',N'0.5'),
(1,7,N'2025-01-15',N'0.5'),
(1,7,N'2025-01-16',N'0.5'),
(1,7,N'2025-01-17',N'0.5'),
(1,7,N'2025-01-20',N'0.5'),
(1,7,N'2025-01-21',N'0.5'),
(1,7,N'2025-01-22',N'0.5'),
(1,7,N'2025-01-23',N'0.5'),
(2,7,N'2025-01-02',N'0.68395625'),
(2,7,N'2025-01-03',N'0.76263999'),
(2,7,N'2025-01-06',N'0.77702031'),
(2,7,N'2025-01-07',N'0.72357639'),
(2,7,N'2025-01-08',N'0.61539318'),
(2,7,N'2025-01-09',N'0.47895769'),
(2,7,N'2025-01-10',N'0.34767409'),
(2,7,N'2025-01-13',N'0.25368519'),
(2,7,N'2025-01-14',N'0.22000274'),
(2,7,N'2025-01-15',N'0.25487339'),
(2,7,N'2025-01-16',N'0.34975958'),
(2,7,N'2025-01-17',N'0.48142987'),
(2,7,N'2025-01-20',N'0.61764677'),
(2,7,N'2025-01-21',N'0.72505964'),
(2,7,N'2025-01-22',N'0.77737006'),
(2,7,N'2025-01-23',N'0.76177062'),
(1,8,N'2025-01-02',N'0.5'),
(1,8,N'2025-01-03',N'0.5'),
(1,8,N'2025-01-06',N'0.5'),
(1,8,N'2025-01-07',N'0.5'),
(1,8,N'2025-01-08',N'0.5'),
(1,8,N'2025-01-09',N'0.5'),
(1,8,N'2025-01-10',N'0.5'),
(1,8,N'2025-01-13',N'0.5'),
(1,8,N'2025-01-14',N'0.5'),
(1,8,N'2025-01-15',N'0.5'),
(1,8,N'2025-01-16',N'0.5'),
(1,8,N'2025-01-17',N'0.5'),
(1,8,N'2025-01-20',N'0.5'),
(1,8,N'2025-01-21',N'0.5'),
(1,8,N'2025-01-22',N'0.5'),
(1,8,N'2025-01-23',N'0.5'),
(2,8,N'2025-01-02',N'0.77702031'),
(2,8,N'2025-01-03',N'0.72357639'),
(2,8,N'2025-01-06',N'0.61539318'),
(2,8,N'2025-01-07',N'0.47895769'),
(2,8,N'2025-01-08',N'0.34767409'),
(2,8,N'2025-01-09',N'0.25368519'),
(2,8,N'2025-01-10',N'0.22000274'),
(2,8,N'2025-01-13',N'0.25487339'),
(2,8,N'2025-01-14',N'0.34975958'),
(2,8,N'2025-01-15',N'0.48142987'),
(2,8,N'2025-01-16',N'0.61764677'),
(2,8,N'2025-01-17',N'0.72505964'),
(2,8,N'2025-01-20',N'0.77737006'),
(2,8,N'2025-01-21',N'0.76177062'),
(2,8,N'2025-01-22',N'0.6820806'),
(2,8,N'2025-01-23',N'0.55781089'),
(1,1,N'2025-02-17',N'0.55'),
(2,1,N'2025-02-17',N'0.55')
) v([RunId],[StockId],[OriginDate],[ProbabilityPositive]) ON d.[RunId]=v.[RunId] AND d.[StockId]=v.[StockId] AND d.[OriginDate]=v.[OriginDate] WHERE EXISTS(SELECT d.[RunId],d.[StockId],d.[OriginDate],d.[ProbabilityPositive] EXCEPT SELECT v.[RunId],v.[StockId],v.[OriginDate],v.[ProbabilityPositive])) THROW 51100,N'Import conflict: Prediction',1;
 INSERT dbo.[Prediction]([RunId],[StockId],[OriginDate],[ProbabilityPositive]) SELECT v.[RunId],v.[StockId],v.[OriginDate],v.[ProbabilityPositive] FROM (VALUES
(1,7,N'2025-01-14',N'0.5'),
(1,7,N'2025-01-15',N'0.5'),
(1,7,N'2025-01-16',N'0.5'),
(1,7,N'2025-01-17',N'0.5'),
(1,7,N'2025-01-20',N'0.5'),
(1,7,N'2025-01-21',N'0.5'),
(1,7,N'2025-01-22',N'0.5'),
(1,7,N'2025-01-23',N'0.5'),
(2,7,N'2025-01-02',N'0.68395625'),
(2,7,N'2025-01-03',N'0.76263999'),
(2,7,N'2025-01-06',N'0.77702031'),
(2,7,N'2025-01-07',N'0.72357639'),
(2,7,N'2025-01-08',N'0.61539318'),
(2,7,N'2025-01-09',N'0.47895769'),
(2,7,N'2025-01-10',N'0.34767409'),
(2,7,N'2025-01-13',N'0.25368519'),
(2,7,N'2025-01-14',N'0.22000274'),
(2,7,N'2025-01-15',N'0.25487339'),
(2,7,N'2025-01-16',N'0.34975958'),
(2,7,N'2025-01-17',N'0.48142987'),
(2,7,N'2025-01-20',N'0.61764677'),
(2,7,N'2025-01-21',N'0.72505964'),
(2,7,N'2025-01-22',N'0.77737006'),
(2,7,N'2025-01-23',N'0.76177062'),
(1,8,N'2025-01-02',N'0.5'),
(1,8,N'2025-01-03',N'0.5'),
(1,8,N'2025-01-06',N'0.5'),
(1,8,N'2025-01-07',N'0.5'),
(1,8,N'2025-01-08',N'0.5'),
(1,8,N'2025-01-09',N'0.5'),
(1,8,N'2025-01-10',N'0.5'),
(1,8,N'2025-01-13',N'0.5'),
(1,8,N'2025-01-14',N'0.5'),
(1,8,N'2025-01-15',N'0.5'),
(1,8,N'2025-01-16',N'0.5'),
(1,8,N'2025-01-17',N'0.5'),
(1,8,N'2025-01-20',N'0.5'),
(1,8,N'2025-01-21',N'0.5'),
(1,8,N'2025-01-22',N'0.5'),
(1,8,N'2025-01-23',N'0.5'),
(2,8,N'2025-01-02',N'0.77702031'),
(2,8,N'2025-01-03',N'0.72357639'),
(2,8,N'2025-01-06',N'0.61539318'),
(2,8,N'2025-01-07',N'0.47895769'),
(2,8,N'2025-01-08',N'0.34767409'),
(2,8,N'2025-01-09',N'0.25368519'),
(2,8,N'2025-01-10',N'0.22000274'),
(2,8,N'2025-01-13',N'0.25487339'),
(2,8,N'2025-01-14',N'0.34975958'),
(2,8,N'2025-01-15',N'0.48142987'),
(2,8,N'2025-01-16',N'0.61764677'),
(2,8,N'2025-01-17',N'0.72505964'),
(2,8,N'2025-01-20',N'0.77737006'),
(2,8,N'2025-01-21',N'0.76177062'),
(2,8,N'2025-01-22',N'0.6820806'),
(2,8,N'2025-01-23',N'0.55781089'),
(1,1,N'2025-02-17',N'0.55'),
(2,1,N'2025-02-17',N'0.55')
) v([RunId],[StockId],[OriginDate],[ProbabilityPositive]) WHERE NOT EXISTS(SELECT 1 FROM dbo.[Prediction] d WITH(UPDLOCK,HOLDLOCK) WHERE d.[RunId]=v.[RunId] AND d.[StockId]=v.[StockId] AND d.[OriginDate]=v.[OriginDate]);
 SET @Added=@Added+@@ROWCOUNT;
 INSERT #ImportReceipt VALUES(N'Prediction',258,@Added);
 COMMIT;
 SELECT TableName,RowsInput,RowsInput-RowsInserted AS RowsAlreadyPresent,RowsInserted FROM #ImportReceipt ORDER BY TableName;
 DROP TABLE #ImportReceipt;
END TRY
BEGIN CATCH
 IF XACT_STATE()<>0 ROLLBACK;
 THROW;
END CATCH;
GO

-- FILE: 04_functions.sql
USE [MarketLabVN30_Demo];
GO
CREATE OR ALTER FUNCTION dbo.fn_CalculateReturn(@StartPrice decimal(19,6),@EndPrice decimal(19,6))
RETURNS decimal(19,8) AS
BEGIN
 RETURN CASE WHEN @StartPrice IS NULL OR @StartPrice<=0 OR @EndPrice IS NULL OR @EndPrice<=0 THEN NULL
 ELSE CONVERT(decimal(19,8),(@EndPrice-@StartPrice)/@StartPrice*100.0) END;
END;
GO
-- Three directions: negative, zero, positive. Zero matches only zero.
CREATE OR ALTER FUNCTION dbo.fn_CheckPredictionDirection(@PredictedReturn decimal(19,8),@ActualReturn decimal(19,8))
RETURNS bit AS
BEGIN
 RETURN CASE WHEN @PredictedReturn IS NULL OR @ActualReturn IS NULL THEN NULL
 WHEN SIGN(@PredictedReturn)=SIGN(@ActualReturn) THEN 1 ELSE 0 END;
END;
GO
CREATE OR ALTER FUNCTION dbo.fn_EligiblePredictions(@AsOfDate date)
RETURNS TABLE AS RETURN
 SELECT p.RunId,r.ModelId,r.DatasetId,r.TargetId,p.StockId,p.OriginDate,f.TargetDate,
 t.HorizonSessions,p.ProbabilityPositive,r.Threshold,
 CONVERT(bit,CASE WHEN z.ClosePrice>a.ClosePrice THEN 1 ELSE 0 END) AS ActualLabel,
 CONVERT(bit,CASE WHEN p.ProbabilityPositive>=r.Threshold THEN 1 ELSE 0 END) AS PredictedLabel,
 dbo.fn_CalculateReturn(a.ClosePrice,z.ClosePrice) AS ActualSourceCloseReturnPct
 FROM dbo.Prediction p JOIN dbo.ModelRun r ON r.RunId=p.RunId
 JOIN dbo.ForecastOrigin f ON f.RunId=p.RunId AND f.OriginDate=p.OriginDate
 JOIN dbo.TargetDefinition t ON t.TargetId=r.TargetId JOIN dbo.Dataset d ON d.DatasetId=r.DatasetId
 JOIN dbo.DailyPrice a ON a.DatasetId=r.DatasetId AND a.StockId=p.StockId AND a.TradeDate=p.OriginDate
 JOIN dbo.DailyPrice z ON z.DatasetId=r.DatasetId AND z.StockId=p.StockId AND z.TradeDate=f.TargetDate
 WHERE f.TargetDate<=@AsOfDate AND f.TargetDate<=d.ObservedThrough AND p.OriginDate>r.ValidationEnd;
GO

-- FILE: 05_views.sql
USE [MarketLabVN30_Demo];
GO
CREATE OR ALTER VIEW dbo.vw_LatestStockPrice AS
 WITH Ranked AS(SELECT p.*,ROW_NUMBER() OVER(PARTITION BY DatasetId,StockId ORDER BY TradeDate DESC) AS rn FROM dbo.DailyPrice p)
 SELECT p.DatasetId,s.StockId,s.Ticker,p.TradeDate,p.ClosePrice,p.Volume,d.PriceUnit,d.PriceBasis
 FROM Ranked p JOIN dbo.Stock s ON s.StockId=p.StockId JOIN dbo.Dataset d ON d.DatasetId=p.DatasetId WHERE rn=1;
GO
CREATE OR ALTER VIEW dbo.vw_StudyUniverse AS
 SELECT d.DatasetId,d.DatasetCode,d.DataKind,s.StockId,s.Ticker,s.CompanyName,s.IndustryId,
 MIN(p.TradeDate) AS FirstObservedDate,MAX(p.TradeDate) AS LastObservedDate,COUNT_BIG(*) AS PriceRows
 FROM dbo.DailyPrice p JOIN dbo.Stock s ON s.StockId=p.StockId JOIN dbo.Dataset d ON d.DatasetId=p.DatasetId
 GROUP BY d.DatasetId,d.DatasetCode,d.DataKind,s.StockId,s.Ticker,s.CompanyName,s.IndustryId;
GO
-- A bounded snapshot only. Not a current or historical VN30 membership claim.
CREATE OR ALTER VIEW dbo.vw_VN30SnapshotJune2026 AS
 SELECT s.StockId,s.Ticker,m.ValidFrom,m.ValidTo,m.EvidenceNote
 FROM dbo.IndexMembership m JOIN dbo.Stock s ON s.StockId=m.StockId JOIN dbo.StockIndex x ON x.IndexId=m.IndexId
 WHERE x.IndexCode='VN30' AND CONVERT(date,'20260630') BETWEEN m.ValidFrom AND m.ValidTo;
GO
CREATE OR ALTER VIEW dbo.vw_ModelPerformance AS
 SELECT e.RunId,e.ModelId,e.DatasetId,e.TargetId,e.HorizonSessions,COUNT_BIG(*) AS EvaluatedRows,
 AVG(CONVERT(decimal(19,10),CASE WHEN e.PredictedLabel=e.ActualLabel THEN 1.0 ELSE 0.0 END)) AS Accuracy,
 AVG(POWER(CONVERT(float,e.ProbabilityPositive)-CONVERT(int,e.ActualLabel),2)) AS BrierScore,
 AVG(-LOG(CASE WHEN e.ActualLabel=1 THEN
 CASE WHEN e.ProbabilityPositive<0.000000000001 THEN 0.000000000001 ELSE CONVERT(float,e.ProbabilityPositive) END
 ELSE CASE WHEN e.ProbabilityPositive>0.999999999999 THEN 0.000000000001 ELSE 1.0-CONVERT(float,e.ProbabilityPositive) END END)) AS NaturalLogLoss
 FROM dbo.fn_EligiblePredictions(CONVERT(date,SYSUTCDATETIME())) e
 GROUP BY e.RunId,e.ModelId,e.DatasetId,e.TargetId,e.HorizonSessions;
GO

-- FILE: 06_stored_procedures.sql
USE [MarketLabVN30_Demo];
GO
CREATE OR ALTER PROCEDURE dbo.usp_InsertDailyPrice
 @DatasetId int,@StockId int,@TradeDate date,@OpenPrice decimal(19,6),@HighPrice decimal(19,6),
 @LowPrice decimal(19,6),@ClosePrice decimal(19,6),@Volume bigint,@AllowUpdate bit=0
AS
BEGIN
 SET NOCOUNT ON; SET XACT_ABORT ON;
 IF @TradeDate IS NULL OR @OpenPrice IS NULL OR @HighPrice IS NULL OR @LowPrice IS NULL OR @ClosePrice IS NULL OR @Volume IS NULL
 OR @OpenPrice<=0 OR @ClosePrice<=0 OR @LowPrice<=0 OR @HighPrice<@OpenPrice OR @HighPrice<@ClosePrice OR @HighPrice<@LowPrice
 OR @LowPrice>@OpenPrice OR @LowPrice>@ClosePrice OR @Volume<0
 THROW 51010,N'OHLCV khong hop le.',1;
 IF NOT EXISTS(SELECT 1 FROM dbo.TradingDay WHERE DatasetId=@DatasetId AND TradeDate=@TradeDate)
 THROW 51011,N'Ngay khong thuoc lich phien cua dataset.',1;
 DECLARE @Own bit=CASE WHEN @@TRANCOUNT=0 THEN 1 ELSE 0 END;
 BEGIN TRY
  IF @Own=1 BEGIN TRANSACTION; ELSE SAVE TRANSACTION PriceSave;
  IF EXISTS(SELECT 1 FROM dbo.DailyPrice WITH(UPDLOCK,HOLDLOCK) WHERE DatasetId=@DatasetId AND StockId=@StockId AND TradeDate=@TradeDate)
  BEGIN
   IF EXISTS(SELECT @OpenPrice,@HighPrice,@LowPrice,@ClosePrice,@Volume EXCEPT
    SELECT OpenPrice,HighPrice,LowPrice,ClosePrice,Volume FROM dbo.DailyPrice WHERE DatasetId=@DatasetId AND StockId=@StockId AND TradeDate=@TradeDate)
   BEGIN
    IF ISNULL(@AllowUpdate,0)=0 THROW 51012,N'Khoa gia da ton tai voi gia tri khac. Can @AllowUpdate=1.',1;
    UPDATE dbo.DailyPrice SET OpenPrice=@OpenPrice,HighPrice=@HighPrice,LowPrice=@LowPrice,ClosePrice=@ClosePrice,Volume=@Volume
    WHERE DatasetId=@DatasetId AND StockId=@StockId AND TradeDate=@TradeDate;
   END;
  END
  ELSE INSERT dbo.DailyPrice(DatasetId,StockId,TradeDate,OpenPrice,HighPrice,LowPrice,ClosePrice,Volume)
   VALUES(@DatasetId,@StockId,@TradeDate,@OpenPrice,@HighPrice,@LowPrice,@ClosePrice,@Volume);
  IF @Own=1 COMMIT;
 END TRY
 BEGIN CATCH
  IF @Own=1 AND XACT_STATE()<>0 ROLLBACK;
  ELSE IF @Own=0 AND XACT_STATE()=1 ROLLBACK TRANSACTION PriceSave;
  THROW;
 END CATCH;
END;
GO
CREATE OR ALTER PROCEDURE dbo.usp_AddPrediction
 @RunId int,@StockId int,@OriginDate date,@TargetDate date,@ProbabilityPositive decimal(19,16)
AS
BEGIN
 SET NOCOUNT ON; SET XACT_ABORT ON;
 IF @OriginDate IS NULL OR @TargetDate IS NULL OR @TargetDate<=@OriginDate OR @ProbabilityPositive IS NULL OR @ProbabilityPositive NOT BETWEEN 0 AND 1
 THROW 51013,N'Ngay hoac xac suat du bao khong hop le.',1;
 IF NOT EXISTS(SELECT 1 FROM dbo.ModelRun WHERE RunId=@RunId) OR NOT EXISTS(SELECT 1 FROM dbo.Stock WHERE StockId=@StockId)
 THROW 51014,N'Ma co phieu hoac model run khong ton tai.',1;
 DECLARE @Own bit=CASE WHEN @@TRANCOUNT=0 THEN 1 ELSE 0 END;
 BEGIN TRY
  IF @Own=1 BEGIN TRANSACTION; ELSE SAVE TRANSACTION PredictionSave;
  IF EXISTS(SELECT 1 FROM dbo.ForecastOrigin WITH(UPDLOCK,HOLDLOCK) WHERE RunId=@RunId AND OriginDate=@OriginDate)
  BEGIN
   IF EXISTS(SELECT 1 FROM dbo.ForecastOrigin WHERE RunId=@RunId AND OriginDate=@OriginDate AND TargetDate<>@TargetDate)
    THROW 51015,N'Ngay muc tieu khac ngay da luu cua lan chay.',1;
  END
  ELSE INSERT dbo.ForecastOrigin(RunId,OriginDate,TargetDate) VALUES(@RunId,@OriginDate,@TargetDate);
  IF EXISTS(SELECT 1 FROM dbo.Prediction WITH(UPDLOCK,HOLDLOCK) WHERE RunId=@RunId AND StockId=@StockId AND OriginDate=@OriginDate)
  BEGIN
   IF EXISTS(SELECT @ProbabilityPositive EXCEPT SELECT ProbabilityPositive FROM dbo.Prediction WHERE RunId=@RunId AND StockId=@StockId AND OriginDate=@OriginDate)
    THROW 51015,N'Du bao trung khoa nhung khac gia tri.',1;
  END
  ELSE INSERT dbo.Prediction(RunId,StockId,OriginDate,ProbabilityPositive)
   VALUES(@RunId,@StockId,@OriginDate,@ProbabilityPositive);
  IF @Own=1 COMMIT;
 END TRY
 BEGIN CATCH
  IF @Own=1 AND XACT_STATE()<>0 ROLLBACK;
  ELSE IF @Own=0 AND XACT_STATE()=1 ROLLBACK TRANSACTION PredictionSave;
  THROW;
 END CATCH;
END;
GO
CREATE OR ALTER PROCEDURE dbo.usp_GetModelPerformance
 @ModelCode varchar(70),@DatasetId int,@HorizonSessions int,@FromDate date,@ToDate date,@AsOfDate date
AS
BEGIN
 SET NOCOUNT ON;
 IF @FromDate IS NULL OR @ToDate IS NULL OR @AsOfDate IS NULL OR @FromDate>@ToDate OR @HorizonSessions IS NULL OR @HorizonSessions<=0
 THROW 51016,N'Bo loc ngay/horizon khong hop le.',1;
 IF NOT EXISTS(SELECT 1 FROM dbo.ForecastModel WHERE ModelCode=@ModelCode) OR NOT EXISTS(SELECT 1 FROM dbo.Dataset WHERE DatasetId=@DatasetId)
 THROW 51017,N'Model hoac dataset khong ton tai.',1;
 SELECT e.RunId,m.ModelCode,e.DatasetId,e.HorizonSessions,@AsOfDate AS EvaluationAsOf,COUNT_BIG(*) AS EvaluatedRows,
 AVG(CONVERT(decimal(19,10),CASE WHEN ActualLabel=PredictedLabel THEN 1.0 ELSE 0.0 END)) AS Accuracy,
 AVG(POWER(CONVERT(float,ProbabilityPositive)-CONVERT(int,ActualLabel),2)) AS BrierScore
 FROM dbo.fn_EligiblePredictions(@AsOfDate) e JOIN dbo.ForecastModel m ON m.ModelId=e.ModelId
 WHERE m.ModelCode=@ModelCode AND e.DatasetId=@DatasetId AND e.HorizonSessions=@HorizonSessions AND e.OriginDate BETWEEN @FromDate AND @ToDate
 GROUP BY e.RunId,m.ModelCode,e.DatasetId,e.HorizonSessions;
END;
GO
CREATE OR ALTER PROCEDURE dbo.usp_CompareModels
 @RunIds varchar(200),@FromDate date,@ToDate date,@AsOfDate date
AS
BEGIN
 SET NOCOUNT ON;
 IF @FromDate IS NULL OR @ToDate IS NULL OR @AsOfDate IS NULL OR @FromDate>@ToDate OR NULLIF(LTRIM(RTRIM(@RunIds)),'') IS NULL
 THROW 51018,N'Danh sach run hoac khoang ngay khong hop le.',1;
 IF EXISTS(SELECT 1 FROM STRING_SPLIT(@RunIds,',') WHERE TRY_CONVERT(int,value) IS NULL)
 THROW 51018,N'RunId phai la so nguyen.',1;
 DECLARE @Runs TABLE(RunId int PRIMARY KEY);
 INSERT @Runs SELECT DISTINCT CONVERT(int,value) FROM STRING_SPLIT(@RunIds,',');
 DECLARE @N int=(SELECT COUNT(*) FROM @Runs);
 IF @N<2 OR @N>8 OR EXISTS(SELECT 1 FROM @Runs q LEFT JOIN dbo.ModelRun r ON r.RunId=q.RunId WHERE r.RunId IS NULL)
 THROW 51019,N'Can 2 den 8 run ton tai.',1;
 IF (SELECT COUNT(*) FROM(SELECT r.DatasetId,r.TargetId FROM dbo.ModelRun r JOIN @Runs q ON q.RunId=r.RunId GROUP BY r.DatasetId,r.TargetId) t)<>1
 THROW 51020,N'Khong so sanh khac dataset hoac dinh nghia bien muc tieu.',1;
 SELECT e.* INTO #Eligible FROM dbo.fn_EligiblePredictions(@AsOfDate) e JOIN @Runs q ON q.RunId=e.RunId
 WHERE e.OriginDate BETWEEN @FromDate AND @ToDate;
 SELECT StockId,OriginDate,TargetDate INTO #Common FROM #Eligible GROUP BY StockId,OriginDate,TargetDate HAVING COUNT(*)=@N;
 IF NOT EXISTS(SELECT 1 FROM #Common) THROW 51021,N'Khong co quan sat da truong thanh chung cho tat ca run.',1;
 SELECT e.RunId,m.ModelCode,COUNT_BIG(*) AS CommonObservations,@AsOfDate AS EvaluationAsOf,
 AVG(CONVERT(decimal(19,10),CASE WHEN e.ActualLabel=e.PredictedLabel THEN 1.0 ELSE 0.0 END)) AS Accuracy,
 AVG(POWER(CONVERT(float,e.ProbabilityPositive)-CONVERT(int,e.ActualLabel),2)) AS BrierScore
 FROM #Eligible e JOIN #Common c ON c.StockId=e.StockId AND c.OriginDate=e.OriginDate AND c.TargetDate=e.TargetDate
 JOIN dbo.ForecastModel m ON m.ModelId=e.ModelId
 GROUP BY e.RunId,m.ModelCode ORDER BY e.RunId;
END;
GO

SET NOEXEC OFF;
