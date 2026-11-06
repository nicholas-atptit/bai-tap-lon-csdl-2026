# Báo cáo FINAL chuẩn hóa + SSMS – danh sách thay đổi

Nền bắt buộc: `report/final/base/MarketLabVN30_FINAL_CHUAN_HOA_THEO_MAU.docx`. Đây là bản sao byte-đúng của file 42 trang trong thư mục Downloads (SHA-256 `7d7237c6…`); file gốc không bị sửa.
Đầu ra: `report/final/MarketLabVN30_FINAL_CHUAN_HOA_SSMS.docx` và `.pdf`, **54 trang A4**, 21 hình, 29 bảng. Mục lục, danh mục hình và danh mục bảng là trường Word, đã cập nhật.
Không ghi đè file mẫu, file nền hay FINAL v2 (`report/final/MarketLabVN30_FINAL.*`).
Dựng lại: `uv run --no-project --with python-docx --with pillow python scripts/build_report_chuan_hoa.py`, sau đó `powershell -ExecutionPolicy Bypass -File scripts\Finalize-Report.ps1 -Docx report\final\MarketLabVN30_FINAL_CHUAN_HOA_SSMS.docx`.

## Bổ sung

- 1.4: một câu phân biệt universe cấu hình với thành phần VN30 lịch sử khi dữ liệu Live kéo về 2023.
- 2.1: ảnh SSMS 16 khóa ngoại (sys.foreign_keys) + ghi chú Demo không có Database Diagram; giữ nguyên Hình 1–2 của bản nền.
- 2.4: ảnh SSMS ràng buộc của 5 bảng tiêu biểu (17 nhóm ràng buộc).
- 3.1: ảnh SSMS Object Explorer (Tables) + truy vấn sys.tables: 13 bảng, số cột, số dòng.
- 3.4: đoạn mô tả backfill trên SQL Server + ảnh SSMS thống kê Live (28.097 dòng, 30 mã, 956 phiên, theo năm, VPL).
- 4.1: 4 ảnh SSMS ngay sau câu SQL tương ứng (Q01; Q02–Q03; Q05–Q07; Q08–Q10). Giữ nguyên 16 truy vấn của bản nền.
- 4.2–4.4: ảnh SSMS cho Views, Stored Procedures (EXEC chỉ đọc), Functions. Bảng tóm tắt và ví dụ rút gọn của bản nền giữ nguyên.
- 4.5: ảnh SSMS ca kiểm thử CHECK (lỗi 547, rollback, Volume trước = sau).
- 5.3.6: trang Backfill lịch sử (Hình 9).
- 5.5.7: quy trình nạp lịch sử 2023–2026 (đoạn ngắn) + Bảng kết quả (28.097 / 27.317 / 780 / 0 thiếu / VPL / chạy lại / sàn 2023).

## Cập nhật

- 1.2.1: hai thao tác ghi qua biểu mẫu (đồng bộ phiên, backfill lịch sử) thay cho “thao tác ghi duy nhất”.
- 1.3.1, 5.5.4, 5.6: sửa tham chiếu “mục 3.6” (không tồn tại) thành “mục 3.4”.
- Bảng 3: phạm vi Live 780 dòng/26 phiên → 28.097 dòng, 30 mã, 956 phiên 03/01/2023–05/11/2026; giới hạn VPL.
- Bảng 19: schema Ops v1–v3, thêm một dòng cho nhóm bảng backfill.
- 4.5: 102 ca → 140/140; regression SQL chạy lại 06/11/2026.
- Bảng 21: template, module backfill, script Backfill-MarketLab, 140 ca kiểm thử.
- 5.3: năm → sáu trang chức năng; mô tả Tổng quan, Lịch sử OHLCV (sàn 01/01/2023, 12 tháng mặc định, CSV), EOD; khung 1280×800.
- Hình 4, 6, 8, 9, 10 cũ: thay bằng ảnh Web FINAL chụp 06/11/2026 (Tổng quan Live, Lịch sử OHLCV FPT 2023–2026, Dự báo, So sánh, Vận hành EOD).
- Bảng 22: thêm route /backfill, /backfill/run và /market/export.csv.
- 5.5.6: kết quả EOD ghi rõ giai đoạn 780 dòng ban đầu và chạy lại 05/11/2026; trỏ sang 5.5.7.
- 5.6–5.10: TriggerKind BACKFILL, lệnh Backfill-MarketLab, kết quả kiểm thử 140/140 – 48/48 – 26/26 – 38/38, kịch bản demo.
- Kết luận và Bảng 27: sáu trang, 28.097 dòng 2023–2026, 140/140, đối chiếu 26/26 – 38/38; thêm dòng dữ liệu 2023–2026.
- Phụ lục A: 140 ca, thư mục ảnh SSMS, số dòng Live 28097.
- Đánh số lại theo thứ tự xuất hiện: 21 hình, 29 bảng; mục lục, danh mục hình, danh mục bảng thành trường Word.

## Loại bỏ

- Hình 5 cũ (Tổng quan REAL 780 dòng) và Hình 7 cũ (bảng OHLCV DEMO03): gộp vào ảnh Web FINAL mới, giảm số ảnh giao diện.
- Hướng phát triển: bỏ mục “chụp bổ sung ảnh SSMS” vì đã thực hiện.

## Giữ lại

- Bìa, form PTIT, lời nói đầu, toàn bộ Chương 2 (13 bảng, đặc tả thuộc tính, chuẩn hóa 3NF, ràng buộc) và cách trình bày SQL ngắn theo mẫu.
- 16 truy vấn Q01–Q16, 4 View, 4 Stored Procedure (bảng tóm tắt + 2 ví dụ EXEC), 3 Function, ví dụ kiểm thử CHECK của bản nền.
- Hình 1 (ERD thiết kế), Hình 2 (nhóm chức năng), Hình 3 (kiến trúc).
- Không đưa lại log lỗi dài, hash, bảng kết quả kỹ thuật thừa hay phần kiểm thử lặp lại đã được cắt giảm ở bản nền.

## Ảnh SSMS thật (SQL Server Management Studio 22.4, chụp tự động 06/11/2026)

Cách chụp: `scripts/capture_ssms_evidence.py`.
- Mở SSMS bằng Windows Authentication, dán script trong `report/final/evidence/ssms/sql/`, nhấn F5.
- Mở thư mục Object Explorer tương ứng, chụp cửa sổ bằng PrintWindow.
- Làm mờ mọi phần tử hiển thị tên đăng nhập Windows; cắt bỏ khung Copilot và ảnh tài khoản.
- Script chỉ đọc. Riêng ca 12 vi phạm CHECK trong transaction trên DEMO rồi hoàn tác; regression 44 ca chạy lại sau đó vẫn PASS, hash 13 bảng không đổi.

| # | Yêu cầu | Tệp | Trạng thái thanh SSMS | Vị trí trong báo cáo |
|---|---|---|---|---|
| 01 | Object Explorer + 13 bảng | `01_database_tables.png` | Query executed successfully., 13 rows | Hình 5 (3.1) |
| 02 | Quan hệ PK/FK (thay cho Database Diagram) | `02_erd_relationships.png` | Query executed successfully., 16 rows | Hình 3 (2.1) |
| 03 | Cấu trúc/ràng buộc Stock, Dataset, DailyPrice, ModelRun, Prediction | `03_table_constraints.png` | Query executed successfully., 17 rows | Hình 4 (2.4) |
| 04 | SELECT danh mục cổ phiếu | `04_select_query.png` | Query executed successfully., 8 rows | Hình 7 (4.1, Q01) |
| 05 | INNER JOIN và LEFT JOIN | `05_join_query.png` | Query executed successfully., 8 rows | Hình 8 (4.1, Q02–Q03) |
| 06 | GROUP BY, HAVING, truy vấn lồng | `06_groupby_having_subquery.png` | Query executed successfully., 146 rows | Hình 9 (4.1, Q05–Q07) |
| 07 | UNION, INTERSECT, EXCEPT | `07_set_operations.png` | Query executed successfully., 16 rows | Hình 10 (4.1, Q08–Q10) |
| 08 | 4 View + kết quả View | `08_views.png` | Query executed successfully., 6 rows | Hình 11 (4.2) |
| 09 | Stored Procedures + EXEC chỉ đọc | `09_stored_procedures.png` | Query executed successfully., 5 rows | Hình 12 (4.3) |
| 10 | Functions + SELECT dùng Function | `10_functions.png` | Query executed successfully., 14 rows | Hình 13 (4.4) |
| 11 | Thống kê dữ liệu thật 2023–2026 (chỉ tổng hợp) | `11_live_data_summary.png` | Query executed successfully., 6 rows | Hình 6 (3.4) |
| 12 | Kiểm thử ràng buộc an toàn trên DEMO | `12_constraint_test.png` | Query executed successfully., 3 rows | Hình 14 (4.5) |

**Không chụp được:** Database Diagram thật. `MarketLabVN30_Demo` không có diagram (`sysdiagrams` = 0). Tạo diagram sẽ thêm bảng hệ thống vào database đang được kiểm thử có đúng 13 bảng, nên ảnh 02 dùng truy vấn `sys.foreign_keys` (16 FK) chụp trong SSMS. Báo cáo giữ Hình 1 (ERD thiết kế của nhóm) và ghi rõ điều này ở mục 2.1.

## Kiểm tra

- Câu SQL Q01–Q16 trong báo cáo khớp `sql/07_business_queries.sql` (chỉ khác xuống dòng). Ví dụ EXEC dùng đúng tham số của thủ tục. `demo_baseline` có horizon 5; dòng (1, 1, 2025-02-19) tồn tại. Có 4 view, 4 thủ tục, 3 hàm, 16 FK (sqlcmd).
- Số liệu Live trong báo cáo khớp ảnh SSMS 11 và SQL: 28.097 dòng, 30 mã, 956 phiên, 03/01/2023–05/11/2026; theo năm 249/250/249/208 phiên; VPL có 373 phiên, từ 13/05/2025.
- Render cả 54 trang và xem từng tấm tổng hợp. Lỗi phát hiện và đã sửa:
  - Bảng 25 thừa hàng tiêu đề và một hàng còn sót từ bảng mẫu.
  - Ảnh truy vấn SSMS có chữ nhỏ: bản dùng trong báo cáo được cắt các dải trống; ảnh bằng chứng gốc giữ nguyên.
- `validate.py --original <file nền>`: All validations PASSED. Mọi font đều nhúng.
- Văn bản PDF không còn: "102 ca", "năm khu vực", "1366", "mục 3.6" (tham chiếu sai của bản nền), tên đăng nhập Windows.
