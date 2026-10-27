# Phân tích chuẩn hóa đến 3NF

## Phụ thuộc hàm và khóa ứng viên

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
