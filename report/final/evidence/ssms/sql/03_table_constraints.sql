-- 03. Rang buoc PK / UNIQUE / FK / CHECK cua 5 bang tieu bieu
USE MarketLabVN30_Demo;
WITH k AS (
  SELECT OBJECT_NAME(parent_object_id) AS TableName, type_desc AS Kind, name FROM sys.key_constraints
  UNION ALL SELECT OBJECT_NAME(parent_object_id), type_desc, name FROM sys.foreign_keys
  UNION ALL SELECT OBJECT_NAME(parent_object_id), type_desc, name FROM sys.check_constraints)
SELECT TableName, Kind, COUNT(*) AS N, STRING_AGG(name, ', ') AS Constraints
FROM k
WHERE TableName IN ('Stock','Dataset','DailyPrice','ModelRun','Prediction')
GROUP BY TableName, Kind
ORDER BY TableName, Kind;
