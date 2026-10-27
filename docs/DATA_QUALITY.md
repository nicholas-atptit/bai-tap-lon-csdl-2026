# Kiểm tra dữ liệu và trạng thái bằng chứng

- Demo: kiểm tra mọi IsSynthetic=1, mã DEMO, DataKind=SYNTHETIC; count/schema/FK/CHECK/triggers qua preflight.
- OHLC dùng DECIMAL(19,6), High/Low bao đúng Open/Close, Volume BIGINT ≥0; xác suất DECIMAL(19,16) trong [0,1].
- Giá duy nhất theo dataset/mã/ngày, dự báo duy nhất theo run/mã/ngày gốc. Chỉ có lịch của dataset mới xác định phiên thứ h.
- Dự báo thiếu hai endpoint hoặc chưa trưởng thành bị loại khỏi tập đánh giá, không gán ActualLabel=0 để bù thiếu.
- SQL/Python đối chiếu Accuracy, Brier và natural-log loss theo run; bắt buộc đủ run, không chấp nhận thiếu JSON như mảng rỗng.
- Nạp trùng giống nhau bỏ qua; khác giá trị báo 51100, rollback cả batch. Public renderer chỉ đọc dữ liệu mô phỏng; không cần nguồn riêng.
- Hash trước/sau bao mọi hàng/cột của cả 13 bảng, kể cả LoadedAt. Count không đủ để chứng minh dữ liệu không đổi.

PASS: phép kiểm cụ thể chạy thành công và có log. FAIL: phép kiểm chạy nhưng không đạt. BLOCKED: thiếu điều kiện bên ngoài. NOT VERIFIED: chưa có kiểm chứng đúng phạm vi. Không đổi BLOCKED/NOT VERIFIED thành PASS nhờ một phép kiểm tương tự. [Bằng chứng và cách chạy](../tests/README.md).
