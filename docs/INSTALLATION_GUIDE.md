# Cài đặt và chạy MarketLab VN30

## Điều kiện

Windows có SQL Server và SSMS. Môi trường kiểm chứng là SQL Server 2025 Developer 17.0.1145.4; chưa chứng minh binary Express/2016. Không có thao tác cài phần mềm, đổi dịch vụ hoặc đổi authentication trong lần công bố. Python/Git chỉ cần cho thao tác nhóm và kiểm chứng nâng cao; demo SSMS độc lập.

## Lấy dự án

```powershell
git clone https://github.com/nicholas-atptit/bai-tap-lon-csdl-2026.git
cd bai-tap-lon-csdl-2026
```

Nếu tải ZIP từ nút Code của GitHub, giải nén rồi mở file SQL; để đóng góp nên dùng clone. Không cần ZIP riêng của tác giả hoặc dữ liệu nghiên cứu.

## SSMS: đường chạy chính

1. Connect → Database Engine. Chọn đúng server/instance trên máy bạn; máy tác giả dùng `.` với Windows Authentication. Không nhập mật khẩu vào script.
2. Mở New Query riêng, không có transaction đang mở. Nếu chưa có MarketLabVN30_Demo, File → Open → File → `sql/all_in_one.sql`, F5 toàn bộ. Không cần SQLCMD mode. Tài khoản cần quyền tạo database cho lần đầu.
3. File đã chứa 00–06 và dữ liệu mô phỏng. Không chạy lại từng phần như cách sửa lỗi tùy tiện. Nếu DB đã đúng, bắt đầu từ preflight, không dựng lại DB.
4. Mở `sql/10_preflight_live.sql`, F5. Phải có PREFLIGHT_PASS, tất cả Actual=Expected, transaction mở=0.
5. Mở và chạy toàn bộ `sql/09_live_demo.sql`; xem LIVE_DEMO_PASS, hash trước=sau. Chạy `07_business_queries.sql` để xem Q01–Q16; `08_validation_tests.sql` phải tổng PASS 44, không có FAIL.
6. Nếu preflight sai, lưu Messages và dừng; không DROP/reset, tắt constraint hoặc đổi nhãn dữ liệu để tạo PASS. Không đổi tên USE sang database nghiên cứu.

File 00 bảo vệ DB có sẵn không thuộc schema MarketLab 1.0. Bản all-in-one là cách đơn giản nhất. Nếu học từng bước: 00 → 01 → 02 → 03 → 04 → 05 → 06, rồi 10 → 09 → 07 → 08.

## sqlcmd: tùy chọn

```powershell
sqlcmd -S . -E -C -No -b -f 65001 -i .\sql\all_in_one.sql
sqlcmd -S . -E -C -No -b -f 65001 -i .\sql\10_preflight_live.sql
sqlcmd -S . -E -C -No -b -f 65001 -i .\sql\09_live_demo.sql
```

`-E` dùng tài khoản Windows hiện hành; `-b` trả mã lỗi; `-f 65001` đọc UTF-8. Các cờ TLS `-C -No` là cấu hình ODBC cho kết nối cục bộ đã thử, không phải hướng dẫn thay chính sách máy chủ từ xa. Thay `.` bằng instance của bạn. Nếu sqlcmd cũ không hỗ trợ tham số, dùng SSMS hoặc xem `sqlcmd -?`; không bỏ kiểm tra lỗi tùy tiện. Không dùng đồng thời `-h` và `-y 0` trong truy vấn JSON.

Launcher `scripts/run_demo.ps1` chạy cả triển khai 00–06 rồi preflight/demo/query/test, vì vậy chỉ dùng khi chủ động muốn kiểm tra toàn đường triển khai trên DB mô phỏng. Nếu DB đã đúng, dùng `run_public_regression.py` để không dựng lại schema.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_demo.ps1 -Server .
```

Cờ ExecutionPolicy chỉ cho process chạy script đã đọc; không đổi policy hệ thống. Đường dẫn có dấu cách được script xử lý bằng tham số, không cần sửa đường dẫn ổ đĩa.

## Lỗi thường gặp

|Triệu chứng|Việc cần làm|
|---|---|
|Không kết nối / SSPI|Kiểm tra tên instance và tài khoản Windows trong session thật. Lưu lỗi; không đổi server/auth để vượt kiểm tra.|
|Không có quyền CREATE DATABASE|Nhờ người quản trị triển khai demo hoặc dùng instance cá nhân được phép; không dùng DB nghiên cứu thay thế.|
|PREFLIGHT_FAIL|Đọc bảng Actual/Expected; đối chiếu đúng DB và bộ SQL. Giữ log, báo technical owner.|
|Must declare variable trong demo|Chạy cả file 09; phần 4–5 dùng chung biến.|
|Lỗi 547 CK_DailyPrice_Volume trong phần 4|Đúng lỗi có chủ đích khi được TRY/CATCH bắt và file tiếp tục tới LIVE_DEMO_PASS; lỗi 547 ở chỗ khác phải điều tra.|
|Express hoặc phiên bản khác|Có thể thử trên máy được phép, nhưng chỉ ghi PASS sau khi lưu kết quả thực; trạng thái hiện tại NOT VERIFIED.|

Không khôi phục `.bak`, không cần `.mdf/.ldf`, không cài Python chỉ để F5 SQL. [Demo](DEMO_GUIDE.md) · [kiểm chứng](../tests/README.md).
