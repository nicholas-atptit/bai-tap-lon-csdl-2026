-- MarketLab VN30 - rollback of EOD extension v1 on ONE business database.
-- sqlcmd -S . -E -C -b -d <Database> -i sql\13_eod_extension_rollback.sql
-- Restores dbo.tr_Dataset_Guard to the exact original text of sql/02_constraints_indexes.sql,
-- drops ops.usp_EodApplySession and the empty [ops] schema, removes the extended property.
-- It does NOT undo data already committed by EOD runs (prices, TradingDay rows, ObservedThrough moves):
-- those are business rows protected by the original rules; restore the pre-migration backup if needed.
SET NOCOUNT ON;
SET XACT_ABORT ON;
SET QUOTED_IDENTIFIER ON;
SET ANSI_NULLS ON;
GO
IF DB_NAME() IN (N'master',N'model',N'msdb',N'tempdb',N'MarketLabVN30_Demo')
BEGIN
 RAISERROR(N'13_eod_extension_rollback: refused on this database.',16,1);
 SET NOEXEC ON;
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
DROP PROCEDURE IF EXISTS ops.usp_EodApplySession;
GO
IF SCHEMA_ID(N'ops') IS NOT NULL AND NOT EXISTS(SELECT 1 FROM sys.objects WHERE schema_id=SCHEMA_ID(N'ops'))
 AND NOT EXISTS(SELECT 1 FROM sys.types WHERE schema_id=SCHEMA_ID(N'ops'))
 EXEC(N'DROP SCHEMA ops;');
GO
IF EXISTS(SELECT 1 FROM sys.extended_properties WHERE class=0 AND name=N'MarketLabEodExtension')
 EXEC sys.sp_dropextendedproperty @name=N'MarketLabEodExtension';
GO
SELECT N'EOD_EXTENSION_ROLLED_BACK' AS Result,DB_NAME() AS DatabaseName,SCHEMA_ID(N'ops') AS OpsSchemaId;
GO
SET NOEXEC OFF;
GO
