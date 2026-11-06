-- 02. Quan he PK/FK giua 13 bang (16 khoa ngoai) - doc tu danh muc he thong
USE MarketLabVN30_Demo;
SELECT fk.name AS ForeignKey,
       OBJECT_NAME(fk.parent_object_id) AS ChildTable,
       STRING_AGG(pc.name, ', ') WITHIN GROUP (ORDER BY fkc.constraint_column_id) AS ChildColumns,
       OBJECT_NAME(fk.referenced_object_id) AS ParentTable,
       STRING_AGG(rc.name, ', ') WITHIN GROUP (ORDER BY fkc.constraint_column_id) AS ParentColumns
FROM sys.foreign_keys fk
JOIN sys.foreign_key_columns fkc ON fkc.constraint_object_id = fk.object_id
JOIN sys.columns pc ON pc.object_id = fkc.parent_object_id AND pc.column_id = fkc.parent_column_id
JOIN sys.columns rc ON rc.object_id = fkc.referenced_object_id AND rc.column_id = fkc.referenced_column_id
GROUP BY fk.name, fk.parent_object_id, fk.referenced_object_id
ORDER BY ParentTable, ChildTable;
