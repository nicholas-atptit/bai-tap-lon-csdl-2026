-- Rollback of ops schema v3 (historical backfill). Ops database only:
--   sqlcmd -S . -E -C -b -d MarketLabVN30_Ops -i sql\16_ops_schema_v3_backfill_rollback.sql
-- Refuses (changes nothing) when any backfill audit row exists: audit history is never dropped silently.
-- Business data written by backfill runs stays in the business database; this script does not touch it.
SET NOCOUNT ON;
SET XACT_ABORT ON;
GO
IF NOT EXISTS(SELECT 1 FROM ops.SchemaVersion WHERE Version=3)
BEGIN
 RAISERROR(N'16 rollback: schema v3 not installed; nothing to do.',10,1);
 SET NOEXEC ON;
END;
GO
IF EXISTS(SELECT 1 FROM ops.BackfillJob) OR EXISTS(SELECT 1 FROM ops.EodRun WHERE TriggerKind='BACKFILL')
 OR EXISTS(SELECT 1 FROM ops.EodRunItem WHERE Outcome IN ('NO_HISTORY','REJECTED_ROW'))
BEGIN
 RAISERROR(N'16 rollback refused: backfill audit rows exist (export/backup them and remove deliberately first).',16,1);
 SET NOEXEC ON;
END;
GO
BEGIN TRANSACTION;
DROP TABLE ops.BackfillSession;
DROP TABLE ops.BackfillReject;
DROP TABLE ops.BackfillStaging;
DROP TABLE ops.BackfillFetch;
DROP TABLE ops.BackfillJob;
ALTER TABLE ops.EodRunItem DROP CONSTRAINT CK_EodRunItem_Outcome;
ALTER TABLE ops.EodRunItem WITH CHECK ADD CONSTRAINT CK_EodRunItem_Outcome CHECK(Outcome IN ('INSERTED','UNCHANGED','WOULD_INSERT','MISSING','REJECTED','CONFLICT','NOT_WRITTEN'));
ALTER TABLE ops.EodRun DROP CONSTRAINT CK_EodRun_NoWriteUnlessSuccess;
ALTER TABLE ops.EodRun WITH CHECK ADD CONSTRAINT CK_EodRun_NoWriteUnlessSuccess CHECK(Status IN ('SUCCESS','RUNNING') OR InsertedCount=0);
ALTER TABLE ops.EodRun DROP CONSTRAINT CK_EodRun_Trigger;
ALTER TABLE ops.EodRun WITH CHECK ADD CONSTRAINT CK_EodRun_Trigger CHECK(TriggerKind IN ('CLI','API','SCHEDULER','TEST','WEB'));
DELETE ops.SchemaVersion WHERE Version=3;
COMMIT;
GO
SELECT N'OPS_SCHEMA_V3_ROLLED_BACK' AS Result,(SELECT MAX(Version) FROM ops.SchemaVersion) AS SchemaVersion;
GO
SET NOEXEC OFF;
GO
