-- MarketLab VN30 - rollback ops schema v2 -> v1.
--   sqlcmd -S . -E -C -b -d MarketLabVN30_Ops -i sql\15_ops_schema_v2_rollback.sql
-- Refuses while rows with TriggerKind='WEB' exist (history is never rewritten silently).
SET NOCOUNT ON;
SET XACT_ABORT ON;
GO
IF EXISTS(SELECT 1 FROM ops.EodRun WHERE TriggerKind='WEB')
BEGIN
 RAISERROR(N'15 rollback refused: ops.EodRun contains WEB-triggered runs. Back up and decide explicitly how to keep them.',16,1);
 SET NOEXEC ON;
END;
GO
IF EXISTS(SELECT 1 FROM ops.SchemaVersion WHERE Version=2)
BEGIN
 BEGIN TRANSACTION;
 ALTER TABLE ops.EodRun DROP CONSTRAINT CK_EodRun_Trigger;
 ALTER TABLE ops.EodRun WITH CHECK ADD CONSTRAINT CK_EodRun_Trigger CHECK(TriggerKind IN ('CLI','API','SCHEDULER','TEST'));
 DELETE ops.SchemaVersion WHERE Version=2;
 COMMIT;
END;
GO
SELECT N'OPS_SCHEMA_V1_RESTORED' AS Result,(SELECT MAX(Version) FROM ops.SchemaVersion) AS SchemaVersion;
GO
SET NOEXEC OFF;
GO
