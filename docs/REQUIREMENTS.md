# Phân tích yêu cầu MarketLab VN30

## Bối cảnh và mục tiêu

Bài tập quản lý thông tin thị trường và đối chiếu các dự báo có sẵn bằng SQL Server. Người học cần trình bày thiết kế quan hệ, toàn vẹn dữ liệu, truy vấn và giao dịch; không huấn luyện lại mô hình. Dữ liệu thực tế chỉ dùng nội bộ; bản demo độc lập dùng dữ liệu mô phỏng có nhãn.

## Phạm vi

Quản lý thị trường, ngành, mã cổ phiếu, lịch phiên, OHLCV, chỉ số và snapshot thành phần; lưu phương pháp, lần chạy, định nghĩa mục tiêu, ngày dự báo và xác suất. Phân tích thực tế giới hạn hai mô hình Stage 1, horizon 20 phiên, 20 ngày gốc đầu tiên từ tháng 09/2025 và vũ trụ 30 mã trong danh sách khóa tháng 06/2026. Không mô tả danh sách này như thành phần lịch sử năm 2025.

## Chức năng quản lý

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

## Trường hợp sử dụng

Người quản trị tạo danh mục, lịch phiên và nạp dữ liệu có manifest; xem receipt và lỗi; nạp lại để xác nhận idempotence. Người phân tích truy vấn giá, gọi đánh giá tại ngày tham chiếu và so sánh các run trên giao quan sát. Người trình bày chạy all_in_one.sql trong SSMS, minh họa JOIN/GROUP BY, kiểm tra CHECK bị từ chối và transaction rollback. Giảng viên có thể dùng sample không cần Python hoặc ổ K của tác giả.

## Báo cáo

16 truy vấn trong sql/07_business_queries.sql và docs/BUSINESS_QUERIES.md; báo cáo hàng/khóa/constraint trong tests/evidence; receipt chuẩn bị và import; chỉ tiêu theo run; bảng so sánh chung quan sát; báo cáo kiểm thử thực tế. Không thêm website, tài khoản người dùng hoặc dashboard ngoài phạm vi bài tập.
