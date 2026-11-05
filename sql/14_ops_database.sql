-- MarketLab VN30 - operational (ops) database, schema version 1.
-- Separate from the 13 business tables. One ops database may serve several business databases;
-- every row is keyed by (DatabaseName, DatasetId).
-- Create the database first (python -m marketlab_app.deploy ops-db does both), then:
--   sqlcmd -S . -E -C -b -d MarketLabVN30_Ops -i sql\14_ops_database.sql
-- Idempotent; never drops or rewrites data. Rollback: sql/14_ops_database_rollback.sql.
SET NOCOUNT ON;
SET XACT_ABORT ON;
SET QUOTED_IDENTIFIER ON;
SET ANSI_NULLS ON;
GO
IF DB_NAME() IN (N'master',N'model',N'msdb',N'tempdb',N'MarketLabVN30_Demo')
 OR EXISTS(SELECT 1 FROM sys.tables WHERE name=N'DailyPrice')
BEGIN
 RAISERROR(N'14_ops_database: run only on a dedicated ops database, never on a business database.',16,1);
 SET NOEXEC ON;
END;
GO
IF SCHEMA_ID(N'ops') IS NULL EXEC(N'CREATE SCHEMA ops AUTHORIZATION dbo;');
GO
IF OBJECT_ID(N'ops.SchemaVersion',N'U') IS NULL
CREATE TABLE ops.SchemaVersion(
 Version int NOT NULL CONSTRAINT PK_OpsSchemaVersion PRIMARY KEY,
 Description nvarchar(400) NOT NULL,
 AppliedAtUtc datetime2(3) NOT NULL CONSTRAINT DF_OpsSchemaVersion_At DEFAULT(SYSUTCDATETIME())
);
GO
-- Per business dataset: source, universe evidence and policy.
IF OBJECT_ID(N'ops.EodConfig',N'U') IS NULL
CREATE TABLE ops.EodConfig(
 DatabaseName sysname NOT NULL,
 DatasetId int NOT NULL,
 SourceCode varchar(40) NOT NULL CONSTRAINT CK_EodConfig_Source CHECK(SourceCode IN ('KBS_VNSTOCK')),
 IndexCode varchar(20) NOT NULL,
 UniverseAsOf date NOT NULL,
 CalendarReferenceSymbol varchar(20) NOT NULL,
 CutoffLocalTime time(0) NOT NULL CONSTRAINT DF_EodConfig_Cutoff DEFAULT('16:10'),
 RequireCompleteUniverse bit NOT NULL CONSTRAINT DF_EodConfig_Complete DEFAULT(1),
 Enabled bit NOT NULL CONSTRAINT DF_EodConfig_Enabled DEFAULT(1),
 UniverseEvidence nvarchar(1000) NOT NULL,
 CreatedAtUtc datetime2(3) NOT NULL CONSTRAINT DF_EodConfig_At DEFAULT(SYSUTCDATETIME()),
 CONSTRAINT PK_EodConfig PRIMARY KEY(DatabaseName,DatasetId),
 CONSTRAINT CK_EodConfig_Complete CHECK(RequireCompleteUniverse=1)  -- v1 supports all-or-nothing only
);
GO
IF OBJECT_ID(N'ops.EodRun',N'U') IS NULL
CREATE TABLE ops.EodRun(
 EodRunId bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_EodRun PRIMARY KEY,
 RunRef varchar(36) NOT NULL CONSTRAINT UQ_EodRun_Ref UNIQUE,
 BatchRef varchar(36) NULL,
 DatabaseName sysname NOT NULL,
 DatasetId int NOT NULL,
 SessionDate date NOT NULL,
 SourceCode varchar(40) NOT NULL,
 TriggerKind varchar(20) NOT NULL CONSTRAINT CK_EodRun_Trigger CHECK(TriggerKind IN ('CLI','API','SCHEDULER','TEST')),
 IsDryRun bit NOT NULL,
 Status varchar(20) NOT NULL CONSTRAINT CK_EodRun_Status CHECK(Status IN ('RUNNING','SUCCESS','FAILED','SKIPPED','NO_SESSION','PARTIAL','DRY_RUN_OK')),
 RequestedCount int NOT NULL CONSTRAINT DF_EodRun_Req DEFAULT(0),
 ReceivedCount int NOT NULL CONSTRAINT DF_EodRun_Rec DEFAULT(0),
 InsertedCount int NOT NULL CONSTRAINT DF_EodRun_Ins DEFAULT(0),
 UnchangedCount int NOT NULL CONSTRAINT DF_EodRun_Unc DEFAULT(0),
 RejectedCount int NOT NULL CONSTRAINT DF_EodRun_Rej DEFAULT(0),
 WouldInsertCount int NULL,
 StartedAtUtc datetime2(3) NOT NULL CONSTRAINT DF_EodRun_Start DEFAULT(SYSUTCDATETIME()),
 FinishedAtUtc datetime2(3) NULL,
 ErrorCode varchar(60) NULL,
 Message nvarchar(2000) NULL,
 ProviderLastCandleDate date NULL,
 ObservedThroughBefore date NULL,
 ObservedThroughAfter date NULL,
 ProviderMeta nvarchar(4000) NULL,
 HostName nvarchar(128) NULL,
 CONSTRAINT CK_EodRun_Counts CHECK(RequestedCount>=0 AND ReceivedCount>=0 AND InsertedCount>=0 AND UnchangedCount>=0 AND RejectedCount>=0),
 CONSTRAINT CK_EodRun_Finished CHECK((Status='RUNNING' AND FinishedAtUtc IS NULL) OR (Status<>'RUNNING' AND FinishedAtUtc IS NOT NULL)),
 -- SUCCESS means: real write, complete universe, nothing rejected.
 CONSTRAINT CK_EodRun_Success CHECK(Status<>'SUCCESS' OR (IsDryRun=0 AND RequestedCount>0 AND RejectedCount=0
   AND InsertedCount+UnchangedCount=RequestedCount AND ReceivedCount=RequestedCount)),
 CONSTRAINT CK_EodRun_DryRun CHECK(IsDryRun=1 OR Status<>'DRY_RUN_OK'),
 CONSTRAINT CK_EodRun_DryNoWrite CHECK(IsDryRun=0 OR InsertedCount=0),
 CONSTRAINT CK_EodRun_NoWriteUnlessSuccess CHECK(Status IN ('SUCCESS','RUNNING') OR InsertedCount=0),
 CONSTRAINT CK_EodRun_ErrorCode CHECK(Status NOT IN ('FAILED','PARTIAL','SKIPPED','NO_SESSION') OR ErrorCode IS NOT NULL)
);
GO
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'ops.EodRun') AND name=N'IX_EodRun_Dataset')
 CREATE INDEX IX_EodRun_Dataset ON ops.EodRun(DatabaseName,DatasetId,StartedAtUtc DESC) INCLUDE(SessionDate,Status,IsDryRun);
GO
IF OBJECT_ID(N'ops.EodRunItem',N'U') IS NULL
CREATE TABLE ops.EodRunItem(
 EodRunId bigint NOT NULL CONSTRAINT FK_EodRunItem_Run REFERENCES ops.EodRun(EodRunId),
 Ticker varchar(20) NOT NULL,
 StockId int NULL,
 Outcome varchar(20) NOT NULL CONSTRAINT CK_EodRunItem_Outcome CHECK(Outcome IN ('INSERTED','UNCHANGED','WOULD_INSERT','MISSING','REJECTED','CONFLICT','NOT_WRITTEN')),
 Detail nvarchar(400) NULL,
 CONSTRAINT PK_EodRunItem PRIMARY KEY(EodRunId,Ticker)
);
GO
-- Provider changed an already stored (closed) price: recorded for human review, never auto-applied.
IF OBJECT_ID(N'ops.PriceReconciliation',N'U') IS NULL
CREATE TABLE ops.PriceReconciliation(
 ReconId bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_PriceReconciliation PRIMARY KEY,
 EodRunId bigint NOT NULL CONSTRAINT FK_PriceRecon_Run REFERENCES ops.EodRun(EodRunId),
 DatabaseName sysname NOT NULL,
 DatasetId int NOT NULL,
 StockId int NOT NULL,
 Ticker varchar(20) NOT NULL,
 TradeDate date NOT NULL,
 StoredOpen decimal(19,6) NOT NULL, StoredHigh decimal(19,6) NOT NULL, StoredLow decimal(19,6) NOT NULL,
 StoredClose decimal(19,6) NOT NULL, StoredVolume bigint NOT NULL,
 ProviderOpen decimal(19,6) NOT NULL, ProviderHigh decimal(19,6) NOT NULL, ProviderLow decimal(19,6) NOT NULL,
 ProviderClose decimal(19,6) NOT NULL, ProviderVolume bigint NOT NULL,
 DetectedBy varchar(30) NOT NULL CONSTRAINT CK_PriceRecon_By CHECK(DetectedBy IN ('SESSION_CONFLICT','HISTORY_DRIFT_PROBE')),
 Status varchar(20) NOT NULL CONSTRAINT DF_PriceRecon_Status DEFAULT('PENDING_REVIEW')
   CONSTRAINT CK_PriceRecon_Status CHECK(Status IN ('PENDING_REVIEW','APPROVED_UPDATE','REJECTED')),
 DetectedAtUtc datetime2(3) NOT NULL CONSTRAINT DF_PriceRecon_At DEFAULT(SYSUTCDATETIME()),
 ReviewedBy nvarchar(128) NULL,
 ReviewedAtUtc datetime2(3) NULL,
 ReviewNote nvarchar(1000) NULL,
 CONSTRAINT CK_PriceRecon_Review CHECK((Status='PENDING_REVIEW' AND ReviewedAtUtc IS NULL) OR (Status<>'PENDING_REVIEW' AND ReviewedAtUtc IS NOT NULL AND ReviewedBy IS NOT NULL))
);
GO
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'ops.PriceReconciliation') AND name=N'IX_PriceRecon_Key')
 CREATE INDEX IX_PriceRecon_Key ON ops.PriceReconciliation(DatabaseName,DatasetId,StockId,TradeDate,Status);
GO
-- Lineage of rows inserted by EOD runs (which run, which provider call). Business tables are unchanged.
IF OBJECT_ID(N'ops.PriceLoadLineage',N'U') IS NULL
CREATE TABLE ops.PriceLoadLineage(
 DatabaseName sysname NOT NULL,
 DatasetId int NOT NULL,
 StockId int NOT NULL,
 TradeDate date NOT NULL,
 EodRunId bigint NOT NULL CONSTRAINT FK_Lineage_Run REFERENCES ops.EodRun(EodRunId),
 SourceCode varchar(40) NOT NULL,
 RecordedAtUtc datetime2(3) NOT NULL CONSTRAINT DF_Lineage_At DEFAULT(SYSUTCDATETIME()),
 CONSTRAINT PK_PriceLoadLineage PRIMARY KEY(DatabaseName,DatasetId,StockId,TradeDate)
);
GO
-- Evaluation of matured forecasts recomputed after a successful EOD write (SQL fn_EligiblePredictions).
IF OBJECT_ID(N'ops.EvaluationSnapshot',N'U') IS NULL
CREATE TABLE ops.EvaluationSnapshot(
 EodRunId bigint NOT NULL CONSTRAINT FK_EvalSnap_Run REFERENCES ops.EodRun(EodRunId),
 RunId int NOT NULL,
 RunCode varchar(100) NOT NULL,
 AsOfDate date NOT NULL,
 TotalPredictions bigint NOT NULL,
 EligibleRows bigint NOT NULL,
 Accuracy decimal(19,10) NULL,
 BrierScore float NULL,
 NaturalLogLoss float NULL,
 ComputedAtUtc datetime2(3) NOT NULL CONSTRAINT DF_EvalSnap_At DEFAULT(SYSUTCDATETIME()),
 CONSTRAINT PK_EvaluationSnapshot PRIMARY KEY(EodRunId,RunId)
);
GO
IF NOT EXISTS(SELECT 1 FROM ops.SchemaVersion WHERE Version=1)
 INSERT ops.SchemaVersion(Version,Description) VALUES(1,N'EOD ops v1: EodConfig, EodRun, EodRunItem, PriceReconciliation, PriceLoadLineage, EvaluationSnapshot');
GO
SELECT N'OPS_SCHEMA_V1_READY' AS Result,DB_NAME() AS DatabaseName,(SELECT MAX(Version) FROM ops.SchemaVersion) AS SchemaVersion;
GO
SET NOEXEC OFF;
GO
