# QA giao diện web — bản cuối (server-side rendered)

Ngày: 2026-11-06 (Asia/Ho_Chi_Minh). Nhánh `feature/marketlab-working-product`. Kiến trúc: Trình duyệt → ứng dụng web Python (FastAPI + Jinja2) → SQL Server; không REST JSON cho giao diện, không Swagger. Trạng thái: **PASS / FAIL / BLOCKED / NOT VERIFIED** theo bằng chứng bên dưới.

## 1. Issue trước / sau

| ID | Mức | Trạng thái | Bằng chứng |
|---|---|---|---|
| UI-01 Swagger không render (OpenAPI 3.1 vs Swagger UI 4) | P0 | Sửa ở `c376eec`; sau đó **Swagger bị gỡ theo yêu cầu** — `/api/docs` = 404 | `test_pages_render_and_no_api_or_swagger_surface`, `ui_audit/ssr/audit.json` |
| UI-02 test không kiểm render Swagger | P1 | Không còn áp dụng; test mới kiểm bề mặt đã gỡ | như trên |
| UI-03 nhãn RESEARCH_READ_ONLY | P1 | PASS | `test_research_read_only_scope` |
| UI-04 hiển thị 0 thay cho "không có ModelRun" | P1 | PASS ("—" + giải thích) | ảnh `10_real_overview_redacted_1440.png` |
| UI-05 thẻ KPI nhồi văn bản dài | P1 | PASS (khối "Nguồn, đơn vị & giới hạn") | ảnh `01_demo_overview_1440.png` |
| UI-06 chỉ báo dữ liệu mới/cũ | P1 | PASS (`CURRENT`/`BEHIND`/`SYNTHETIC_FIXED`, có chữ) | `test_scope_labels_and_freshness` |
| UI-07 biểu đồ nối qua phiên thiếu giá | P1 | PASS (ngắt đường + vạch gạch) | `test_chart_breaks_on_calendar_session_without_price` |
| UI-08 mất trạng thái khi F5 | P1 | PASS (query string) | E2E reload giữ bộ lọc |
| UI-09 mobile: tab, KPI, bảng | P1 | PASS | 4 viewport, 0 tràn ngang |
| UI-10 khung so sánh trống | P2 | PASS (empty state) | `test_compare_matches_usp_compare_models` |
| UI-11 footer "trên ." | P2 | PASS ("(local)") | ảnh |
| UI-12 bàn phím/ARIA | P1 | PASS (skip link, `aria-current`, `aria-sort`, `:focus-visible`, label cho mọi input) | `test_keyboard_navigation_and_dataset_picker` |
| UI-13 token còn trong ô sau khi gửi | P1 | PASS (form POST, trang mới không điền lại; `pageshow` xóa ô) | E2E: ô token rỗng sau lỗi |
| UI-14 chuyển chế độ | P2 | PASS (liên kết loopback `MARKETLAB_PEERS`) | `test_peers_accept_only_loopback` |
| UI-15 thẻ EOD gần nhất mơ hồ | P2 | PASS (tách run gần nhất / phiên SUCCESS gần nhất) | ảnh `14_real_ops_status_1440.png` |
| UI-16 thiếu xóa lọc / validate | P2 | PASS (server-side, HTTP 422 + thông báo) | 16 ca `test_invalid_inputs_render_explained_pages` |
| UI-17 thiếu "Thử lại" | P2 | PASS (trang lỗi 503 có "Thử lại") | `test_sql_downtime_renders_503_page` |
| UI-18 độ trễ 3–4 s ngắt quãng | P2 | **NOT DETERMINED** (không tái hiện; có `Server-Timing` + log chậm) | `docs/PRODUCT_UI_AUDIT.md` |
| EOD-01 KBS `end` không bao gồm sau nửa đêm | P1 | PASS | test hồi quy + run #38/#39 thật |
| SSR-01 `Origin: null` với `no-referrer` | P1 | PASS (`same-origin`) | E2E form REAL |

## 2. Checklist 4 viewport (DEMO và REAL, 5 trang mỗi viewport)

| Viewport | Tràn ngang | Control bị cắt/thiếu label | Console error | Request lỗi | Trình duyệt tự gọi dữ liệu | Kết quả |
|---|---|---|---|---|---|---|
| 1440×900 | 0 | 0 | 0 | 0 | 0 | PASS |
| 1366×768 | 0 | 0 | 0 | 0 | 0 | PASS |
| 768×1024 | 0 | 0 | 0 | 0 | 0 | PASS |
| 390×844 | 0 | 0 | 0 | 0 | 0 | PASS |

Nguồn: `uv run python scripts/ui_audit.py --phase ssr` (Edge headless), 40 màn hình, `tests/product_evidence/ui_audit/ssr/audit.json`; ảnh DEMO trong cùng thư mục, ảnh REAL trong thư mục private. Bảng rộng cuộn ngang trong khung, cột đầu dính, có gợi ý "Vuốt ngang". Ghi chú môi trường: phần mềm Kaspersky trên máy tự chèn script và XHR tới `*.kaspersky-labs.com`; các request đó bị loại khỏi phép đếm vì không thuộc ứng dụng.

## 3. Accessibility (cơ bản)

PASS: skip link là điểm Tab đầu tiên; điều hướng bằng liên kết thật với `aria-current="page"`; mọi input/select có `<label>`; bảng có `<caption>` (ẩn), `scope="col"/"row"`, cột sắp xếp có `aria-sort`; `:focus-visible` viền 3 px màu tương phản; trạng thái/nhãn luôn có chữ (không chỉ dựa màu); lỗi dùng `role="alert"`; job EOD dùng `aria-live`; biểu đồ có `role="img"` + mô tả, đọc được bằng phím ←/→; có bảng OHLCV tương đương số liệu biểu đồ; `prefers-reduced-motion` tắt hiệu ứng quay. NOT VERIFIED: kiểm tra bằng trình đọc màn hình thật (NVDA/Narrator) và đo contrast tự động.

## 4. Đối chiếu UI ↔ SQL (1:1, số trên trang do máy chủ render)

| Hành trình | Trang | Đối chiếu SQL | Kết quả |
|---|---|---|---|
| Mở dashboard, đọc KPI | `/?ds=1` | `COUNT(*) DailyPrice`, `COUNT(DISTINCT StockId)`, `fn_EligiblePredictions(today)` → 280 / 8 / 256 | PASS (`test_overview_matches_sql`) |
| Giá gần nhất | `/` | `vw_LatestStockPrice` từng dòng (Close, Volume) | PASS |
| Lọc mã + ngày, sắp xếp | `/market?t=DEMO03&f=2025-02-01&to=2025-02-14&sort=close&order=asc` | SELECT tham số hóa cùng điều kiện, ORDER BY ClosePrice | PASS (10 dòng, đúng thứ tự) |
| Biểu đồ | cùng trang | số điểm JSON nhúng = số dòng SQL; basis `SOURCE_CLOSE` | PASS |
| Hiệu năng run 1 tại as_of 2026-07-01 | `/forecast?run=1&as_of=2026-07-01` | `usp_GetModelPerformance` (128 dòng, Accuracy, Brier) | PASS (sai lệch < 1e-9) |
| So sánh run 1,2 | `/compare?runs=1&runs=2&…` | `usp_CompareModels` (128 quan sát chung, Accuracy) | PASS |
| Trạng thái EOD + lỗi | `/ops` (REAL) | `ops.EodRun` MAX(SessionDate) SUCCESS, số run | PASS (`verify_web_vs_sql.py` REAL 11/11) |
| Dry run không ghi | form `/ops/eod` (REAL thật, phiên 05/11) | `ops.EodRun` #39: WEB, DRY_RUN_OK, 30/30, inserted 0; `DailyPrice` vẫn 780 | PASS |

Instance đang chạy: `scripts/verify_web_vs_sql.py` — DEMO 9/9 PASS (`tests/product_evidence/web_vs_sql_demo.json`), REAL_PRIVATE `MarketLabVN30_Live` 11/11 PASS (báo cáo private, chỉ số đếm/hash).

## 5. Lệnh kiểm thử và kết quả (2026-11-06 00:51, máy cục bộ)

| Lệnh | Kết quả |
|---|---|
| `uv run pytest tests/product -v --junitxml=tests/product_evidence/logs/pytest_product.xml` | **102 passed**, 0 failed, 0 skipped, 55,5 s (unit 36, EOD integration 23, SQL regression 5, web 31, E2E Edge 7) |
| `python -m unittest discover -s tests -p "test_*.py"` | 11 OK |
| `python scripts/run_public_regression.py --server .` | PASS: 44 ca SQL, 16 query, 2 live demo, hash 13 bảng trước = sau |
| `python scripts/ui_audit.py --phase ssr` | 40/40 PASS |
| `python scripts/verify_web_vs_sql.py` (DEMO, REAL) | 9/9, 11/11 PASS |
| `python scripts/check_publication.py` | FAIL dự kiến (allowlist chưa đăng ký file mới — phạm vi khác với test) |

Số 88 (phiên đầu) và 100 (sau polish SPA) là số của các phiên bản trước; con số hiện hành là **102**.

## 6. Ảnh chính thức (sau khi sửa)

`report/final/assets/screens/` + `screens_manifest.json` (route, chế độ, viewport, thời điểm, phân loại, che dữ liệu): 11 ảnh DEMO (dashboard, biểu đồ + tooltip, bảng lọc/sắp xếp, dự báo, so sánh, vận hành bị khóa, lỗi validate, tablet, 2 mobile, trang 404 thay Swagger) và 6 ảnh REAL (tổng quan, biểu đồ — giá/volume làm mờ; kết quả job dry run, chi tiết run, trạng thái EOD, mobile — chỉ số đếm/trạng thái).

## 7. Tồn đọng

* UI-18 chưa xác định nguyên nhân (P2).
* Trình đọc màn hình thật: NOT VERIFIED.
* Lịch Task Scheduler 16:10 tự chạy: NOT VERIFIED (task để Disabled, chưa có chấp thuận).
* Job EOD chạy từ web chỉ được theo dõi trong tiến trình server hiện tại; nếu server dừng giữa chừng, run vẫn có trong `ops.EodRun` (có thể đánh dấu ABANDONED) nhưng trang `/ops/jobs/<id>` mất.
