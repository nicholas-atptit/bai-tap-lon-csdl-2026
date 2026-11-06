# Bằng chứng kiểm thử sản phẩm (bản cuối, ứng dụng web render phía máy chủ)

> **Cập nhật 06/11/2026 (Web FINAL + backfill 2023 → nay):** bộ kiểm thử hiện hành là **140 ca, 140 passed**, gồm thêm `test_unit_backfill.py` (11), `test_integration_backfill.py` (17), `test_web_backfill.py` (7), bridge 8 ca và E2E 8 ca. Kết quả, đối chiếu UI↔SQL (DEMO 26/26, LIVE 38/38), audit UI 48/48 và số đo tốc độ ở [FINAL_WEB_ACCEPTANCE.md](FINAL_WEB_ACCEPTANCE.md). Các mục bên dưới là bằng chứng của phiên bản trước (102 ca), giữ lại để đối chiếu lịch sử.

Máy: Windows 11 Pro 10.0.26300, SQL Server 2025 Standard Developer 17.0.1145.4 (`.`), ODBC Driver 18, Python 3.12.10, uv 0.10.10, Microsoft Edge (Playwright 1.52). Môi trường Python ghim trong `uv.lock`. Nhánh `feature/marketlab-working-product`.

Bằng chứng công khai: `tests/product_evidence/` (log, JUnit XML, audit UI, đối chiếu DEMO) và `report/final/assets/screens/`. Bằng chứng có dữ liệu thật: `tests/product_evidence/private/` (**gitignored**) — tài liệu này chỉ chép số đếm, trạng thái, mã run, không chép giá.

## 1. Bộ kiểm thử hiện hành (chạy 2026-11-06 00:51)

| Bộ | File | Số ca | Kết quả |
|---|---|---|---|
| Unit: OHLCV, ngày/timezone, phiên, cấu hình | `test_unit_normalize_calendar.py` | 30 | PASS |
| Unit: bridge nguồn (timeout, lỗi import, lỗi từng mã) | `test_unit_provider_bridge.py` | 6 | PASS |
| Integration EOD (DB cô lập `MarketLabVN30_IT_*`, FakeProvider chỉ trong test) | `test_integration_eod.py` | 23 | PASS |
| Integration SQL: 44 test gốc + 16 query trên bản demo đã migrate, rollback/re-apply, preflight | `test_integration_sql_regression.py` | 5 | PASS |
| Web server-side: route, validation, CSRF/token/khóa, luồng job, 503, đối chiếu HTML↔SQL | `test_web.py` | 31 | PASS |
| E2E Edge: hành trình 5 trang, bàn phím, 4 viewport, form EOD REAL fixture | `test_e2e_ui.py` | 7 | PASS |
| **Tổng** `uv run pytest tests/product` | | **102** | **102 passed, 0 failed, 0 skipped** (55,5 s) |
| Unit test gốc của repo | `python -m unittest discover -s tests` | 11 | OK |
| Regression công khai gốc trên `MarketLabVN30_Demo` | `scripts/run_public_regression.py --server .` | 44 ca + 16 query + 2 demo | PASS, hash 13 bảng trước = sau |
| Gate công bố | `scripts/check_publication.py` | — | FAIL dự kiến (allowlist chưa đăng ký file mới; khác phạm vi với test) |

Log: `tests/product_evidence/logs/pytest_product.log`, `pytest_product.xml`, `original_unittest.log`, `original_public_regression.log`. Các phiên bản trước báo 88 (phiên đầu, còn REST API) và 100 (polish SPA); không dùng các con số đó cho bản cuối.

Các DB `MarketLabVN30_IT_*` do test tạo được gắn `MarketLabPurpose=INTEGRATION_TEST` và chỉ những DB đó bị xóa sau test. `MarketLabVN30_Demo` và `MarketLabVN30_Research_20261027` chỉ được đọc.

## 2. EOD với nguồn thật (KBS qua vnstock 3.5.1) — `MarketLabVN30_Live`

| Run | Phiên | Kích hoạt | Kết quả | Yêu cầu/Nhận | Thêm | Không đổi |
|---|---|---|---|---|---|---|
| 1 | 2026-11-04 | CLI dry run | DRY_RUN_OK | 30/30 | 0 (sẽ thêm 30) | 0 |
| 2–26 | 2026-10-01 … 2026-11-04 | CLI backfill 25 ngày thường | 25 × SUCCESS | 30/30 | 750 | 0 |
| 27 | 2026-11-05 | CLI | SUCCESS | 30/30 | 30 | 0 |
| 28 | 2026-11-05 | CLI chạy lại | SUCCESS idempotent | 30/30 | 0 | 30 |
| 29 | 2026-11-01 | CLI | NO_SESSION / WEEKEND | — | 0 | 0 |
| 30 | 2026-09-02 | CLI | NO_SESSION / PROVIDER_CALENDAR_GAP | — | 0 | 0 |
| 31, 34 | 2026-11-06 | CLI | SKIPPED / FUTURE_DATE (exit 10) | — | 0 | 0 |
| 32 | 2026-11-05 | REST (đã gỡ) dry run | DRY_RUN_OK | 30/30 | 0 | 30 |
| 33 | 2026-11-05 | PowerShell dry run | DRY_RUN_OK | 30/30 | 0 | 30 |
| 35 | 2026-11-04 | PowerShell chạy lại | SUCCESS idempotent | 30/30 | 0 | 30 |
| 36 | 2026-11-03 | PowerShell, interpreter sai | FAILED / PROVIDER_NOT_CONFIGURED (exit 30) | — | 0 | 0 |
| 37 | 2026-11-05 | REST dry run lúc 00:24 | **PARTIAL / MISSING_TICKERS 10/30** — lỗi EOD-01 (KBS `end` không bao gồm), không ghi gì | 30/10 | 0 | 0 |
| 38 | 2026-11-05 | REST dry run sau sửa | DRY_RUN_OK | 30/30 | 0 | 30 |
| 39 | 2026-11-05 | **form web (WEB)** dry run | DRY_RUN_OK | 30/30 | 0 (sẽ thêm 0) | 30 |
| — | 2026-11-05 | Task Scheduler `-RunNow` (task Disabled) | ALREADY_SUCCEEDED, exit 0 | — | — | — |

Tổng (truy vấn `ops.EodRun`): 28 SUCCESS (780 dòng thêm), 5 DRY_RUN_OK, 2 NO_SESSION, 2 SKIPPED, 1 PARTIAL (dry run), 1 FAILED; `ops.PriceLoadLineage` = 780; DB live: 780 giá, 26 phiên, 30 mã, ObservedThrough 2026-11-05, đúng 13 bảng. Số dòng trước backfill 0/0, sau dry run vẫn 0/0, sau backfill 750/25, sau run 27 là 780/26, sau mọi lần chạy lại/dry run vẫn 780/26. Giá ACB 04/11 trong DB trùng nến lấy độc lập bằng vnstock 4.0.9 trước khi đồng bộ.

## 3. Đối chiếu trang web với SQL (server đang chạy)

| Instance | Kết quả | Báo cáo |
|---|---|---|
| DEMO_OFFLINE `MarketLabVN30_Demo` (:8000) | 9/9 PASS | `tests/product_evidence/web_vs_sql_demo.json` |
| REAL_PRIVATE `MarketLabVN30_Live` (:8001) | 11/11 PASS | private |

Chi tiết hành trình UI↔SQL: `docs/PRODUCT_UI_QA.md` mục 4.

## 4. Windows thực tế

`Setup-MarketLab.ps1` PASS (Windows PowerShell 5.1); `Start-MarketLab.ps1 -Background` khởi động 8000/8001 và in URL; `Stop-MarketLab.ps1` dừng đúng tiến trình; `Run-MarketLab-EOD.ps1` cho exit 0/0/10/0/30 đúng bảng mã; `Install-MarketLab-EODTask.ps1` cài task **Disabled**, `-RunNow` chạy một lần qua Task Scheduler (exit 0) rồi trả về Disabled. Lịch tự động 16:10: **NOT VERIFIED** (cần bạn `-Enable`).

## 5. Chưa xác minh / bị chặn

* Lịch Task Scheduler tự chạy: NOT VERIFIED. Migration DB nghiên cứu: NOT DONE (cần backup + xác nhận).
* vnstock 4.0.9 trong luồng ghi thật: NOT VERIFIED (dữ liệu thật ghi bằng 3.5.1). Express/SQL Server 2016, đăng nhập SQL Authentication thật, trình đọc màn hình: NOT VERIFIED.
* Push/PR GitHub: BLOCKED (quyền bị chặn trong phiên làm việc).
