# Câu hỏi phản biện và gợi ý trả lời

1. **Mục tiêu của bài tập?** Quản lý giá, lịch phiên và dự báo có sẵn trong CSDL quan hệ, tra cứu và đối chiếu khi thực tế đã quan sát. Không huấn luyện AI hoặc xây website.
2. **Vì sao 13 bảng?** Bổ sung Dataset để tách nguồn, TargetDefinition để định nghĩa đầu ra/horizon và ForecastOrigin để loại phụ thuộc bộ phận. Mỗi bảng có mục đích nghiệp vụ.
3. **Khóa DailyPrice là gì?** (DatasetId,StockId,TradeDate). Giá từ nguồn/phiên bản khác nhau không được trộn vào cùng bản ghi.
4. **Vì sao ticker không là khóa toàn cầu?** Mã có thể trùng giữa thị trường. Stock có StockId và UNIQUE(MarketId,Ticker).
5. **Điểm chuẩn hóa chính?** (RunId,OriginDate) xác định TargetDate trong khi khóa Prediction còn chứa StockId. Tách ForecastOrigin loại phụ thuộc bộ phận; FK ghép JOIN lại đúng một ngày.
6. **Chứng minh migration không mất dữ liệu thế nào?** Khôi phục DDL 12 bảng từ lịch sử thật; so EXCEPT hai chiều toàn bộ dự báo gồm TargetDate, ProbabilityPositive và LoadedAt. Giữ nguyên 258 dòng, tạo đúng 34 ForecastOrigin và kiểm tra nạp lại.
7. **Legacy có hai ngày mục tiêu cho cùng run/ngày gốc?** Từ chối bằng lỗi 51200 trước thay đổi schema. Không tự chọn ngày; fixture lỗi có chủ đích được giữ riêng, không đưa vào gói nộp.
8. **Vì sao DECIMAL?** Lưu thập phân giá/xác suất chính xác. FLOAT chỉ dùng trung gian tính logarit/bình phương; chỉ tiêu được tính lại bằng Python.
9. **CHECK OHLC kiểm tra gì?** Giá dương; High ≥ Open/Close/Low; Low ≤ Open/Close; Volume ≥ 0. PK ngăn trùng khóa giá.
10. **FK khác trigger?** FK bảo vệ khóa tham chiếu. Trigger kiểm tra liên bảng/thời gian: thị trường, loại dữ liệu, horizon, ngoài mẫu và khoảng hiệu lực.
11. **Có lỗi SQL nghĩa là test FAIL?** Không. Lỗi 547 hoặc 51100 có chủ đích là PASS khi đúng mã, đúng constraint và rollback được xác nhận. Lỗi khác dự kiến hoặc dữ liệu sai không bị từ chối mới là FAIL.
12. **Vì sao ngành/tên công ty ở tập thật NULL?** Nguồn thiếu bằng chứng; không gán bằng suy đoán. Ngành ở demo được ghi rõ mô phỏng. NULL không phải số 0.
13. **Dự báo thật là gì?** Xác suất Close ở t+20 phiên lớn hơn Close ở t. Không phải mức giá hoặc lợi suất dự báo. Nhãn 0 gồm giảm/hòa, threshold 0,5.
14. **Hàm so chiều xử lý 0?** Ba dấu âm/0/dương; 0 chỉ khớp 0, NULL trả NULL. Hàm này không thay quy tắc nhãn nhị phân của forecast thật.
15. **20 ngày hay 20 phiên?** 20 phiên kế tiếp trong TradingDay cùng dataset; không lấy giao lịch các thị trường hoặc tự điền giá thiếu.
16. **Khi nào được chấm?** Đủ hai endpoint; TargetDate ≤ AsOfDate và ≤ ObservedThrough. Demo có 258 dự báo nhưng chỉ 256 đủ điều kiện; hai dự báo thiếu endpoint trong dữ liệu.
17. **Vì sao demo 128, nghiên cứu 600 quan sát/run?** Hai dataset/database riêng. Trong từng lần so sánh, cả hai run dùng giao (StockId,OriginDate,TargetDate). Không so số liệu mô phỏng với thật.
18. **Brier/log loss?** Đánh giá xác suất, nhỏ hơn tốt hơn trên cùng tập quan sát. Brier dùng xác suất gốc, log loss clip epsilon 1e-12 để tránh log(0).
19. **Baseline tốt hơn có chứng minh ưu thế không?** Không. Chỉ mô tả 20 ngày gốc retrospective, vũ trụ chọn cố định. Không có kết luận ý nghĩa thống kê hoặc hiệu quả đầu tư.
20. **Có lịch sử VN30 đầy đủ?** Không. Chỉ snapshot 06/2026, không gọi là thành phần lịch sử 2025 hoặc danh sách hiện tại.
21. **Giá đã điều chỉnh chưa?** Chưa xác minh adjustment/hệ số đơn vị. Chỉ gọi Close nguồn và thay đổi Close nguồn, không gọi total return.
22. **Nạp lại có nhân hàng?** Bản ghi giống hệt bỏ qua; cùng khóa khác giá trị gây lỗi 51100 và rollback cả batch. Test chứng minh hàng cha thêm đầu batch cũng rollback khi lỗi cuối batch.
23. **AllowUpdate để làm gì?** Mặc định từ chối ghi đè khác giá trị; chỉ cập nhật khi chủ động AllowUpdate=1. Demo/regression rollback thay đổi, không sửa nguồn nghiên cứu.
24. **Số hàng không đổi đã đủ?** Chưa. Runner so hash canonical mọi hàng/cột, gồm LoadedAt, trên cả 13 bảng trước/sau.
25. **Đã thử Express?** Chưa có instance Express. Registry và hai instance đang chạy đều là Developer; compatibility 130 không phải kiểm thử binary Express/2016.
26. **Kết nối Windows từng lỗi vì sao?** Ngữ cảnh hạn chế không có credentials dùng được; kết nối bằng tài khoản Windows cục bộ thành công. Không đổi authentication/server config để vượt lỗi.
27. **Vì sao QUOTED_IDENTIFIER ON?** Truy vấn PK dùng XML `.value`, cần SET option phù hợp. Lỗi 1934 đã tái hiện bằng sqlcmd và sửa ngay trong session của script.
28. **Có ảnh SSMS dựng lại không?** Không. Có log SQL thực và ảnh render tài liệu. Giới hạn renderer/QA ghi trong DOCUMENT_QA.md.
29. **ZIP có dữ liệu thật?** Không có bản ghi giá/dự báo, SQL import hoặc log bản ghi thật. Chỉ mô phỏng có nhãn, mã nguồn, tài liệu, manifest và bằng chứng phù hợp; nghiên cứu chỉ có thống kê tổng hợp.
30. **Gặp FAIL khi demo?** Giữ log, đọc mã lỗi, dừng phần phụ thuộc. Không DROP/reset để làm số đếm khớp hoặc biến thiếu bằng chứng thành PASS.
