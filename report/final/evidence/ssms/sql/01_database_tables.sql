-- 01. Database MarketLabVN30_Demo: 13 bang nghiep vu (schema dbo)
USE MarketLabVN30_Demo;
SELECT t.name AS TableName,
       (SELECT COUNT(*) FROM sys.columns c WHERE c.object_id = t.object_id) AS Columns,
       (SELECT SUM(p.rows) FROM sys.partitions p WHERE p.object_id = t.object_id AND p.index_id IN (0,1)) AS [Rows]
FROM sys.tables t
WHERE t.schema_id = SCHEMA_ID('dbo')
ORDER BY t.name;
