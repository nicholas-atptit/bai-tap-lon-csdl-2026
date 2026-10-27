# Bộ truy vấn nghiệp vụ và kết quả thực chạy

Thực thi bằng sqlcmd trên SQL Server 2025 Developer, cả demo và nghiên cứu. Số dòng là số hàng thực trả về, không phải kết quả dự kiến. Số 0 hợp lệ với truy vấn phát hiện thiếu dữ liệu khi không có lỗi. Các log chứa bảng kết quả; không dùng ảnh SSMS dựng lại.

## Q01 — SELECT: Danh muc co phieu va tinh trang metadata.

Mục đích: Danh muc co phieu va tinh trang metadata.

```sql
SELECT StockId,Ticker,CompanyName,IndustryId,IsSynthetic FROM dbo.Stock ORDER BY Ticker;
```

Kết quả: demo 8 dòng; nghiên cứu 30 dòng; PASS trên cả hai. Log: `tests/evidence/demo_Q01.log` và `tests/evidence/research_Q01.log`. Phép toán giữ đúng phạm vi khóa nguồn; không xem dữ liệu thiếu là số 0.

## Q02 — INNER JOIN: Gia gan nhat kem don vi va pham vi nguon.

Mục đích: Gia gan nhat kem don vi va pham vi nguon.

```sql
SELECT s.Ticker,p.TradeDate,p.ClosePrice,d.PriceUnit FROM dbo.vw_LatestStockPrice p INNER JOIN dbo.Stock s ON s.StockId=p.StockId INNER JOIN dbo.Dataset d ON d.DatasetId=p.DatasetId ORDER BY s.Ticker;
```

Kết quả: demo 8 dòng; nghiên cứu 30 dòng; PASS trên cả hai. Log: `tests/evidence/demo_Q02.log` và `tests/evidence/research_Q02.log`. Phép toán giữ đúng phạm vi khóa nguồn; không xem dữ liệu thiếu là số 0.

## Q03 — LEFT JOIN: Co phieu chua co thong tin phan nganh.

Mục đích: Co phieu chua co thong tin phan nganh.

```sql
SELECT s.Ticker,i.IndustryName FROM dbo.Stock s LEFT JOIN dbo.Industry i ON i.IndustryId=s.IndustryId WHERE i.IndustryId IS NULL ORDER BY s.Ticker;
```

Kết quả: demo 0 dòng; nghiên cứu 30 dòng; PASS trên cả hai. Log: `tests/evidence/demo_Q03.log` và `tests/evidence/research_Q03.log`. Phép toán giữ đúng phạm vi khóa nguồn; không xem dữ liệu thiếu là số 0.

## Q04 — FULL JOIN: Doi chieu pham vi co gia va pham vi co du bao.

Mục đích: Doi chieu pham vi co gia va pham vi co du bao.

```sql
WITH P AS(SELECT DISTINCT StockId FROM dbo.DailyPrice),F AS(SELECT DISTINCT StockId FROM dbo.Prediction)
SELECT COALESCE(P.StockId,F.StockId) AS StockId,CASE WHEN P.StockId IS NULL THEN 0 ELSE 1 END AS HasPrice,CASE WHEN F.StockId IS NULL THEN 0 ELSE 1 END AS HasForecast FROM P FULL JOIN F ON F.StockId=P.StockId ORDER BY StockId;
```

Kết quả: demo 8 dòng; nghiên cứu 30 dòng; PASS trên cả hai. Log: `tests/evidence/demo_Q04.log` và `tests/evidence/research_Q04.log`. Phép toán giữ đúng phạm vi khóa nguồn; không xem dữ liệu thiếu là số 0.

## Q05 — GROUP BY: Khoi luong trung binh theo nganh; UNKNOWN khong duoc xem la 0.

Mục đích: Khoi luong trung binh theo nganh; UNKNOWN khong duoc xem la 0.

```sql
SELECT COALESCE(i.IndustryName,N'Chua co metadata nganh') AS IndustryName,COUNT_BIG(*) AS PriceRows,AVG(CONVERT(decimal(25,2),p.Volume)) AS AverageVolume
FROM dbo.DailyPrice p JOIN dbo.Stock s ON s.StockId=p.StockId LEFT JOIN dbo.Industry i ON i.IndustryId=s.IndustryId GROUP BY i.IndustryName;
```

Kết quả: demo 2 dòng; nghiên cứu 1 dòng; PASS trên cả hai. Log: `tests/evidence/demo_Q05.log` và `tests/evidence/research_Q05.log`. Phép toán giữ đúng phạm vi khóa nguồn; không xem dữ liệu thiếu là số 0.

## Q06 — HAVING: Ma co it nhat 20 phien gia trong dataset.

Mục đích: Ma co it nhat 20 phien gia trong dataset.

```sql
SELECT DatasetId,StockId,COUNT(*) AS ObservedSessions FROM dbo.DailyPrice GROUP BY DatasetId,StockId HAVING COUNT(*)>=20 ORDER BY DatasetId,StockId;
```

Kết quả: demo 8 dòng; nghiên cứu 30 dòng; PASS trên cả hai. Log: `tests/evidence/demo_Q06.log` và `tests/evidence/research_Q06.log`. Phép toán giữ đúng phạm vi khóa nguồn; không xem dữ liệu thiếu là số 0.

## Q07 — Subquery: Phien co khoi luong cao hon trung binh cung ma/dataset.

Mục đích: Phien co khoi luong cao hon trung binh cung ma/dataset.

```sql
SELECT p.DatasetId,p.StockId,p.TradeDate,p.Volume FROM dbo.DailyPrice p WHERE p.Volume>(SELECT AVG(CONVERT(decimal(25,2),q.Volume)) FROM dbo.DailyPrice q WHERE q.DatasetId=p.DatasetId AND q.StockId=p.StockId) ORDER BY p.StockId,p.TradeDate;
```

Kết quả: demo 136 dòng; nghiên cứu 478 dòng; PASS trên cả hai. Log: `tests/evidence/demo_Q07.log` và `tests/evidence/research_Q07.log`. Phép toán giữ đúng phạm vi khóa nguồn; không xem dữ liệu thiếu là số 0.

## Q08 — UNION: Tap ma can quan ly tu gia hoac du bao (loai trung).

Mục đích: Tap ma can quan ly tu gia hoac du bao (loai trung).

```sql
SELECT StockId FROM dbo.DailyPrice UNION SELECT StockId FROM dbo.Prediction;
```

Kết quả: demo 8 dòng; nghiên cứu 30 dòng; PASS trên cả hai. Log: `tests/evidence/demo_Q08.log` và `tests/evidence/research_Q08.log`. Phép toán giữ đúng phạm vi khóa nguồn; không xem dữ liệu thiếu là số 0.

## Q09 — INTERSECT: Co phieu duoc ca hai run dau tien du bao.

Mục đích: Co phieu duoc ca hai run dau tien du bao.

```sql
SELECT StockId FROM dbo.Prediction WHERE RunId=(SELECT MIN(RunId) FROM dbo.ModelRun)
INTERSECT SELECT StockId FROM dbo.Prediction WHERE RunId=(SELECT MAX(RunId) FROM dbo.ModelRun);
```

Kết quả: demo 8 dòng; nghiên cứu 30 dòng; PASS trên cả hai. Log: `tests/evidence/demo_Q09.log` và `tests/evidence/research_Q09.log`. Phép toán giữ đúng phạm vi khóa nguồn; không xem dữ liệu thiếu là số 0.

## Q10 — EXCEPT: Ma co gia nhung khong co du bao.

Mục đích: Ma co gia nhung khong co du bao.

```sql
SELECT StockId FROM dbo.DailyPrice EXCEPT SELECT StockId FROM dbo.Prediction;
```

Kết quả: demo 0 dòng; nghiên cứu 0 dòng; PASS trên cả hai. Log: `tests/evidence/demo_Q10.log` và `tests/evidence/research_Q10.log`. Phép toán giữ đúng phạm vi khóa nguồn; không xem dữ liệu thiếu là số 0.

## Q11 — LIKE: Tim ma theo ky tu A trong danh muc.

Mục đích: Tim ma theo ky tu A trong danh muc.

```sql
SELECT StockId,Ticker FROM dbo.Stock WHERE Ticker LIKE '%A%' ORDER BY Ticker;
```

Kết quả: demo 0 dòng; nghiên cứu 3 dòng; PASS trên cả hai. Log: `tests/evidence/demo_Q11.log` và `tests/evidence/research_Q11.log`. Phép toán giữ đúng phạm vi khóa nguồn; không xem dữ liệu thiếu là số 0.

## Q12 — BETWEEN: Gia trong 7 ngay lich dau tien cua tap du lieu.

Mục đích: Gia trong 7 ngay lich dau tien cua tap du lieu.

```sql
SELECT p.StockId,p.TradeDate,p.ClosePrice FROM dbo.DailyPrice p WHERE p.TradeDate BETWEEN (SELECT MIN(TradeDate) FROM dbo.DailyPrice) AND DATEADD(day,6,(SELECT MIN(TradeDate) FROM dbo.DailyPrice)) ORDER BY p.StockId,p.TradeDate;
```

Kết quả: demo 40 dòng; nghiên cứu 150 dòng; PASS trên cả hai. Log: `tests/evidence/demo_Q12.log` và `tests/evidence/research_Q12.log`. Phép toán giữ đúng phạm vi khóa nguồn; không xem dữ liệu thiếu là số 0.

## Q13 — TOP / function: 5 ma tang gia nguon manh nhat tu dau den cuoi tap.

Mục đích: 5 ma tang gia nguon manh nhat tu dau den cuoi tap.

```sql
WITH R AS(SELECT DatasetId,StockId,MIN(TradeDate) AS D0,MAX(TradeDate) AS D1 FROM dbo.DailyPrice GROUP BY DatasetId,StockId)
SELECT TOP(5) s.Ticker,dbo.fn_CalculateReturn(a.ClosePrice,z.ClosePrice) AS SourceCloseReturnPct
FROM R JOIN dbo.Stock s ON s.StockId=R.StockId JOIN dbo.DailyPrice a ON a.DatasetId=R.DatasetId AND a.StockId=R.StockId AND a.TradeDate=R.D0
JOIN dbo.DailyPrice z ON z.DatasetId=R.DatasetId AND z.StockId=R.StockId AND z.TradeDate=R.D1 ORDER BY SourceCloseReturnPct DESC,s.Ticker;
```

Kết quả: demo 5 dòng; nghiên cứu 5 dòng; PASS trên cả hai. Log: `tests/evidence/demo_Q13.log` và `tests/evidence/research_Q13.log`. Phép toán giữ đúng phạm vi khóa nguồn; không xem dữ liệu thiếu là số 0.

## Q14 — Ham huong: Minh hoa du bao huong loi suat 3 trang thai; khong thay the Brier.

Mục đích: Minh hoa du bao huong loi suat 3 trang thai; khong thay the Brier.

```sql
SELECT dbo.fn_CheckPredictionDirection(1.0,2.0) AS PositiveMatch,dbo.fn_CheckPredictionDirection(0,0) AS FlatMatch,dbo.fn_CheckPredictionDirection(0,1) AS FlatMismatch;
```

Kết quả: demo 1 dòng; nghiên cứu 1 dòng; PASS trên cả hai. Log: `tests/evidence/demo_Q14.log` và `tests/evidence/research_Q14.log`. Phép toán giữ đúng phạm vi khóa nguồn; không xem dữ liệu thiếu là số 0.

## Q15 — View: Ket qua phan loai theo run va horizon, chi du lieu da truong thanh.

Mục đích: Ket qua phan loai theo run va horizon, chi du lieu da truong thanh.

```sql
SELECT r.RunCode,m.ModelCode,p.* FROM dbo.vw_ModelPerformance p JOIN dbo.ModelRun r ON r.RunId=p.RunId JOIN dbo.ForecastModel m ON m.ModelId=p.ModelId ORDER BY p.RunId;
```

Kết quả: demo 2 dòng; nghiên cứu 2 dòng; PASS trên cả hai. Log: `tests/evidence/demo_Q15.log` và `tests/evidence/research_Q15.log`. Phép toán giữ đúng phạm vi khóa nguồn; không xem dữ liệu thiếu là số 0.

## Q16 — LEFT JOIN: Kiem tra thieu gia tren lich dataset trong pham vi da quan sat.

Mục đích: Kiem tra thieu gia tren lich dataset trong pham vi da quan sat.

```sql
SELECT u.DatasetId,u.StockId,t.TradeDate FROM dbo.vw_StudyUniverse u JOIN dbo.TradingDay t ON t.DatasetId=u.DatasetId
JOIN dbo.Dataset d ON d.DatasetId=t.DatasetId LEFT JOIN dbo.DailyPrice p ON p.DatasetId=u.DatasetId AND p.StockId=u.StockId AND p.TradeDate=t.TradeDate
WHERE t.TradeDate BETWEEN u.FirstObservedDate AND d.ObservedThrough AND p.StockId IS NULL ORDER BY u.StockId,t.TradeDate;
```

Kết quả: demo 0 dòng; nghiên cứu 0 dòng; PASS trên cả hai. Log: `tests/evidence/demo_Q16.log` và `tests/evidence/research_Q16.log`. Phép toán giữ đúng phạm vi khóa nguồn; không xem dữ liệu thiếu là số 0.
