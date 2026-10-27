---
title: "MARKETLAB VN30"
subtitle: "Thiết kế và triển khai hệ thống cơ sở dữ liệu quản lý thị trường và đánh giá dự báo cổ phiếu"
date: "Báo cáo bài tập lớn Hệ quản trị cơ sở dữ liệu — 27/10/2026"
lang: vi-VN
---

<!-- maintained-live-report -->

# 1. Giới thiệu đề tài

MarketLab VN30 tổ chức dữ liệu thị trường và dự báo chứng khoán trong cơ sở dữ liệu quan hệ, phục vụ tra cứu và đối chiếu kết quả dự báo đã có. Trọng tâm học phần là thiết kế 3NF, ràng buộc, truy vấn, hàm, thủ tục và transaction. Dự án không huấn luyện mô hình mới hoặc xây dựng ứng dụng web.

Hai phạm vi được triển khai: một demo dùng dữ liệu mô phỏng để giảng viên có thể chạy độc lập, và một database nghiên cứu cục bộ dùng tập con VN30 thật có lineage. Các con số thực nghiệm trong báo cáo lấy từ SQL Server và được tính lại độc lập bằng Python; không mô phỏng ảnh SSMS.

# 2. Phân tích yêu cầu hệ thống



|Mã|Chức năng|Dữ liệu/đối tượng|
|---|---|---|
|M01|Quản lý danh mục thị trường/ngành/mã|Market, Industry, Stock|
|M02|Quản lý phạm vi nguồn và lịch phiên|Dataset, TradingDay|
|M03|Thêm giá; cập nhật khi có yêu cầu rõ ràng|usp_InsertDailyPrice; AllowUpdate mặc định 0|
|M04|Quản lý chỉ số và thành phần có hiệu lực|StockIndex, IndexMembership|
|M05|Quản lý mô hình, mục tiêu, cấu hình run|ForecastModel, TargetDefinition, ModelRun|
|M06|Thêm và chống trùng dự báo|ForecastOrigin, Prediction, usp_AddPrediction|
|M07|Nạp theo batch và ghi receipt|import_data.py, transaction, kiểm tra xung đột|

## Chức năng phân tích

|Mã|Chức năng|Điều kiện|
|---|---|---|
|A01|Giá gần nhất trong dataset|Không đồng nhất với ngày hiện tại|
|A02|Tra cứu ngành, mã, khoảng ngày, khối lượng|Giữ metadata UNKNOWN/NULL hiển thị|
|A03|Tính thay đổi Close nguồn|Không gọi là total return hay giá đã điều chỉnh|
|A04|Đánh giá Accuracy, Brier, natural log loss|Đủ hai giá đầu/cuối và mục tiêu đã quan sát|
|A05|So sánh các run|Cùng dataset, TargetDefinition và giao các khóa (StockId,OriginDate,TargetDate)|
|A06|Kiểm tra thiếu giá hoặc thiếu dự báo|LEFT/FULL JOIN, EXCEPT; không tự điền giá|

## Quy tắc nghiệp vụ

OHLC dương, High không thấp hơn Open/Low/Close, Low không cao hơn Open/High/Close; Volume không âm. Mỗi mã/ngày có tối đa một giá trong dataset. Ngày mục tiêu là phiên thứ h tiếp theo trong lịch dataset. Dự báo phải có ngày gốc sau validation; nguồn là đánh giá retrospective ngoài mẫu, không phải bằng chứng kiểm định chưa từng quan sát. Xác suất nằm trong [0,1]; phân lớp 1 khi p ≥ threshold. Nhãn thực tế bằng 1 khi Close mục tiêu > Close gốc, ngược lại bằng 0 kể cả hòa. ActualLabel được tính khi TargetDate ≤ AsOfDate và ≤ ObservedThrough, đồng thời có đủ giá. Không cần biết giá tương lai khi thêm một dự báo chưa trưởng thành.

Khoảng thành phần chỉ số không chồng lấn cho cùng chỉ số/mã. Không xóa dây chuyền dữ liệu. Không sửa cấu hình run đã sử dụng hoặc lịch làm thay đổi horizon đã lưu. Bản ghi nhập lại giống hệt được bỏ qua; cùng khóa nhưng khác giá trị làm rollback batch, không âm thầm ghi đè. Chỉ cập nhật giá qua thủ tục với AllowUpdate=1 khi chủ động sửa dữ liệu quản lý.



# 3. Mô hình thực thể–liên kết

![ERD vật lý của MarketLab VN30; bản SVG/PDF đầy đủ nằm trong docs/diagrams.](../docs/diagrams/marketlab_erd.png)

Mô hình gồm 13 thực thể. Market liên kết Stock, Dataset và StockIndex; Industry là metadata tùy chọn của Stock. TradingDay và DailyPrice quản lý lịch/giá theo dataset. StockIndex và Stock có quan hệ N–N qua IndexMembership. ForecastModel, TargetDefinition và Dataset xác định ModelRun; ForecastOrigin giữ ngày mục tiêu theo lần chạy/ngày gốc; Prediction giữ xác suất theo mã. Tất cả quan hệ FK và bội số trong sơ đồ được sinh từ schema thực.

# 4. Thiết kế cơ sở dữ liệu

|Bảng|Vai trò|
|---|---|
|Market|Danh mục thị trường và đồng tiền tham chiếu.|
|Industry|Danh mục ngành có nguồn hoặc được ghi rõ mô phỏng; không tự gán ngành cho dữ liệu thật.|
|Stock|Định danh mã chứng khoán trong thị trường; tên công ty và ngành có thể chưa biết.|
|Dataset|Phạm vi nguồn, đơn vị giá, loại dữ liệu và ngày đã quan sát; tách các phiên bản dữ liệu.|
|TradingDay|Lịch phiên riêng cho từng dataset, không giao cắt lịch của các thị trường.|
|DailyPrice|OHLCV của một mã tại một phiên trong một dataset.|
|StockIndex|Danh mục chỉ số trong thị trường.|
|IndexMembership|Quan hệ N–N chỉ số–cổ phiếu có khoảng hiệu lực đóng [ValidFrom, ValidTo].|
|ForecastModel|Định danh phương pháp dự báo, không lưu xác suất ở mức mô hình.|
|TargetDefinition|Định nghĩa biến mục tiêu, đơn vị đầu ra và số phiên dự báo.|
|ModelRun|Cấu hình một lần chạy: dataset, mục tiêu, development/validation, threshold và nguồn.|
|ForecastOrigin|Ánh xạ một lần chạy và ngày gốc sang ngày mục tiêu; loại phụ thuộc bộ phận khỏi Prediction.|
|Prediction|Xác suất tăng giá của một mã tại một ngày gốc trong một lần chạy.|

Giá dùng DECIMAL(19,6), xác suất DECIMAL(19,16), khối lượng BIGINT, ngày dùng DATE, thời gian nạp DATETIME2(0). FLOAT chỉ dùng trung gian khi tính bình phương/logarit trong chỉ tiêu, không dùng lưu giá hoặc xác suất nguồn. Từ điển dữ liệu đầy đủ ở docs/DATA_DICTIONARY.md bao gồm từng cột, NULL, DEFAULT, khóa và CHECK; dữ liệu định danh sử dụng INT. Không xóa cascade.

# 5. Chuẩn hóa đến 3NF



Các khóa ứng viên được chọn theo ngữ nghĩa quản lý, không dựa vào việc một mẫu nhỏ tình cờ có giá trị duy nhất.

|Quan hệ|Khóa ứng viên|Phụ thuộc hàm chính|
|---|---|---|
|Market|MarketId; MarketCode|Mỗi khóa → MarketName, CurrencyCode và các thuộc tính còn lại|
|Industry|IndustryId; IndustryCode|Mỗi khóa → IndustryName, EvidenceNote|
|Stock|StockId; (MarketId,Ticker)|Mỗi khóa → CompanyName, IndustryId, IsSynthetic|
|Dataset|DatasetId; DatasetCode|Mỗi khóa → MarketId, DataKind, PriceBasis, PriceUnit, ObservedThrough, ManifestPath, ProvenanceNote|
|TradingDay|(DatasetId,TradeDate)|Chỉ gồm các thuộc tính khóa|
|DailyPrice|(DatasetId,StockId,TradeDate)|Toàn bộ khóa → OpenPrice, HighPrice, LowPrice, ClosePrice, Volume, LoadedAt|
|StockIndex|IndexId; (MarketId,IndexCode)|Mỗi khóa → IndexName và các thuộc tính còn lại|
|IndexMembership|(IndexId,StockId,ValidFrom)|Toàn bộ khóa → ValidTo, EvidenceNote|
|ForecastModel|ModelId; ModelCode|Mỗi khóa → ModelName, MethodNote|
|TargetDefinition|TargetId; TargetCode; HorizonSessions trong miền hiện tại|Mỗi khóa → OutputType, LabelRule, các thuộc tính còn lại; UQ ghép (HorizonSessions,OutputType,LabelRule) cùng CHECK cố định hai giá trị sau bảo đảm khóa horizon trong miền này|
|ModelRun|RunId; RunCode|Mỗi khóa → ModelId, DatasetId, TargetId, cửa sổ thời gian, SelectedC, Threshold, EvaluationClass, SourceRun, CompletedAt|
|ForecastOrigin|(RunId,OriginDate)|Toàn bộ khóa → TargetDate|
|Prediction|(RunId,StockId,OriginDate)|Toàn bộ khóa → ProbabilityPositive, LoadedAt|

## 1NF

Mỗi ô lưu một giá trị thuộc miền xác định: DATE cho ngày, DECIMAL cho giá/xác suất, BIGINT cho khối lượng. Không lưu danh sách ticker, nhóm ngày hoặc mảng dự báo trong một ô nghiệp vụ. Danh sách run CSV chỉ là tham số thủ tục, được tách để xử lý; nó không phải dữ liệu quan hệ được lưu.

## 2NF

Các bảng khóa đơn không có phụ thuộc bộ phận vào khóa chính. Với khóa tự nhiên ghép của Stock và StockIndex, tên và metadata gắn với cả thị trường và mã; không giả định ticker toàn cầu duy nhất. Với TradingDay không có thuộc tính ngoài khóa. Với DailyPrice, một giá phụ thuộc đồng thời phạm vi nguồn, cổ phiếu và ngày; dataset khác có thể chứa nguồn/phiên bản khác. Với IndexMembership, ngày kết thúc và bằng chứng gắn với toàn bộ chỉ số–mã–ngày bắt đầu. Với Prediction, xác suất gắn với cả lần chạy, mã và ngày gốc.

Ngày mục tiêu không được lưu lặp trong Prediction. Theo quy tắc horizon cố định của run, (RunId,OriginDate) → TargetDate, trong khi khóa Prediction còn chứa StockId. Tách ForecastOrigin loại bỏ đúng phụ thuộc bộ phận này. Đây là thay đổi chuẩn hóa thực tế từ thiết kế thử nghiệm đầu tiên, không phải một chuỗi phân rã được dựng ra để minh họa. Bản SQL có chuyển đổi không mất thông tin cho các database do lượt triển khai này tạo: sao chép và so sánh toàn bộ ánh xạ ngày trước khi bỏ trường lặp.

## 3NF

Không lưu MarketName trong Stock, IndustryName trong Stock, ModelName trong ModelRun, HorizonSessions trong Prediction, PriceUnit trong DailyPrice hoặc DatasetId/TargetId trong Prediction. Các giá trị đó được lấy qua FK và JOIN. Vì vậy các phụ thuộc bắc cầu tương ứng đã được loại bỏ. ActualLabel, lợi suất, Accuracy, Brier và log loss được tính từ dữ liệu đủ điều kiện, không lưu lặp như thuộc tính gốc của Prediction.

Trong từng quan hệ cuối cùng, với các phụ thuộc hàm nghiệp vụ đã nêu, mọi phụ thuộc không tầm thường có vế trái là siêu khóa hoặc vế phải là thuộc tính khóa. Các cột EvidenceNote/ProvenanceNote là mô tả của bản ghi bằng chứng cụ thể, không được giả định xác định duy nhất một thực thể khác. Quan hệ cuối đáp ứng 3NF theo các giả thiết miền đã tài liệu hóa.

## Tính không mất thông tin và bảo toàn liên kết

JOIN Prediction với ForecastOrigin theo (RunId,OriginDate) khôi phục đúng ngày mục tiêu, vì cặp này là PK của ForecastOrigin và FK của Prediction. Không nhân số dự báo. JOIN các bảng danh mục theo PK/FK khôi phục tên, đơn vị và cấu hình theo đúng một cha. Không điền NULL metadata bằng giá trị giả. Ràng buộc horizon, sự trưởng thành của nhãn và không chồng lấn khoảng hiệu lực là quy tắc liên bảng/thời gian, không phải bằng chứng thay thế cho phân tích 3NF.


# 6. Thiết lập ràng buộc

PRIMARY KEY nhận dạng thực thể và ngăn trùng khóa nghiệp vụ; FOREIGN KEY bảo đảm liên kết đến danh mục/lịch/run; UNIQUE bảo vệ mã tự nhiên; NOT NULL bắt buộc dữ liệu cốt lõi; DEFAULT ghi LoadedAt UTC và threshold 0.5; CHECK kiểm tra giá dương, High/Low, volume, xác suất, ngày và miền nhãn.

Trigger bổ sung quy tắc liên bảng: cùng thị trường/loại dữ liệu, ngày mục tiêu đúng horizon, ngày gốc sau validation, thành phần chỉ số không chồng lấn, cấu hình đã dùng không được đổi và lịch không làm sai horizon. Chỉ mục bổ sung tập trung thứ tự ngày và truy vấn phương pháp; không tạo chỉ mục cùng thứ tự với PK. Các kiểm thử có chủ đích xác nhận lỗi đúng constraint hoặc mã lỗi nghiệp vụ, sau đó rollback.

# 7. Triển khai SQL Server

Môi trường thực chạy: Standard Developer Edition (64-bit), engine 17.0.1145.4, Windows Authentication, server homematepc. SQL Server đã có sẵn; không cài phần mềm hệ thống. Ban đầu sandbox gặp SSPI, sau đó chạy công cụ với tài khoản Windows ngoài sandbox kết nối được mà không sửa instance. Script hướng đến SQL Server 2016 SP1 trở lên; một database mới hoàn toàn đã triển khai ở compatibility 130, nhưng chưa có instance Express riêng để kiểm chứng binary Express.

all_in_one.sql ghép 00–06, dùng GO tương thích SSMS/sqlcmd, có đầy đủ INSERT mô phỏng. Script tạo database mới nếu cần, bảo vệ database không thuộc dự án và không DROP database. Các lần chạy lại dùng kiểm tra khóa/giá trị để giữ dữ liệu không trùng. Bản schema hoàn chỉnh đã được thử từ database vắng mặt trước triển khai; toàn bộ 44 kiểm thử trên database mới đều PASS.

# 8. Nhập và kiểm tra dữ liệu

Nguồn thật: 30 tệp CSV KBS/Vnstock ngày, 39.873 dòng giá từ 2021–2026; tệp Stage 1 có 40.104 dự báo, hai mô hình và hai horizon. Khám phá chỉ đọc có giới hạn. 30/30 tệp giá khớp manifest lịch sử; 35/35 tệp đã mở có hash không đổi sau toàn bộ xử lý.

Tập con chọn trước theo thời gian: 20 ngày gốc đầu từ 01/09/2025, thực tế 03–30/09/2025; hai mô hình, horizon 20. Giá giữ từ 03/09 đến 28/10/2025, 40 phiên. Có 30 mã, 1.200 dòng giá, 1.200 dự báo và 40 ForecastOrigin. Đối chiếu 1.200 nhãn với giá và lịch đều khớp. Không có dòng trong phạm vi bị loại; 38.904 dự báo ngoài phạm vi được ghi là ngoài phạm vi, không gọi là lỗi. Toàn bộ 39.873 dòng giá đã được kiểm tra ngày/OHLCV/trùng khóa trước khi lấy mẫu.

Pipeline tạo JSON/CSV dẫn xuất và SQL batch 200 hàng. Cùng khóa khác giá trị gây lỗi 51100 và rollback toàn transaction. Đã kiểm tra nạp lại không tăng hàng, và cố tình gây xung đột ở cuối batch để kiểm tra một hàng cha thêm ở đầu cũng được rollback. Metadata ngành và tên pháp nhân ở dữ liệu thật để NULL; không tự gán. Demo gồm 8 mã mô phỏng, 280 giá và 258 dự báo, trong đó hai dự báo chưa có endpoint nên không được chấm.

# 9. Truy vấn nghiệp vụ

|Mã|Nghiệp vụ|Dòng demo|Dòng thật|Trạng thái|
|---|---|---|---|---|
|Q01|SELECT: Danh muc co phieu va tinh trang metadata.|8|30|PASS|
|Q02|INNER JOIN: Gia gan nhat kem don vi va pham vi nguon.|8|30|PASS|
|Q03|LEFT JOIN: Co phieu chua co thong tin phan nganh.|0|30|PASS|
|Q04|FULL JOIN: Doi chieu pham vi co gia va pham vi co du bao.|8|30|PASS|
|Q05|GROUP BY: Khoi luong trung binh theo nganh; UNKNOWN khong duoc xem la 0.|2|1|PASS|
|Q06|HAVING: Ma co it nhat 20 phien gia trong dataset.|8|30|PASS|
|Q07|Subquery: Phien co khoi luong cao hon trung binh cung ma/dataset.|136|478|PASS|
|Q08|UNION: Tap ma can quan ly tu gia hoac du bao (loai trung).|8|30|PASS|
|Q09|INTERSECT: Co phieu duoc ca hai run dau tien du bao.|8|30|PASS|
|Q10|EXCEPT: Ma co gia nhung khong co du bao.|0|0|PASS|
|Q11|LIKE: Tim ma theo ky tu A trong danh muc.|0|3|PASS|
|Q12|BETWEEN: Gia trong 7 ngay lich dau tien cua tap du lieu.|40|150|PASS|
|Q13|TOP / function: 5 ma tang gia nguon manh nhat tu dau den cuoi tap.|5|5|PASS|
|Q14|Ham huong: Minh hoa du bao huong loi suat 3 trang thai; khong thay the Brier.|1|1|PASS|
|Q15|View: Ket qua phan loai theo run va horizon, chi du lieu da truong thanh.|2|2|PASS|
|Q16|LEFT JOIN: Kiem tra thieu gia tren lich dataset trong pham vi da quan sat.|0|0|PASS|

Q01–Q16 bao phủ SELECT, INNER/LEFT/FULL JOIN, GROUP BY, HAVING, subquery, UNION, INTERSECT/EXCEPT, LIKE, BETWEEN và TOP. SQL đầy đủ, mục đích và log của từng truy vấn ở docs/BUSINESS_QUERIES.md. Dòng kết quả bằng 0 là hợp lệ khi truy vấn tìm lỗi/thiếu dữ liệu không phát hiện trường hợp nào. Không đổi NULL ngành thành dữ liệu nguồn giả.

Ví dụ giá nguồn tăng theo mã:

```sql
SELECT TOP(5) * FROM dbo.vw_LatestStockPrice ORDER BY Ticker;
SELECT dbo.fn_CalculateReturn(100,110) AS ReturnPct;
```

# 10. Stored procedures

|Thủ tục|Đầu vào chính|Kiểm tra và hành vi|
|---|---|---|
|usp_InsertDailyPrice|DatasetId, StockId, TradeDate, OHLCV, AllowUpdate|Kiểm tra OHLCV/lịch; bản ghi giống bỏ qua; khác giá trị từ chối trừ khi chủ động AllowUpdate=1|
|usp_AddPrediction|RunId, StockId, OriginDate, TargetDate, ProbabilityPositive|Kiểm tra mã/run/ngày/xác suất; tạo ForecastOrigin cùng transaction; chống trùng khác giá trị|
|usp_GetModelPerformance|ModelCode, DatasetId, HorizonSessions, FromDate, ToDate, AsOfDate|Chỉ tính bản ghi đủ endpoint và đã trưởng thành; lọc đúng mục tiêu/dataset|
|usp_CompareModels|RunIds, FromDate, ToDate, AsOfDate|2–8 run hợp lệ; cùng dataset/mục tiêu; chỉ giao đầy đủ tất cả khóa; không có giao thì báo lỗi|

Thủ tục ghi dùng TRY/CATCH, XACT_ABORT, transaction và savepoint khi đã nằm trong transaction của caller. Nếu transaction không còn khả năng commit, lỗi được trả về để caller rollback. Bộ test có trường hợp thành công, nạp lại, dữ liệu sai, xung đột và không có giao quan sát. Các thủ tục không tuyên bố mô hình tốt hơn chỉ từ chênh lệch mẫu nhỏ.

# 11. Functions và views

fn_CalculateReturn tính 100 × (Close cuối − Close đầu) / Close đầu, trả NULL cho giá NULL hoặc không dương. fn_CheckPredictionDirection dùng ba dấu âm/0/dương: 0 chỉ khớp 0; NULL cho thông tin chưa biết. Hàm này minh họa so chiều lợi suất, không thay quy tắc phân lớp nhị phân của dự báo thật. fn_EligiblePredictions nhận AsOfDate và kết nối run, mục tiêu, ngày gốc/mục tiêu và hai giá, loại bản ghi chưa trưởng thành. Hai hàm bắt buộc được dùng thực sự trong view/hàm đủ điều kiện hoặc Q13/Q14.

vw_LatestStockPrice trả giá cuối trong từng dataset/mã. vw_StudyUniverse nêu phạm vi quan sát mà không suy diễn thành phần lịch sử. vw_VN30SnapshotJune2026 chỉ biểu diễn snapshot ngày tham chiếu 30/06/2026, không gọi là danh sách hiện tại. vw_ModelPerformance tổng hợp Accuracy, Brier và natural-log loss theo run/dataset/mục tiêu; xác suất dùng log clip epsilon 1e-12 để xử lý 0/1, Brier dùng xác suất nguyên gốc.

# 12. Kiểm thử hệ thống

Đợt hoàn thiện hiện tại chạy 44 ca gốc trên bốn database: demo hiện có, nghiên cứu hiện có, database demo mới và database migration 12→13, tổng 176 lượt PASS. Đã chạy 16 query trên mỗi database, tổng 64 lượt; bảy regression test xác minh hợp đồng JSON và đủ mô hình. Ba preflight và năm live demo thành công; hash mọi hàng/cột của cả 13 bảng trước–sau khớp. Launcher cuối chạy thêm một vòng preflight/demo/query/44 ca.

Migration dùng DDL 12 bảng gốc thu hồi từ lịch sử thực thi; so EXCEPT hai chiều toàn bộ dự báo gồm LoadedAt: 258 dòng giữ nguyên, tạo 34 ForecastOrigin. Fixture ngày mục tiêu mâu thuẫn bị từ chối bằng lỗi 51200 trước thay đổi schema/dữ liệu. Lịch sử lỗi và giới hạn còn lại được giữ ở docs/HISTORICAL_FAILURE_AUDIT.md. Demo SQL khoảng 4 phút bằng 10_preflight_live.sql và 09_live_demo.sql, trong buổi trình bày khoảng 13–14 phút.

Các bằng chứng của giai đoạn triển khai trước vẫn được giữ để đối chiếu lịch sử:

44/44 test PASS trên demo và 44/44 trên nghiên cứu; thêm 44/44 trên database mới ở compatibility 130. Có kiểm tra PK/FK/UNIQUE/NOT NULL/DEFAULT/CHECK, trigger horizon/ngoài mẫu/khoảng hiệu lực, metadata bất biến, thủ tục thành công/thất bại, xử lý hòa/NULL, thiếu endpoint, ngày tham chiếu, common support và COMMIT/ROLLBACK. Mỗi thay đổi kiểm thử được rollback, không làm thay đổi số hàng chính.

16 truy vấn chạy trên mỗi database chính, tổng 32 lượt; toàn bộ view/hàm/thủ tục được gọi thực. Python tính lại chỉ tiêu độc lập từ giá/xác suất đã chuẩn bị, chênh lệch SQL dưới 1e-9. Log STATISTICS IO/TIME ghi phép đo thực tế trên máy cục bộ và dữ liệu nhỏ; cache không bị flush, không có đối chứng tốc độ, nên không suy diễn năng lực tải lớn. Các thao tác 0 ms phản ánh độ phân giải đồng hồ. Bằng chứng nằm trong tests/evidence, không có ảnh SSMS giả.

# 13. Đánh giá kết quả

|Run / mô hình|n chung|Accuracy|Brier|Log loss|
|---|---|---|---|---|
|1 / baseline|600|0.580000|0.247666|0.688478|
|2 / logistic L2|600|0.568333|0.252362|0.698052|

Hai run có cùng 600 khóa (mã, ngày gốc, ngày mục tiêu). Các giá trị này chỉ mô tả tập con đã khóa theo thời gian. Baseline có Brier/log loss thấp hơn trong tập con, nhưng không có kiểm định phụ thuộc theo thời gian và không kết luận ưu thế tổng quát hoặc hiệu quả đầu tư. Kết quả mô phỏng được giữ riêng và không dùng đánh giá nghiên cứu thật.

# 14. Hạn chế và hướng phát triển

Chưa kiểm thử trên instance Express riêng; compatibility 130 không tương đương chạy engine 2016/Express. Chưa xác minh adjustment hoặc hệ số đơn vị giá, vì vậy chỉ mô tả Close nguồn. Chưa có phân ngành/tên pháp nhân và timestamp hoàn tất nguồn nên giữ NULL. Danh sách thành phần chỉ số chỉ có snapshot 06/2026; vũ trụ dùng cho năm 2025 có điều kiện chọn mẫu theo danh sách này. Đánh giá retrospective không phải kiểm định mới chưa từng nhìn kết quả. Quyền provider/publication của dữ liệu nguồn vẫn UNKNOWN; dữ liệu thật và log mức bản ghi chỉ giữ cục bộ, không nằm trong gói demo độc lập.

Có thể mở rộng bằng metadata ngành có bằng chứng, lịch sử thành phần được xác minh, nguồn giá có ngữ nghĩa điều chỉnh rõ ràng và kiểm thử trên Express. Mỗi nguồn/target mới cần dataset/định nghĩa riêng cùng kiểm tra lineage. Không bổ sung huấn luyện hoặc giao diện phức tạp khi chưa cần cho yêu cầu học phần.

# 15. Kết luận

Đã triển khai một CSDL quan hệ có thể chạy độc lập bằng SQL Server, bao phủ các thành phần học phần và có bằng chứng thực thi. Schema 13 bảng loại bỏ phụ thuộc bộ phận của ngày mục tiêu, các quy tắc thời gian được kiểm tra tại DB, và so sánh mô hình dựa trên giao quan sát đã trưởng thành. Các giới hạn về nguồn, metadata và phiên bản môi trường được giữ hiển thị thay vì điền dữ liệu hoặc kết quả chưa xác minh.

# 16. Tài liệu tham khảo

1. Microsoft Learn, CREATE PROCEDURE (Transact-SQL): https://learn.microsoft.com/en-us/sql/t-sql/statements/create-procedure-transact-sql?view=sql-server-ver17 — tham khảo CREATE OR ALTER và tham số.
2. Microsoft Learn, sqlcmd utility: https://learn.microsoft.com/en-us/sql/tools/sqlcmd-utility?view=sql-server-ver16 — tham khảo tham số công cụ.
3. Protocol nguồn NEW_RETROSPECTIVE_EXPLORATORY_20261021, run SEDBM2026_ID12_SAME_DAY_RUN_20261021T154502; định nghĩa Close-up, horizon và chia mẫu được đọc cục bộ, hash trong DATA_INVENTORY.md.
4. vn30_constituents_2026_06.csv và INPUT_SHA256.csv của cùng nguồn; không thay thế bằng danh sách tự suy đoán.
5. Hồ sơ thực thi MarketLab: source_inventory.json, preparation_receipt.json, schema_*.json, validation_*.log, metrics_sql/python_*.json và fresh_database.log.
