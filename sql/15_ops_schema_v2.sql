-- MarketLab VN30 - ops database schema v2 (run on the dedicated ops database only).
--   sqlcmd -S . -E -C -b -d MarketLabVN30_Ops -i sql\15_ops_schema_v2.sql
-- Change: ops.EodRun.TriggerKind also accepts 'WEB' (EOD started from the server-side web form, which replaced the
-- former REST endpoint; historical 'API' rows stay valid). Idempotent. Rollback: sql/15_ops_schema_v2_rollback.sql.
SET NOCOUNT ON;
SET XACT_ABORT ON;
GO
IF OBJECT_ID(N'ops.SchemaVersion',N'U') IS NULL OR NOT EXISTS(SELECT 1 FROM ops.SchemaVersion WHERE Version=1)
 OR EXISTS(SELECT 1 FROM sys.tables WHERE name=N'DailyPrice')
BEGIN
 RAISERROR(N'15_ops_schema_v2: needs a dedicated ops database at schema v1 (sql/14_ops_database.sql).',16,1);
 SET NOEXEC ON;
END;
GO
IF NOT EXISTS(SELECT 1 FROM ops.SchemaVersion WHERE Version=2)
BEGIN
 BEGIN TRANSACTION;
 ALTER TABLE ops.EodRun DROP CONSTRAINT CK_EodRun_Trigger;
 ALTER TABLE ops.EodRun WITH CHECK ADD CONSTRAINT CK_EodRun_Trigger CHECK(TriggerKind IN ('CLI','API','SCHEDULER','TEST','WEB'));
 INSERT ops.SchemaVersion(Version,Description) VALUES(2,N'TriggerKind WEB (server-side web form replaces REST endpoint)');
 COMMIT;
END;
GO
SELECT N'OPS_SCHEMA_V2_READY' AS Result,DB_NAME() AS DatabaseName,(SELECT MAX(Version) FROM ops.SchemaVersion) AS SchemaVersion;
GO
SET NOEXEC OFF;
GO
