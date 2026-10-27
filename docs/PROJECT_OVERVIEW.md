# Tổng quan cho thành viên nhóm

MarketLab VN30 là bài tập CSDL quản lý dự báo có sẵn. Câu hỏi kỹ thuật là lưu và ghép đúng quan sát, bảo vệ dữ liệu, đánh giá khi đủ bằng chứng; không phải xây một mô hình AI mới.

Ba nhóm bảng: (1) Market/Industry/Stock/StockIndex/IndexMembership; (2) Dataset/TradingDay/DailyPrice; (3) ForecastModel/TargetDefinition/ModelRun/ForecastOrigin/Prediction. Mỗi nhóm phục vụ quy tắc riêng nên 13 bảng có ý nghĩa nghiệp vụ, không phải tăng số bảng cho đủ yêu cầu.

DailyPrice có khóa (DatasetId,StockId,TradeDate) để không trộn nguồn/phiên bản. ForecastOrigin tách TargetDate khỏi Prediction vì (RunId,OriginDate) xác định TargetDate. Hàm fn_EligiblePredictions nối hai giá qua run/dataset, kiểm tra ngày trưởng thành và trả nhãn thực tính tại lúc đánh giá. usp_CompareModels dùng cùng tập quan sát giữa các run.

Bản công khai chạy hoàn toàn bằng mẫu mô phỏng: 8 mã, 280 giá, 258 dự báo; 256 đủ điều kiện, hai thiếu endpoint. Tập nghiên cứu giữ riêng; số tổng hợp trong báo cáo không biến dữ liệu mô phỏng thành dữ liệu thật. [Kiểm kê](DATA_INVENTORY.md).

Đọc theo thứ tự: [README](../README.md) → [thiết kế](DATABASE_DESIGN.md) → [từ điển](DATA_DICTIONARY.md) → [3NF](NORMALIZATION.md) → [demo](DEMO_GUIDE.md) → hướng dẫn [báo cáo](REPORT_WRITING_GUIDE.md)/[slide](SLIDE_BUILD_GUIDE.md). Bản tham khảo được giữ nguyên trong report/ và slides/; các thay đổi cần review theo [CONTRIBUTING](../CONTRIBUTING.md).
