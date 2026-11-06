-- MarketLab VN30 - READ-ONLY preflight before applying sql/13_eod_extension.sql.
-- sqlcmd -S . -E -C -b -W -s "|" -d <Database> -i sql\13_eod_preflight.sql
-- Writes nothing. Exit code 1 (THROW 52100) if a blocking check fails.
SET NOCOUNT ON;
DECLARE @C TABLE(Item nvarchar(120),Actual nvarchar(200),Expected nvarchar(200),Blocking bit,Status varchar(6));
DECLARE @LastFullBackup datetime=(SELECT MAX(b.backup_finish_date) FROM msdb.dbo.backupset b WHERE b.database_name=DB_NAME() AND b.type='D');
INSERT @C(Item,Actual,Expected,Blocking) VALUES
 (N'Database is not the public demo',DB_NAME(),N'<> MarketLabVN30_Demo',1),
 (N'MarketLabSchema property',ISNULL((SELECT CONVERT(nvarchar(50),value) FROM sys.extended_properties WHERE class=0 AND name=N'MarketLabSchema'),N'(missing)'),N'1.0',1),
 (N'dbo business tables',CONVERT(nvarchar(20),(SELECT COUNT(*) FROM sys.tables WHERE is_ms_shipped=0 AND SCHEMA_NAME(schema_id)=N'dbo')),N'13',1),
 (N'All user tables (any schema)',CONVERT(nvarchar(20),(SELECT COUNT(*) FROM sys.tables WHERE is_ms_shipped=0)),N'13',1),
 (N'Disabled/untrusted FK or CHECK',CONVERT(nvarchar(20),(SELECT COUNT(*) FROM sys.foreign_keys WHERE is_disabled=1 OR is_not_trusted=1)+(SELECT COUNT(*) FROM sys.check_constraints WHERE is_disabled=1 OR is_not_trusted=1)),N'0',1),
 (N'Disabled triggers',CONVERT(nvarchar(20),(SELECT COUNT(*) FROM sys.triggers WHERE is_ms_shipped=0 AND is_disabled=1)),N'0',1),
 (N'Open transactions',CONVERT(nvarchar(20),@@TRANCOUNT),N'0',1),
 (N'usp_InsertDailyPrice present',CASE WHEN OBJECT_ID(N'dbo.usp_InsertDailyPrice',N'P') IS NULL THEN N'no' ELSE N'yes' END,N'yes',1),
 (N'SYNTHETIC datasets (EOD writes need REAL_PRIVATE)',CONVERT(nvarchar(20),(SELECT COUNT(*) FROM dbo.Dataset WHERE DataKind='SYNTHETIC')),N'0 (informational)',0),
 (N'REAL_PRIVATE datasets',CONVERT(nvarchar(20),(SELECT COUNT(*) FROM dbo.Dataset WHERE DataKind='REAL_PRIVATE')),N'>=1 for EOD',0),
 (N'EOD extension already applied',ISNULL((SELECT CONVERT(nvarchar(10),value) FROM sys.extended_properties WHERE class=0 AND name=N'MarketLabEodExtension'),N'no'),N'informational',0),
 (N'Last FULL backup (msdb)',ISNULL(CONVERT(nvarchar(30),@LastFullBackup,126),N'NONE'),N'recent, before migration',0),
 (N'Compatibility level (OPENJSON needs >=130)',CONVERT(nvarchar(10),(SELECT compatibility_level FROM sys.databases WHERE name=DB_NAME())),N'>=130',1);
UPDATE @C SET Status=CASE
 WHEN Item=N'Database is not the public demo' THEN CASE WHEN Actual<>N'MarketLabVN30_Demo' THEN 'PASS' ELSE 'FAIL' END
 WHEN Item=N'Compatibility level (OPENJSON needs >=130)' THEN CASE WHEN TRY_CONVERT(int,Actual)>=130 THEN 'PASS' ELSE 'FAIL' END
 WHEN Blocking=0 THEN 'INFO'
 WHEN Actual=Expected THEN 'PASS' ELSE 'FAIL' END;
SELECT DB_NAME() AS DatabaseName,@@SERVERNAME AS ServerName,SYSUTCDATETIME() AS CheckedAtUtc;
SELECT Item,Actual,Expected,Status FROM @C ORDER BY Blocking DESC,Item;
SELECT DatasetId,DatasetCode,DataKind,PriceBasis,ObservedThrough FROM dbo.Dataset ORDER BY DatasetId;
IF @LastFullBackup IS NULL OR @LastFullBackup<DATEADD(day,-1,GETDATE())
 SELECT N'WARNING: no FULL backup in the last 24h. Back up before migrating a database holding real data:' AS Advice,
  CONCAT(N'BACKUP DATABASE [',DB_NAME(),N'] TO DISK=N''<path>\',DB_NAME(),N'_pre_eod_v1.bak'' WITH COPY_ONLY, CHECKSUM, INIT;') AS Command;
IF EXISTS(SELECT 1 FROM @C WHERE Status='FAIL') THROW 52100,N'EOD extension preflight FAIL. Nothing changed.',1;
SELECT N'EOD_PREFLIGHT_PASS' AS Result;
