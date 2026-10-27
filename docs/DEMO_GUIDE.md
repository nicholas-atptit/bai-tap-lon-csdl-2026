# Kịch bản SSMS khoảng 4 phút

## Trước buổi trình bày

Kết nối instance SQL Server của bạn, Windows Authentication đã được phép; máy tác giả dùng `.`. Xem [cài đặt](INSTALLATION_GUIDE.md). Database mới dùng all_in_one; DB đã đúng không cần dựng lại. Chạy `sql/10_preflight_live.sql` trên session riêng: 13 bảng, 8 mã, 280 giá, 258 dự báo, 256 đủ điều kiện, 2 thiếu endpoint, 4SP/3hàm/4views; tất cả Actual=Expected, PREFLIGHT_PASS. Nếu FAIL giữ log và dừng, không reset.

Mở `sql/09_live_demo.sql`, phóng to chữ. Chạy **toàn bộ file bằng F5**; không cần SQLCMD mode. Phần 4–5 dùng chung biến, không chạy riêng. Dữ liệu là **SYNTHETIC**, không phải quan sát thị trường.

|Thời gian|Nhóm kết quả|Điều giải thích|
|---|---|---|
|0:00–0:40|DEMO1: 13 bảng, PK/FK thực trong catalog|DailyPrice PK dataset/mã/ngày; Prediction FK ghép tới ForecastOrigin|
|0:40–1:30|DEMO2: JOIN, GROUP BY/HAVING, subquery|Giá cuối có ngành; độ phủ ≥20 phiên; Volume trên trung bình cùng dataset/mã|
|1:30–2:10|DEMO3: CompareModels và functions|128 quan sát chung/run mô phỏng; 100→110=10%; flat/flat=1; eligible256|
|2:10–2:50|DEMO4: CHECK âm bị từ chối|Đúng547 và CK_DailyPrice_Volume được bắt, session tiếp tục; lỗi khác vẫn trả ra|
|2:50–3:50|DEMO5: transaction|BEFORE V, DURING V+1, AFTER ROLLBACK V; hash trước=sau, @@TRANCOUNT0, LIVE_DEMO_PASS|
|3:50–4:00|Quay về slide|Nhắc demo mô phỏng và dữ liệu không đổi|

Các log đã chạy được giữ tại [preflight](../tests/reference_evidence/10_preflight.log), [live demo](../tests/reference_evidence/09_live_demo.log); đây là log sqlcmd, không phải ảnh SSMS. Lượt công bố mới ở [PUBLICATION_AUDIT](PUBLICATION_AUDIT.md). Muốn chụp ảnh dùng checklist S01–S08 trong [hướng dẫn báo cáo](REPORT_WRITING_GUIDE.md); không dựng ảnh.

## Trình bày 14 slide

Thời gian slide1–14 lần lượt: 20,40,45,40,60,45,45,40,40,45,45,45,240,35 giây; tổng825giây=13:45. Đây là kế hoạch, chưa phải đo rehearsal. [SLIDE_BUILD_GUIDE](SLIDE_BUILD_GUIDE.md) bám thứ tự deck đã duyệt, demo ở slide13. [DEFENSE_QA](DEFENSE_QA.md) có30câu.

Nếu live lỗi, nêu lỗi thật rồi dùng log có nhãn lịch sử/NOT VERIFIED trên máy hiện tại; không giả vờ PASS, không sửa constraint hoặc reset DB trước lớp. Không mở database nghiên cứu để thay demo. File12 chỉ là aggregate tùy chọn trên máy có DB riêng, không cần cho bài trình bày công khai.
