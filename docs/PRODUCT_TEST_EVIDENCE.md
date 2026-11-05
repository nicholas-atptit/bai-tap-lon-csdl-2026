# Bằng chứng kiểm thử sản phẩm — 2026-11-05

Máy: Windows 11 Pro 10.0.26300, SQL Server 2025 Standard Developer 17.0.1145.4 (`.`), ODBC Driver 18, Python 3.12.10, uv 0.10.10. Môi trường Python ghim trong `uv.lock`. Nhánh `feature/marketlab-working-product`.

Bằng chứng công khai: `tests/product_evidence/` (log, JUnit XML, screenshot dữ liệu mô phỏng/fixture). Bằng chứng dữ liệu thật: `tests/product_evidence/private/` (**gitignored**, không đẩy lên GitHub) — tài liệu này chỉ chép lại số đếm, trạng thái, mã run, không chép giá.

## 1. Kết quả theo bộ test

| Bộ | Lệnh | Kết quả | Log |
|---|---|---|---|
| Unit (OHLCV, ngày/timezone, phiên, config, bridge/timeout) | `uv run pytest tests/product/test_unit_*.py` | **36 PASS** | `logs/pytest_product.log` |
| Integration EOD (DB cô lập `MarketLabVN30_IT_*`, FakeProvider chỉ trong test) | `uv run pytest tests/product/test_integration_eod.py` | **22 PASS** | như trên |
| Integration SQL: 44 test gốc + 16 query trên bản demo đã migrate, rollback/re-apply, preflight | `uv run pytest tests/product/test_integration_sql_regression.py` | **5 PASS** (trong đó `PASS|44`) | như trên |
| API (input sai, paging, Host/Origin/token/lockout, SQL downtime, mode mismatch, API↔SQL) | `uv run pytest tests/product/test_api.py` | **23 PASS** | như trên |
| UI E2E (uvicorn thật + Microsoft Edge headless) | `uv run pytest tests/product/test_e2e_ui.py` | **2 PASS**, 7 screenshot | `screenshots/` |
| **Tổng** | `uv run pytest tests/product -v --junitxml=…` | **88 passed, 0 failed, 0 skipped** (52,9 s) | `logs/pytest_product.xml` |
| Unit test gốc của repo | `python -m unittest discover -s tests -p "test_*.py"` | **11 OK** | `logs/original_unittest.log` |
| Regression công khai gốc trên `MarketLabVN30_Demo` | `python scripts/run_public_regression.py --server .` | **PASS**: 44 ca, 16 query, 2 live demo, hash 13 bảng trước = sau | `logs/original_public_regression.log` |
| Gate công bố | `python scripts/check_publication.py` | **FAIL (dự kiến)**: file mới chưa có trong allowlist đã review | — |

Các DB `MarketLabVN30_IT_*` do test tạo được gắn `MarketLabPurpose=INTEGRATION_TEST` và chỉ những DB đó bị xóa khi test xong. `MarketLabVN30_Demo` và `MarketLabVN30_Research_20261027` chỉ được đọc.

## 2. Kịch bản integration đã kiểm (FakeProvider — không phải bằng chứng nguồn thật)

Cuối tuần / tương lai / trước cutoff (không gọi provider, không ghi) • nghỉ lễ theo chuỗi tham chiếu → NO_SESSION • dữ liệu chưa có → SKIPPED • lịch lệch với `TradingDay` → FAILED • provider timeout/HTTP lỗi → FAILED • thiếu 2 mã → PARTIAL, 0 dòng • OHLC sai / volume âm / NaN → FAILED, 0 dòng • trùng nguồn mâu thuẫn → FAILED • dry run → DRY_RUN_OK, số dòng không đổi • dòng thứ 4 vi phạm CHECK *bên trong SQL* → rollback toàn phiên (giá, TradingDay, ObservedThrough) • universe thiếu → 51142 • applock bị giữ → SKIPPED/LOCK_BUSY • SUCCESS (+5 dòng, ObservedThrough 10-01→10-02, lineage 5, dự báo horizon-1 trưởng thành 4/5 vì 1 mã thiếu endpoint) • chạy lại → SUCCESS inserted 0 / unchanged 5 • giá đã chốt bị đổi → FAILED + 1 reconciliation PENDING, giá cũ giữ nguyên • phiên kế tiếp + drift probe phát hiện giá cũ đổi → cảnh báo + reconciliation • số liệu khớp `usp_GetModelPerformance` (Accuracy/Brier sai lệch < 1e-9/1e-12) • `as_of` trước TargetDate → 0 đủ điều kiện • so sánh run khác TargetDefinition → 51020/409 • as_of quá sớm → 51021/422 • backfill dry-run/giới hạn/dừng ở PARTIAL • CHECK của `ops.EodRun` chặn "SUCCESS giả" • DEMO_OFFLINE từ chối EOD.

## 3. EOD với nguồn thật (KBS qua vnstock 3.5.1) — `MarketLabVN30_Live`

DB REAL_PRIVATE **mới** (không phải DB nghiên cứu), universe 30 mã snapshot VN30 06/2026. Thời điểm: 2026-11-05 15:56–16:11 UTC (22:56–23:11 giờ VN, sau phiên).

| Run | Phiên | Kích hoạt | Kết quả | Yêu cầu/Nhận | Thêm | Không đổi | ObservedThrough |
|---|---|---|---|---|---|---|---|
| 1 | 2026-11-04 | CLI dry run | DRY_RUN_OK (sẽ thêm 30) | 30/30 | 0 | 0 | 2026-09-30 → 2026-09-30 |
| 2–26 | 2026-10-01 … 2026-11-04 | CLI backfill (25 ngày thường) | 25 × SUCCESS | 30/30 mỗi phiên | 750 | 0 | 2026-09-30 → 2026-11-04 |
| 27 | 2026-11-05 | CLI | SUCCESS | 30/30 | 30 | 0 | 2026-11-04 → 2026-11-05 |
| 28 | 2026-11-05 | CLI (chạy lại) | SUCCESS idempotent | 30/30 | **0** | **30** | không đổi |
| 29 | 2026-11-01 | CLI | NO_SESSION / WEEKEND | — | 0 | 0 | — |
| 30 | 2026-09-02 | CLI | NO_SESSION / PROVIDER_CALENDAR_GAP (nến VN30 28/08 và 03/09, không có 02/09) | — | 0 | 0 | — |
| 31, 34 | 2026-11-06 | CLI | SKIPPED / FUTURE_DATE (exit 10) | — | 0 | 0 | — |
| 32 | 2026-11-05 | **UI → API** dry run | DRY_RUN_OK | 30/30 | 0 | 30 | — |
| 33 | 2026-11-05 | Run-MarketLab-EOD.ps1 -DryRun | DRY_RUN_OK (exit 0) | 30/30 | 0 | 30 | — |
| 35 | 2026-11-04 | Run-MarketLab-EOD.ps1 (chạy lại ngày cũ) | SUCCESS idempotent, drift probe: 0 thay đổi | 30/30 | 0 | 30 | — |
| 36 | 2026-11-03 | Run-MarketLab-EOD.ps1, interpreter sai | FAILED / PROVIDER_NOT_CONFIGURED (**exit 30**) | — | 0 | 0 | — |
| — | 2026-11-05 | Task Scheduler (`-RunNow`, task disabled) | ALREADY_SUCCEEDED, exit 0 (không tạo run mới) | — | — | — | — |

Số dòng trước/sau (cùng dataset): trước backfill `DailyPrice=0, TradingDay=0, ObservedThrough=2026-09-30`; sau dry run vẫn `0/0/2026-09-30`; sau backfill `750/25/2026-11-04`; sau run 27 `780/26/2026-11-05`; sau run 28 vẫn `780/26/2026-11-05`. Tổng: 28 SUCCESS (780 dòng thêm), 3 DRY_RUN_OK, 2 NO_SESSION, 2 SKIPPED, 1 FAILED; `ops.PriceLoadLineage` = 780 dòng; DB vẫn đúng 13 bảng.

Đối chiếu độc lập: giá ACB 2026-11-04 lưu trong DB (20,30/20,55/20,15/20,50/11.819.700) trùng khớp nến mà smoke test vnstock 4.0.9 (venv cô lập) trả về trước khi đồng bộ.

## 4. Đối chiếu API (HTTP, server thật) với SELECT SQL

`scripts/verify_api_vs_sql.py` — so datasets, `vw_LatestStockPrice` (hash), chuỗi giá 1 mã (số dòng + hash), tổng phân trang, số dự báo đủ điều kiện theo run tại as_of, accuracy với `vw_ModelPerformance`, ngày SUCCESS gần nhất và số run trong ops:

| Instance | Kết quả | Báo cáo |
|---|---|---|
| DEMO_OFFLINE `MarketLabVN30_Demo` (:8000) | 9/9 PASS | `api_vs_sql_demo.json` |
| REAL_PRIVATE `MarketLabVN30_Live` (:8001) | 11/11 PASS | private |
| REAL_PRIVATE chỉ-đọc `MarketLabVN30_Research_20261027` (:8002) | 11/11 PASS; `/api/models/compare` = `usp_CompareModels` (600 quan sát giao, Accuracy 0,5800/0,5683) | private |

## 5. Windows thực tế

`Setup-MarketLab.ps1` (Windows PowerShell 5.1) PASS; `Start-MarketLab.ps1 -Background` khởi động 3 instance (8000/8001/8002) và in URL; `Run-MarketLab-EOD.ps1` cho exit 0/0/10/0/30 đúng bảng mã; `Install-MarketLab-EODTask.ps1` cài task **Disabled** (T2–T6 16:10/17:30/19:30 local = giờ VN), `-RunNow` chạy một lần qua Task Scheduler và trả task về Disabled. **Lịch tự động (trigger theo giờ) chưa được bật — NOT VERIFIED theo thiết kế, cần bạn đồng ý (`-Enable`).**

## 6. Screenshot (render thật, không dựng ảnh)

`tests/product_evidence/screenshots/`: `01_overview_demo.png`, `02_market_explorer_demo.png` (chart + tooltip), `03_forecast_analysis_demo.png`, `04_model_comparison_demo.png`, `05_data_operations_demo.png`, `06_overview_mobile_demo.png` (420 px), `07_ops_missing_provider_it_fixture.png` (REAL trên fixture test: token sai → INVALID_OPS_TOKEN, thiếu nguồn → FAILED PROVIDER_NOT_CONFIGURED). Ảnh dữ liệu thật `real_01…04` nằm trong thư mục private.

## 7. Chưa xác minh / bị chặn

* Trigger lịch tự động chạy lúc 16:10 thật: NOT VERIFIED (task để Disabled).
* Migration DB nghiên cứu: NOT DONE (cần backup + xác nhận của chủ dự án).
* vnstock 4.0.9 trong luồng ghi thật: NOT VERIFIED (chỉ smoke đọc); dữ liệu thật được ghi bằng 3.5.1.
* Express / SQL Server 2016: NOT VERIFIED.
* SQL Authentication: chỉ unit test chuỗi kết nối/redaction; chưa đăng nhập thật bằng SQL login.
