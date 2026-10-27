# Kiểm kê công khai và ranh giới dữ liệu

## Có thể tái hiện trong repository

[data/sample](../data/sample/README.md) có 13 CSV và tables.json, hoàn toàn mô phỏng: Market 1, Industry 2, Stock 8, Dataset 1, TradingDay 42, DailyPrice 280, StockIndex 1, IndexMembership 8, ForecastModel 2, TargetDefinition 1, ModelRun 2, ForecastOrigin 34, Prediction 258. Horizon 5; 256 đủ hai endpoint, hai thiếu endpoint. Giá và xác suất không phải quan sát thị trường hoặc kết quả huấn luyện AI.

[Manifest](../data/manifests/demo_manifest.json) chỉ hash file mô phỏng. all_in_one.sql nhúng mẫu, không cần tệp CSV ngoài. Khóa và ràng buộc dùng giống thiết kế nghiên cứu, nhãn dữ liệu vẫn tách biệt.

## Nghiên cứu riêng — chỉ mô tả tổng hợp

Báo cáo đã duyệt mô tả tập con retrospective VN30: 30 mã, 40 phiên, 1.200 giá và 1.200 dự báo, hai run cùng 600 quan sát, horizon 20; 20 ngày gốc tháng 09/2025. Quyền nguồn chưa được xác minh để phân phối, nên không có record OHLCV/dự báo, tệp chuẩn bị, source inventory, input hash manifest hay log truy vấn trả bản ghi thật trong GitHub.

Ngành/tên pháp nhân/timestamp hoàn tất run thiếu bằng chứng nên NULL. Đơn vị quy đổi và adjustment UNKNOWN. VN30 chỉ có snapshot tháng 06/2026, không phải lịch sử thành phần. Không dùng LoadedAt như thời điểm forecast công bố, không tự đổi Close thành giá điều chỉnh/total return.

Các thống kê nghiên cứu và kiểm thử 4 DB là bằng chứng lịch sử được ghi rõ phạm vi, không phải kết quả mới tái chạy bằng bộ dữ liệu công khai. `sql/12_research_summary.sql` chỉ chứa SELECT tổng hợp tùy chọn, không chứa dữ liệu và không cần chạy để demo. [Giới hạn](HISTORICAL_FAILURE_AUDIT.md).
