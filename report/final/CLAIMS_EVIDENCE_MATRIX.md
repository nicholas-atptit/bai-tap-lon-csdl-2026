# Ma trận tuyên bố – bằng chứng (báo cáo FINAL)

Nguồn mã: nhánh `feature/marketlab-working-product`, ứng dụng web ở commit `701d0c5` (commit chứa báo cáo: xem `QA_REPORT.md`). Ngày tái xác minh: 05–06/11/2026, máy cục bộ (Windows 11 Pro, SQL Server 2025 Developer 17.0.1145.4, instance `.`). Trạng thái: **PASS** (tái xác minh trong lần hoàn thiện này), **HISTORICAL** (theo log bàn giao, không chạy lại), **NOT VERIFIED**, **NOT DONE**, **NOT IMPLEMENTED**, **BLOCKED**.

| # | Tuyên bố trong báo cáo | Lệnh / artefact kiểm chứng | Phạm vi | Kết quả |
|---|---|---|---|---|
| 1 | 13 bảng nghiệp vụ, 4 procedure, 3 function (2 scalar + 1 inline TVF), 4 view, 10 trigger | `sys.objects` / `sys.partitions` trên `MarketLabVN30_Demo` (06/11/2026); Bảng 18b | Demo | PASS |
| 2 | 44 ca SQL PASS | `scripts/run_public_regression.py --server .` → `PASS|44`; log `tests/product_evidence/logs/original_public_regression.log`, thư mục `tests/runs/public_20261105T175220966677Z/` | Demo | PASS |
| 3 | Hash toàn bộ 13 bảng trước = sau bộ thử | cùng lệnh, `all_13_tables_unchanged: true` | Demo | PASS |
| 4 | 176 lượt PASS lịch sử = 44 ca × 4 DB, không phải 176 ca độc lập | README, `tests/reference_evidence/final_regression_summary.json` | lịch sử | HISTORICAL |
| 5 | 44/44 PASS sau migration 13 | `tests/product/test_integration_sql_regression.py::test_original_44_validation_tests_pass_after_migration` | bản sao IT | PASS |
| 6 | 16 truy vấn chạy được, số dòng demo khớp lịch sử (Bảng 21) | `query_Q01..Q16.log` trong thư mục regression ở #2 | Demo | PASS |
| 7 | Cột "Thật" của Bảng 21 | báo cáo gốc | nghiên cứu | HISTORICAL (không chạy lại trên DB nghiên cứu) |
| 8 | Bảng 22: 600 quan sát, Accuracy 0,580000/0,568333, Brier 0,247666/0,252362, log loss 0,688478/0,698052 | `EXEC dbo.usp_CompareModels '1,2','20250901','20250930','20260701'` + truy vấn log loss trên tập giao, chỉ đọc trên `MarketLabVN30_Research_20261027` | nghiên cứu, chỉ đọc | PASS |
| 9 | Ví dụ procedure/function trong Chương 3 (51012, usp_GetModelPerformance, usp_CompareModels, fn_CalculateReturn, vw_ModelPerformance) | sqlcmd 06/11/2026 trên Demo; ghi lại giá giống hệt là no-op, số dòng 280 → 280 | Demo | PASS |
| 10 | Live demo: CHECK Volume âm bị từ chối 547, BEFORE/DURING/AFTER, hash bằng nhau, 0 transaction mở | `live_demo_1.log` (regression #2) | Demo | PASS |
| 11 | Migration 13 giữ đúng 13 bảng, thêm 1 procedure trong schema ops; rollback khôi phục nguyên văn trigger | `test_rollback_restores_original_trigger_and_reapply_is_idempotent`; `sys.objects` trên Live | IT + Live | PASS |
| 12 | Database Ops tách biệt, schema v2 (TriggerKind WEB) | `SELECT MAX(Version) FROM ops.SchemaVersion` = 2; backup `MarketLabVN30_Ops_pre_v2_20261106.bak` (RESTORE VERIFYONLY hợp lệ) | Ops | PASS |
| 13 | 780 giá OHLCV thật, 30 mã, 26 phiên (750 backfill 01/10–04/11 + 30 phiên 05/11) | `ops.EodRun` #2–27; `COUNT(*)` DailyPrice = 780, TradingDay = 26, `ops.PriceLoadLineage` = 780 | Live | PASS |
| 14 | Chạy lại không thêm dòng | run #28 (05/11) và #35 (04/11): inserted 0, unchanged 30 | Live | PASS |
| 15 | NO_SESSION 02/09/2026 theo bằng chứng nguồn | run #30, `ProviderMeta.calendar` = PROVIDER_CALENDAR_GAP (nến 28/08, 03/09) | Live | PASS |
| 16 | Nguồn KBS qua vnstock 3.5.1 | `ProviderMeta.provider.package_version` của run #27 | Live | PASS |
| 17 | FPT 09/2025 lệch ~9% so với bản trích cũ, cùng Volume (điều chỉnh hồi tố) | probe chỉ đọc ngày 05/11/2026 so với DB nghiên cứu (giá trị cụ thể không đưa vào repo vì quyền phân phối dữ liệu nguồn chưa rõ) | quan sát | PASS (quan sát 3 phiên; không kết luận định lượng chung) |
| 18 | PARTIAL #37 do biên `end` của nguồn sau nửa đêm, không ghi gì; sửa và kiểm hồi quy | run #37/#38; `test_exclusive_end_provider_and_provisional_next_day_row` FAIL khi bỏ bản sửa, PASS khi có | Live + test | PASS |
| 19 | Dry run qua biểu mẫu web không ghi dữ liệu | run #39 WEB DRY_RUN_OK 30/30; DailyPrice vẫn 780 | Live | PASS |
| 20 | 102 ca kiểm thử phần mở rộng PASS (30+6+23+5+31+7) | `uv run pytest tests/product` → `tests/product_evidence/logs/pytest_product.xml` | IT, Demo | PASS |
| 21 | Không còn API Gateway/REST/Swagger | `/api/docs`, `/api/openapi.json`, `/docs`, `/openapi.json` → 404 (`ui_audit/ssr/audit.json`); `test_pages_render_and_no_api_or_swagger_surface` | ứng dụng | PASS |
| 22 | Trình duyệt không kết nối SQL / không tự gọi dữ liệu | CSP `connect-src 'none'`; 0 XHR/fetch tới origin ứng dụng trong 40 màn hình | ứng dụng | PASS |
| 23 | Giao diện không lỗi ở 4 kích thước | `scripts/ui_audit.py --phase ssr`: 40/40, 0 console error, 0 request lỗi | Demo + Live | PASS |
| 24 | Số liệu trang khớp SQL | `scripts/verify_web_vs_sql.py`: DEMO 9/9 (`tests/product_evidence/web_vs_sql_demo.json`), REAL 11/11 (báo cáo private) | Demo + Live | PASS |
| 25 | Ảnh giao diện là ảnh thật sau khi hoàn thiện | `report/final/assets/screens/screens_manifest.json` (route, chế độ, viewport, thời điểm, che dữ liệu) | ứng dụng | PASS |
| 26 | Hình 16 là ảnh "trước" của giao diện cũ | `tests/product_evidence/ui_audit/before/DEMO_390x844_market.png` (audit before) | Demo | PASS |
| 27 | Universe = snapshot VN30 06/2026, không phải thành phần hiện hành | `IndexMembership` 01–30/06/2026; tệp `vn30_constituents_2026_06.csv` sha256 `a961eeae…` | Live | PASS (giới hạn được nêu) |
| 28 | Task Scheduler cài ở trạng thái tắt; -RunNow exit 0 | `Install-MarketLab-EODTask.ps1 -Show` (05/11/2026) | Windows | PASS |
| 29 | Lịch tự chạy 16:10 | task chưa bật | Windows | NOT VERIFIED |
| 30 | Migration DB nghiên cứu | cần backup + duyệt của chủ dữ liệu | nghiên cứu | NOT DONE |
| 31 | Tạo dự báo mới hằng ngày | không có model artifact | — | NOT IMPLEMENTED |
| 32 | `check_publication.py` FAIL không có nghĩa 102 ca thất bại | gate allowlist khác phạm vi kiểm thử | repo | PASS (giải thích) |
| 33 | Đẩy nhánh / mở pull request | lệnh push bị từ chối quyền trong phiên làm việc | GitHub | BLOCKED |
| 34 | Ảnh SSMS GUI | chưa chụp; báo cáo dùng output sqlcmd | — | NOT DONE (checklist Phụ lục A.1) |
