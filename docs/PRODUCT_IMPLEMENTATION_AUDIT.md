# Kiểm toán triển khai sản phẩm MarketLab VN30 (Giai đoạn 1)

Ngày kiểm tra: 2026-11-05 (Asia/Ho_Chi_Minh). Người thực hiện: Claude Code theo yêu cầu của chủ dự án.

## 1. Repository và nhánh

| Hạng mục | Thực tế |
|---|---|
| Thư mục được mở | `K:\btl he quan tri csdl` — **không phải** git repository; chứa 3 thư mục bàn giao cũ (`MarketLabVN30`, `MarketLabVN30_Publication`, `MarketLabVN30_License_Update_20261028`) và các file `.zip`/receipt |
| Các clone git có sẵn | 5 clone thuộc tài khoản `CodexSandboxOffline` (git báo *dubious ownership*). `MarketLabVN30_Publication\repository` sạch, `main` = `c1273b9` |
| Remote | `https://github.com/nicholas-atptit/bai-tap-lon-csdl-2026` — `main` = `c1273b9`, không có nhánh extension |
| Quyết định | Clone mới vào `K:\btl he quan tri csdl\bai-tap-lon-csdl-2026` (thuộc user hiện tại), tạo nhánh `feature/marketlab-working-product`. Không sửa, không xóa các thư mục/receipt/zip cũ; không đổi `git config --global` |
| Thay đổi chưa commit của người dùng | Không có (các clone cũ đều sạch) |

## 2. Gói mở rộng được nhắc tới

`marketlab_extension/`, `marketlab_live/`, `sql/13_eod_extension.sql`, `report/team/…` **không tồn tại** ở bất kỳ đâu trong thư mục làm việc hay trên remote. Toàn bộ API/UI/worker/migration trong nhánh này được viết mới; không có bản song song.

## 3. Lõi SQL đã có (giữ nguyên)

13 bảng, 16 FK, PK/UNIQUE/CHECK, 10 trigger, 3 function, 4 view, 4 procedure, 16 truy vấn, 44 ca kiểm thử (`08`). Đọc: `README.md`, `docs/REQUIREMENTS.md`, `DATABASE_DESIGN.md`, `NORMALIZATION.md`, `DATA_DICTIONARY.md`, `PUBLICATION_AUDIT.md`, `sql/00–10,12`.

Những ràng buộc quan trọng phát hiện khi audit:

1. `tr_Dataset_Guard` cấm đổi `ObservedThrough` sau khi dataset có giá/run → EOD bắt buộc phải có migration (đã làm: `sql/13_eod_extension.sql`).
2. `tr_DailyPrice_Scope` cấm giá có `TradeDate > ObservedThrough` → phải nâng `ObservedThrough` trong cùng transaction với giá.
3. **Test #151 của `08_validation_tests.sql` khẳng định toàn database có đúng 13 bảng**, và `10_preflight_live.sql` khẳng định đúng 4 procedure. ⇒ Bảng nhật ký vận hành **không thể** đặt trong database nghiệp vụ mà vẫn giữ 44/44 PASS. Quyết định: bảng `ops.*` nằm trong database riêng `MarketLabVN30_Ops`; database nghiệp vụ chỉ nhận schema `ops` chứa 1 procedure + trigger sửa đổi (0 bảng mới).
4. `usp_GetModelPerformance`/`usp_CompareModels` không trả log loss; `vw_ModelPerformance` cố định `as_of = SYSUTCDATETIME()`. API dùng `fn_EligiblePredictions(@as_of)` với **đúng công thức** của view (kiểm chứng bằng test so khớp 1e-12) và gọi `usp_CompareModels` cho phần so sánh.
5. `scripts/check_publication.py` dùng allowlist chính xác theo hash → mọi file mới làm gate FAIL ("unlisted") cho tới khi người duyệt cập nhật `docs/PUBLICATION_ALLOWLIST.json`. Không tự sửa file kiểm soát này.

## 4. Môi trường máy

| Thành phần | Thực tế | Trạng thái |
|---|---|---|
| Windows | 11 Pro 10.0.26300, timezone `SE Asia Standard Time` (UTC+7) | OK |
| SQL Server | `MSSQLSERVER` 17.0.1145.4 Standard Developer (đang chạy); `MSSQLSERVER02` (rỗng) | OK |
| Database | `MarketLabVN30_Demo` (SYNTHETIC), `MarketLabVN30_Research_20261027` (REAL_PRIVATE, KBS, 30 mã, 1.200 giá/dự báo), 4 DB kiểm thử cũ | Không sửa demo/nghiên cứu |
| ODBC | Driver 17 và **18** for SQL Server | OK |
| sqlcmd | 17.0.1000.7 | OK |
| Python | 3.12.10 (system) ; `uv` 0.10.10 | OK |
| Port 8000 | trống; firewall bật cả 3 profile — app chỉ bind 127.0.0.1 nên không cần rule | OK |
| Frontend | Không có frontend cũ; Node 24 có sẵn nhưng **không dùng** (HTML/CSS/JS thuần, không build) | — |
| Edge | Có sẵn → Playwright điều khiển Edge, không tải browser | OK |

## 5. Nguồn dữ liệu EOD (smoke test thật)

* PyPI không còn phiên bản `vnstock` nào (kiểm tra 2026-11-05). Index vendor `vnstocks.com/api/simple` có 4.0.8/4.0.9. Việc cài từ index bên thứ ba vào `.venv` dự án **bị chặn** trong phiên làm việc → thiết kế adapter subprocess dùng interpreter người dùng đã tự cài vnstock (`MARKETLAB_PROVIDER_PYTHON`, hiện là system Python với vnstock 3.5.1).
* `Quote(source='kbs').history(...)` hoạt động ở cả 3.5.1 (system) và 4.0.9 (venv thử nghiệm cô lập trong scratch). Cột `time, open, high, low, close, volume`; `time` dạng naive `YYYY-MM-DD 07:00:00` = nhãn ngày.
* ACB 20–28/10/2025 khớp **tuyệt đối** DB nghiên cứu. FPT 03–05/09/2025 cùng Volume nhưng giá thấp hơn ~9,1% ⇒ **KBS điều chỉnh hồi tố giá lịch sử**. Hệ quả thiết kế: không bao giờ tự update giá đã chốt; có quy trình reconciliation + drift probe.
* Chuỗi VN30 index thiếu 31/08–02/09/2026 trong khi có 28/08 và 03/09 ⇒ dùng làm bằng chứng lịch nghỉ (NO_SESSION) thay vì tự đoán ngày lễ.

## 6. Thiếu / blocker ban đầu và cách xử lý

| Vấn đề | Xử lý |
|---|---|
| Không có model artifact / pipeline inference | Không tạo dự báo mới. UI/API hiển thị "Chưa cấu hình mô hình tạo dự báo mới". **Inference: NOT IMPLEMENTED** (ngoài phạm vi khi không có artifact) |
| Database nghiên cứu chưa có migration EOD | Không chạy DDL lên DB nghiên cứu. Dùng DB mới `MarketLabVN30_Live` (REAL_PRIVATE). Migration DB nghiên cứu cần backup + xác nhận (lệnh có sẵn) |
| vnstock không có trên PyPI | Adapter subprocess + cấu hình interpreter |
| Universe | Chỉ có snapshot 06/2026 (file HOSE period 1/2026, sha256 `a961eeae…`). Dùng snapshot này **làm universe cố định có ghi giới hạn**, không suy ra thành phần hiện tại |
| Gate công bố allowlist | Ghi nhận FAIL dự kiến; cần người duyệt cập nhật allowlist khi merge |
