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
IF OBJECT_ID(N'dbo.Prediction',N'U') IS NULL
CREATE TABLE dbo.Prediction(
 RunId int NOT NULL CONSTRAINT FK_Prediction_Run REFERENCES dbo.ModelRun(RunId),
 StockId int NOT NULL CONSTRAINT FK_Prediction_Stock REFERENCES dbo.Stock(StockId),
 OriginDate date NOT NULL,
 TargetDate date NOT NULL,
 ProbabilityPositive decimal(19,16) NOT NULL,
 LoadedAt datetime2(0) NOT NULL CONSTRAINT DF_Prediction_LoadedAt DEFAULT(SYSUTCDATETIME()),
 CONSTRAINT PK_Prediction PRIMARY KEY(RunId,StockId,OriginDate),
 CONSTRAINT CK_Prediction_Dates CHECK(TargetDate>OriginDate),
 CONSTRAINT CK_Prediction_Probability CHECK(ProbabilityPositive BETWEEN 0 AND 1)
);
GO
