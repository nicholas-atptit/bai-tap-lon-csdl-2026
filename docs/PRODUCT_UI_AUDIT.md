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

## Issue phát hiện thêm trong lúc polish (trước khi đổi kiến trúc)

| ID | Mức | Màn hình | Tái hiện | Nguyên nhân | Sửa | Test |
|---|---|---|---|---|---|---|
| UI-18 | P2 | tải trang đầu ở instance REAL | 2 lần quan sát `/api/stocks` 3,6–4,2 s ngay sau khi khởi động lại | Không xác định: 160 lần gọi HTTP + 60 lần kết nối trực tiếp + thử sau 75 s rảnh đều < 0,1 s | Thêm `Server-Timing` vào mọi response và log `slow request` khi > 1 s để bắt lại nếu tái diễn | `test_web.py::test_chart_breaks…` kiểm tra header `Server-Timing`. **Nguyên nhân: NOT DETERMINED** |
| EOD-01 | **P1** | dry run qua UI trên dữ liệu thật (06/11 00:24) | Phiên 05/11 báo `PARTIAL/MISSING_TICKERS 20/30` dù 22:56 hôm trước đủ 30/30 | Sau nửa đêm giờ VN, KBS coi `end` là **không bao gồm**; pipeline xin cửa sổ `[D−10, D]` | Xin `[D−10, min(D+1, hôm nay)]` rồi bỏ nến sau D trước khi validate | `test_exclusive_end_provider_and_provisional_next_day_row` — đã chứng minh FAIL khi bỏ bản sửa, PASS khi có. Run #38 (dry run thật) sau sửa: DRY_RUN_OK 30/30 |
| UI-19 | P2 | mọi trang | Dán deep link khác (chỉ đổi `#…`) vào cùng tab không áp dụng | SPA không nghe `hashchange` | (đã sửa ở bản SPA; bản cuối dùng query string phía server nên vấn đề không còn tồn tại) | `test_demo_journey_end_to_end` (reload giữ bộ lọc) |

## Thay đổi kiến trúc theo yêu cầu: bỏ API Gateway / REST / Swagger

Commit polish `c376eec` là bản cuối của kiến trúc "SPA + REST JSON + Swagger". Theo yêu cầu mới của chủ dự án, kiến trúc cuối là:

```text
Trình duyệt ──HTTP (HTML)──► Ứng dụng web Python (FastAPI làm framework ASGI + Jinja2) ──pyodbc──► SQL Server
EOD Worker (CLI / Task Scheduler / form web có CSRF) ──► SQL Server (DB nghiệp vụ) + DB Ops
```

| Hạng mục | Trước | Sau |
|---|---|---|
| Lấy dữ liệu cho giao diện | Trình duyệt gọi 19 endpoint JSON `/api/*` | Máy chủ chạy truy vấn (cùng `queries.py`) và trả HTML hoàn chỉnh; CSP `connect-src 'none'` — trình duyệt không thể tự gọi dữ liệu |
| Swagger/OpenAPI | `/api/docs`, `/api/openapi.json` | Gỡ bỏ (404); `openapi_url=None`; gỡ dependency `swagger-ui-py` (và `pyyaml`) |
| Ghi EOD thủ công | `POST /api/ops/eod` JSON + header token | `POST /ops/eod` form HTML: CSRF double-submit (cookie `ml_csrf` HttpOnly SameSite=Strict + trường ẩn), token trong ô mật khẩu, ô xác nhận bắt buộc cho SYNC, kiểm Origin/Sec-Fetch-Site, khóa sau 5 lần sai, một job tại một thời điểm; kết quả qua trang `/ops/jobs/<id>` tự làm mới |
| Trạng thái URL | hash `#tab=…` | query string thật (`/market?ds=1&t=ACB&f=…`) — refresh/bookmark ổn định, chạy cả khi tắt JavaScript (trừ biểu đồ) |
| Liveness | `/api/health` JSON | `/health` text (chỉ để script khởi động kiểm tra; không phải API dữ liệu) |
| Nhật ký | `TriggerKind='API'` | `TriggerKind='WEB'` — cần **ops schema v2** (`sql/15_ops_schema_v2.sql`, có rollback); đã backup DB ops (`MarketLabVN30_Ops_pre_v2_20261106.bak`, RESTORE VERIFYONLY hợp lệ) trước khi áp |
| Giữ nguyên | — | 13 bảng, procedure/function/view/trigger, `queries.py`, `db.py`, toàn bộ `eod/*`, CLI, script PowerShell, Task Scheduler |

Bỏ đi: `marketlab_app/api.py`, `web/index.html`, `web/app.js`, `tests/product/test_api.py`, `scripts/verify_api_vs_sql.py`, `scripts/ui_api_sql_journeys.py`, ảnh SPA cũ. Thêm: `marketlab_app/web_app.py`, `templates/*.html`, `web/enhance.js` (chỉ vẽ biểu đồ từ JSON nhúng, tự gửi form chọn dataset, hộp xác nhận), `tests/product/test_web.py`, `scripts/verify_web_vs_sql.py`.

Lỗi phát hiện khi đổi kiến trúc: với `Referrer-Policy: no-referrer`, Chromium gửi `Origin: null` cho form POST cùng origin → bị chặn 403. Sửa bằng `Referrer-Policy: same-origin` (không nới kiểm tra Origin). Test: `test_real_mode_ops_form_and_job_page`.

Audit lại sau đổi kiến trúc (`scripts/ui_audit.py --phase ssr`): 40/40 màn hình (2 chế độ × 4 viewport × 5 trang) không issue, 0 console error, 0 request lỗi, 0 lần trình duyệt tự lấy dữ liệu, `/api/docs`, `/api/openapi.json`, `/docs`, `/openapi.json` đều 404. Kết quả: `tests/product_evidence/ui_audit/ssr/audit.json`.
