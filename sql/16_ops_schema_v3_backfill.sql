-- MarketLab VN30 - ops database schema v3: historical backfill (run on the dedicated ops database only).
--   sqlcmd -S . -E -C -b -d MarketLabVN30_Ops -i sql\16_ops_schema_v3_backfill.sql
-- Business databases are NOT touched: the 13 business tables, ops.usp_EodApplySession and the guards stay as they are.
-- Changes (idempotent, additive; rollback: sql/16_ops_schema_v3_backfill_rollback.sql):
--   1. ops.EodRun.TriggerKind also accepts 'BACKFILL' (one EodRun per applied historical session, linked to its job).
--   2. A BACKFILL run may be PARTIAL *and* have written rows: a historical session (<= ObservedThrough) where some
--      tickers have no provider candle is written for the tickers that do, never counted as SUCCESS. Daily EOD runs
--      keep the original rule (PARTIAL/FAILED never write).
--   3. ops.EodRunItem.Outcome also accepts 'NO_HISTORY' (provider has no candle for the ticker on or before that date,
--      e.g. listed later) and 'REJECTED_ROW'.
--   4. New tables: BackfillJob (parameters, status, totals, backup evidence), BackfillFetch (checkpoint per ticker and
--      date chunk), BackfillStaging (validated provider candles before they reach the business tables), BackfillReject
--      (rows that failed validation), BackfillSession (checkpoint/outcome per session date).
SET NOCOUNT ON;
SET XACT_ABORT ON;
SET QUOTED_IDENTIFIER ON;
SET ANSI_NULLS ON;
GO
IF OBJECT_ID(N'ops.SchemaVersion',N'U') IS NULL OR NOT EXISTS(SELECT 1 FROM ops.SchemaVersion WHERE Version=2)
 OR EXISTS(SELECT 1 FROM sys.tables WHERE name=N'DailyPrice')
BEGIN
 RAISERROR(N'16_ops_schema_v3: needs a dedicated ops database at schema v2 (sql/14 + sql/15).',16,1);
 SET NOEXEC ON;
END;
GO
IF NOT EXISTS(SELECT 1 FROM ops.SchemaVersion WHERE Version=3)
BEGIN
 BEGIN TRANSACTION;
 ALTER TABLE ops.EodRun DROP CONSTRAINT CK_EodRun_Trigger;
 ALTER TABLE ops.EodRun WITH CHECK ADD CONSTRAINT CK_EodRun_Trigger CHECK(TriggerKind IN ('CLI','API','SCHEDULER','TEST','WEB','BACKFILL'));
 ALTER TABLE ops.EodRun DROP CONSTRAINT CK_EodRun_NoWriteUnlessSuccess;
 ALTER TABLE ops.EodRun WITH CHECK ADD CONSTRAINT CK_EodRun_NoWriteUnlessSuccess
  CHECK(Status IN ('SUCCESS','RUNNING') OR InsertedCount=0 OR (Status='PARTIAL' AND TriggerKind='BACKFILL' AND IsDryRun=0));
 ALTER TABLE ops.EodRunItem DROP CONSTRAINT CK_EodRunItem_Outcome;
 ALTER TABLE ops.EodRunItem WITH CHECK ADD CONSTRAINT CK_EodRunItem_Outcome
  CHECK(Outcome IN ('INSERTED','UNCHANGED','WOULD_INSERT','MISSING','REJECTED','CONFLICT','NOT_WRITTEN','NO_HISTORY','REJECTED_ROW'));

 CREATE TABLE ops.BackfillJob(
  JobId bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_BackfillJob PRIMARY KEY,
  JobRef varchar(36) NOT NULL CONSTRAINT UQ_BackfillJob_Ref UNIQUE,
  DatabaseName sysname NOT NULL,
  DatasetId int NOT NULL,
  SourceCode varchar(40) NOT NULL,
  StartDate date NOT NULL,
  EndDate date NOT NULL,
  EndDateSpec varchar(20) NOT NULL,                     -- 'latest' or the literal date requested
  TickersJson nvarchar(max) NOT NULL,                   -- tickers of this job (subset or the whole configured universe)
  UniverseSize int NOT NULL,
  IsFullUniverse bit NOT NULL,
  IsDryRun bit NOT NULL,
  Status varchar(30) NOT NULL CONSTRAINT CK_BackfillJob_Status CHECK(Status IN
   ('CREATED','FETCHING','APPLYING','COMPLETED','COMPLETED_WITH_GAPS','DRY_RUN_OK','FAILED','INTERRUPTED')),
  ErrorCode varchar(60) NULL,
  Message nvarchar(2000) NULL,
  SessionsPlanned int NULL,
  SessionsProcessed int NOT NULL CONSTRAINT DF_BackfillJob_SP DEFAULT(0),
  RowsInserted int NOT NULL CONSTRAINT DF_BackfillJob_RI DEFAULT(0),
  RowsUnchanged int NOT NULL CONSTRAINT DF_BackfillJob_RU DEFAULT(0),
  RowsWouldInsert int NOT NULL CONSTRAINT DF_BackfillJob_RW DEFAULT(0),
  RowsMissing int NOT NULL CONSTRAINT DF_BackfillJob_RM DEFAULT(0),
  RowsNoHistory int NOT NULL CONSTRAINT DF_BackfillJob_RN DEFAULT(0),
  RowsRejected int NOT NULL CONSTRAINT DF_BackfillJob_RR DEFAULT(0),
  ConflictCount int NOT NULL CONSTRAINT DF_BackfillJob_CC DEFAULT(0),
  FetchCalls int NOT NULL CONSTRAINT DF_BackfillJob_FC DEFAULT(0),
  FetchRetries int NOT NULL CONSTRAINT DF_BackfillJob_FR DEFAULT(0),
  ResumeCount int NOT NULL CONSTRAINT DF_BackfillJob_Res DEFAULT(0),
  BackupFile nvarchar(400) NULL,
  BackupVerifiedAtUtc datetime2(3) NULL,
  ProviderMeta nvarchar(4000) NULL,
  HostName nvarchar(128) NULL,
  TriggerKind varchar(20) NOT NULL CONSTRAINT CK_BackfillJob_Trigger CHECK(TriggerKind IN ('CLI','WEB','TEST')),
  CreatedAtUtc datetime2(3) NOT NULL CONSTRAINT DF_BackfillJob_At DEFAULT(SYSUTCDATETIME()),
  HeartbeatAtUtc datetime2(3) NULL,
  FinishedAtUtc datetime2(3) NULL,
  CONSTRAINT CK_BackfillJob_Range CHECK(StartDate<=EndDate),
  CONSTRAINT CK_BackfillJob_DryNoWrite CHECK(IsDryRun=0 OR RowsInserted=0),
  CONSTRAINT CK_BackfillJob_DryStatus CHECK(IsDryRun=1 OR Status<>'DRY_RUN_OK'),
  CONSTRAINT CK_BackfillJob_RealBackup CHECK(IsDryRun=1 OR TriggerKind='TEST' OR Status IN ('CREATED','FAILED','INTERRUPTED') OR BackupVerifiedAtUtc IS NOT NULL),
  CONSTRAINT CK_BackfillJob_Finished CHECK((Status IN ('COMPLETED','COMPLETED_WITH_GAPS','DRY_RUN_OK','FAILED','INTERRUPTED')) OR FinishedAtUtc IS NULL)
 );
 CREATE INDEX IX_BackfillJob_Dataset ON ops.BackfillJob(DatabaseName,DatasetId,JobId DESC);

 CREATE TABLE ops.BackfillFetch(
  JobId bigint NOT NULL CONSTRAINT FK_BackfillFetch_Job REFERENCES ops.BackfillJob(JobId),
  Ticker varchar(20) NOT NULL,
  ChunkStart date NOT NULL,
  ChunkEnd date NOT NULL,
  IsReference bit NOT NULL,
  Status varchar(20) NOT NULL CONSTRAINT CK_BackfillFetch_Status CHECK(Status IN ('FETCHED','FAILED')),
  Attempts int NOT NULL,
  RowsReceived int NOT NULL,
  RowsStaged int NOT NULL,
  RowsRejected int NOT NULL,
  RowsOutOfWindow int NOT NULL,
  FirstDate date NULL,
  LastDate date NULL,
  ErrorCode varchar(60) NULL,
  Message nvarchar(600) NULL,
  FetchedAtUtc datetime2(3) NOT NULL CONSTRAINT DF_BackfillFetch_At DEFAULT(SYSUTCDATETIME()),
  CONSTRAINT PK_BackfillFetch PRIMARY KEY(JobId,Ticker,ChunkStart),
  CONSTRAINT CK_BackfillFetch_Chunk CHECK(ChunkStart<=ChunkEnd),
  CONSTRAINT CK_BackfillFetch_Err CHECK(Status<>'FAILED' OR ErrorCode IS NOT NULL)
 );

 CREATE TABLE ops.BackfillStaging(
  JobId bigint NOT NULL CONSTRAINT FK_BackfillStaging_Job REFERENCES ops.BackfillJob(JobId),
  Ticker varchar(20) NOT NULL,
  TradeDate date NOT NULL,
  OpenPrice decimal(19,6) NOT NULL, HighPrice decimal(19,6) NOT NULL, LowPrice decimal(19,6) NOT NULL,
  ClosePrice decimal(19,6) NOT NULL, Volume bigint NOT NULL,
  StagedAtUtc datetime2(3) NOT NULL CONSTRAINT DF_BackfillStaging_At DEFAULT(SYSUTCDATETIME()),
  CONSTRAINT PK_BackfillStaging PRIMARY KEY(JobId,Ticker,TradeDate),
  CONSTRAINT CK_BackfillStaging_OHLCV CHECK(OpenPrice>0 AND HighPrice>0 AND LowPrice>0 AND ClosePrice>0 AND Volume>=0
   AND HighPrice>=OpenPrice AND HighPrice>=ClosePrice AND HighPrice>=LowPrice AND LowPrice<=OpenPrice AND LowPrice<=ClosePrice)
 );
 CREATE INDEX IX_BackfillStaging_Date ON ops.BackfillStaging(JobId,TradeDate) INCLUDE(Ticker);

 CREATE TABLE ops.BackfillReject(
  JobId bigint NOT NULL CONSTRAINT FK_BackfillReject_Job REFERENCES ops.BackfillJob(JobId),
  Ticker varchar(20) NOT NULL,
  ChunkStart date NOT NULL,
  RowNo int NOT NULL,
  RawTime nvarchar(40) NULL,
  TradeDate date NULL,
  Code varchar(40) NOT NULL,
  Detail nvarchar(400) NULL,
  CONSTRAINT PK_BackfillReject PRIMARY KEY(JobId,Ticker,ChunkStart,RowNo)
 );

 CREATE TABLE ops.BackfillSession(
  JobId bigint NOT NULL CONSTRAINT FK_BackfillSession_Job REFERENCES ops.BackfillJob(JobId),
  SessionDate date NOT NULL,
  Status varchar(20) NOT NULL CONSTRAINT CK_BackfillSession_Status CHECK(Status IN
   ('COMPLETE','PARTIAL','NOT_WRITTEN','DRY_RUN_OK','DRY_RUN_PARTIAL','FAILED')),
  ErrorCode varchar(60) NULL,
  EodRunId bigint NULL CONSTRAINT FK_BackfillSession_Run REFERENCES ops.EodRun(EodRunId),
  Requested int NOT NULL, Present int NOT NULL, Inserted int NOT NULL, Unchanged int NOT NULL, WouldInsert int NOT NULL,
  Missing int NOT NULL, NoHistory int NOT NULL, Rejected int NOT NULL, Conflicts int NOT NULL,
  MissingTickers nvarchar(400) NULL,
  Message nvarchar(1000) NULL,
  ProcessedAtUtc datetime2(3) NOT NULL CONSTRAINT DF_BackfillSession_At DEFAULT(SYSUTCDATETIME()),
  CONSTRAINT PK_BackfillSession PRIMARY KEY(JobId,SessionDate),
  CONSTRAINT CK_BackfillSession_Counts CHECK(Requested>=0 AND Present>=0 AND Inserted>=0 AND Unchanged>=0 AND WouldInsert>=0
   AND Missing>=0 AND NoHistory>=0 AND Rejected>=0 AND Conflicts>=0 AND Inserted+Unchanged+WouldInsert<=Present),
  CONSTRAINT CK_BackfillSession_Complete CHECK(Status NOT IN ('COMPLETE','DRY_RUN_OK')
   OR (Missing=0 AND NoHistory=0 AND Rejected=0 AND Conflicts=0 AND Present=Requested)),
  CONSTRAINT CK_BackfillSession_DryNoWrite CHECK(Status NOT IN ('DRY_RUN_OK','DRY_RUN_PARTIAL') OR Inserted=0)
 );

 INSERT ops.SchemaVersion(Version,Description) VALUES(3,N'Historical backfill: BackfillJob/Fetch/Staging/Reject/Session; TriggerKind BACKFILL; PARTIAL backfill writes; NO_HISTORY outcome');
 COMMIT;
END;
GO
SELECT N'OPS_SCHEMA_V3_READY' AS Result,DB_NAME() AS DatabaseName,(SELECT MAX(Version) FROM ops.SchemaVersion) AS SchemaVersion;
GO
SET NOEXEC OFF;
GO
