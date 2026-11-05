-- MarketLab VN30 - rollback of ops schema v1. DESTROYS the EOD audit history in this ops database.
-- Back the ops database up first. Requires the sqlcmd variable ConfirmDropOps=YES:
--   sqlcmd -S . -E -C -b -d MarketLabVN30_Ops -v ConfirmDropOps=YES -i sql\14_ops_database_rollback.sql
-- Business databases are not touched.
SET NOCOUNT ON;
SET XACT_ABORT ON;
GO
IF N'$(ConfirmDropOps)'<>N'YES' OR EXISTS(SELECT 1 FROM sys.tables WHERE name=N'DailyPrice')
BEGIN
 RAISERROR(N'14_ops_database_rollback: refused (needs -v ConfirmDropOps=YES on a dedicated ops database).',16,1);
 SET NOEXEC ON;
END;
GO
BEGIN TRANSACTION;
DROP TABLE IF EXISTS ops.EvaluationSnapshot;
DROP TABLE IF EXISTS ops.PriceLoadLineage;
DROP TABLE IF EXISTS ops.PriceReconciliation;
DROP TABLE IF EXISTS ops.EodRunItem;
DROP TABLE IF EXISTS ops.EodRun;
DROP TABLE IF EXISTS ops.EodConfig;
DROP TABLE IF EXISTS ops.SchemaVersion;
COMMIT;
GO
SELECT N'OPS_SCHEMA_V1_ROLLED_BACK' AS Result,DB_NAME() AS DatabaseName;
GO
SET NOEXEC OFF;
GO
