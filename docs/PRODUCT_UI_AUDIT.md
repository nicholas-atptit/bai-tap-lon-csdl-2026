# Kiểm toán Web UI / API trước khi polish

* Ngày: 2026-11-06 (Asia/Ho_Chi_Minh). Nhánh `feature/marketlab-working-product`, HEAD khi audit = `da7b27b768133981267398323943f5cffa6419c9`, working tree sạch.
* Stack thực tế: FastAPI 0.115.12 + uvicorn 0.34.2 + pyodbc 5.2.0; frontend HTML/CSS/JavaScript ES module thuần (`marketlab_app/web/`: `index.html`, `app.js`, `charts.js`, `styles.css`), biểu đồ SVG tự vẽ, không framework, không build, không CDN. **Giữ nguyên stack** — không có lỗi kiến trúc buộc phải đổi.
* Instance đang chạy (do `Start-MarketLab.ps1 -Background` khởi động): DEMO_OFFLINE `127.0.0.1:8000` (`MarketLabVN30_Demo`), REAL_PRIVATE `127.0.0.1:8001` (`MarketLabVN30_Live`). Không có process trùng cổng.
* Công cụ: `scripts/ui_audit.py` (Playwright 1.52 + Microsoft Edge đã cài, headless): 2 chế độ × 4 viewport (1440×900, 1366×768, 768×1024, 390×844) × 5 tab + Swagger; thu console error, response ≥ 400, tràn ngang trang, control bị cắt/thiếu label, chữ NaN/undefined, container trống không có thông báo. Kết quả máy đọc: `tests/product_evidence/ui_audit/before/audit.json`; ảnh DEMO: `tests/product_evidence/ui_audit/before/`; ảnh REAL: thư mục private (gitignored). Sau đó xem trực quan từng ảnh.

Kết quả tự động "before": 40 màn hình; **0 console error, 0 request lỗi**, 0 tràn ngang trang, 0 control thiếu label; 9 màn hình có container trống không thông báo; **Swagger không render ở cả 2 instance**.

## Bảng issue

| ID | Mức | Route / màn hình | Cách tái hiện | Nguyên nhân | Cách sửa | Test chứng minh |
|---|---|---|---|---|---|---|
| UI-01 | **P0** | `/api/docs` (cả 8000, 8001) | Mở Swagger → "Unable to render this definition … valid version field" | FastAPI 0.115 phát OpenAPI **3.1.0**; `swagger-ui-bundle 1.1.0` đóng gói Swagger UI **4.15.5** (chỉ hỗ trợ 3.0.x) | Dùng asset Swagger UI **5.24.2** từ `swagger-ui-py` (PyPI), vẫn phục vụ cục bộ, gỡ `swagger-ui-bundle` | E2E: số `.opblock` ≥ số route; `ui_audit` after: Swagger "rendered" |
| UI-02 | P1 | test | Test cũ chỉ kiểm HTML Swagger trỏ asset cục bộ → không bắt được UI-01 | Kiểm thử thiếu bước render | Thêm E2E mở Swagger trong Edge và đếm operation | `test_swagger_renders_all_operations` |
| UI-03 | P1 | header / mọi tab | Chạy REAL_PRIVATE trên DB nghiên cứu (:8002) → nhãn giống hệt DB live | UI chỉ có 2 nhãn theo `MARKETLAB_MODE` | `/api/meta.data_scope` = `DEMO_OFFLINE` / `REAL_PRIVATE` / `RESEARCH_READ_ONLY` (REAL_PRIVATE nhưng DB không có migration EOD → chỉ đọc); nhãn và màu riêng | API test `data_scope`; ảnh after |
| UI-04 | P1 | Tổng quan (REAL live) | Thẻ "Dự báo đủ điều kiện = **0** trên 0 dự báo · 0 run" | Hiển thị số 0 khi dataset không có ModelRun | Hiển thị "—" + "Chưa có ModelRun (chưa cấu hình mô hình tạo dự báo)" | E2E/visual after |
| UI-05 | P1 | Tổng quan (REAL) | Thẻ "Đơn vị giá" in chuỗi dài 4 dòng cỡ 20px; mã dataset bị ngắt giữa từ; ProvenanceNote dài nhồi trong thẻ KPI | Thẻ KPI dùng cho văn bản dài | KPI chỉ giữ số/ngày ngắn; thêm khối "Nguồn, đơn vị & giới hạn" dạng danh sách mô tả | visual after (1440, 390) |
| UI-06 | P1 | Tổng quan / Vận hành | Không có chỉ báo dữ liệu mới/cũ; người xem phải tự so ngày | Thiếu phép so sánh phiên dự kiến vs giá mới nhất | API `overview.freshness` (phiên làm việc dự kiến theo giờ VN + cutoff, chưa tính lễ) → `CURRENT` / `BEHIND` / `SYNTHETIC_FIXED`; badge có chữ, không chỉ màu | API test freshness |
| UI-07 | P1 | Market Explorer chart | Đường Close nối liền mọi điểm; nếu một phiên có trong `TradingDay` nhưng thiếu giá, đường vẫn nối như có giao dịch; tiêu đề không ghi dataset/basis | `/api/prices/series` chỉ trả dòng có giá | Series trả cả phiên lịch thiếu giá (giá `null`, trong khoảng giá đầu–cuối của mã) → đường bị ngắt, có đánh dấu; tiêu đề chart ghi mã · dataset · khoảng ngày · SOURCE_CLOSE | API test gap; parity script cập nhật |
| UI-08 | P1 | mọi tab | F5 mất tab/mã/khoảng ngày; không có link chia sẻ | State chỉ nằm trong bộ nhớ | Đồng bộ state vào `location.hash` (tab, dataset, ticker, from, to, run, as_of) và khôi phục khi tải | E2E reload giữ nguyên |
| UI-09 | P1 | 390×844, 768×1024 | Thanh tab bị cắt không gợi ý; KPI 1 cột rất dài; bảng giá cắt cột Close/Volume không có gợi ý cuộn | CSS chưa tối ưu mobile | Tab bar cuộn ngang có fade; KPI 2 cột ở mobile; bảng có cột đầu dính + chú thích "vuốt ngang"; badge chế độ rút gọn | ui_audit after 390/768 |
| UI-10 | P2 | So sánh mô hình | Khung kết quả trống trước khi bấm (audit: "empty container") | Không có empty state | Thông báo hướng dẫn + ghi rõ dataset, TargetCode, as_of trong tiêu đề kết quả | ui_audit after |
| UI-11 | P2 | footer | Hiển thị "trên **.** ·" | `MARKETLAB_SQL_SERVER='.'` in nguyên văn | Hiển thị "(local)" | visual |
| UI-12 | P1 | tab bar | Không điều hướng tab bằng phím mũi tên; thiếu `aria-controls`/`tabindex` quản lý; focus dựa vào mặc định trình duyệt; không có skip link | Thiếu mẫu ARIA tabs | Roving tabindex + ←/→/Home/End, `aria-controls`, `:focus-visible` rõ, skip link, `aria-sort` cho cột sắp xếp | E2E bàn phím |
| UI-13 | P1 | Vận hành dữ liệu | Sau khi job chạy xong, token vẫn nằm trong ô mật khẩu | Không xóa sau khi gửi | Xóa ô token sau mỗi yêu cầu (thành công hay lỗi); hiển thị phạm vi (database, dataset, ngày) cạnh nút | E2E: ô token rỗng sau job |
| UI-14 | P2 | header | Không có cách chuyển giữa instance DEMO và REAL ngoài việc tự gõ cổng | Mỗi chế độ là một server riêng (thiết kế cố ý: không tự chuyển chế độ) | `MARKETLAB_PEERS` (chỉ URL loopback) → menu "Chuyển chế độ" là liên kết sang instance kia; Start script đặt mặc định 8000↔8001 | API test peers chỉ nhận loopback |
| UI-15 | P2 | Tổng quan | "EOD gần nhất: FAILED 2026-11-03" — là run thử nguồn hỏng có chủ đích, không ghi rõ run/nguồn kích hoạt | Thẻ chỉ lấy run mới nhất | Tách "Lần chạy gần nhất (#id, trigger, dry-run?)" và "Phiên đồng bộ thành công gần nhất" | visual |
| UI-16 | P2 | Market / Dự báo | Không có nút xóa bộ lọc; mã không hợp lệ chỉ báo lỗi sau khi gọi API | Thiếu control | Nút "Xóa lọc", kiểm tra mã/khoảng ngày phía client (vẫn giữ kiểm tra server) | E2E clear filter |
| UI-17 | P2 | mọi trạng thái lỗi | Thông báo lỗi không có cách thử lại | — | Nút "Thử lại" trong error state | E2E retry khi API lỗi |

Không phát hiện: console error, request 4xx/5xx ngoài dự kiến, tràn ngang trang, lộ token trong HTML/JS/network URL. Lỗi SQL/trigger: không phát hiện; không cần migration mới.
