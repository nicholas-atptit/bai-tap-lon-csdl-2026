# Nghiệm thu Web FINAL + backfill OHLCV thật 2023 → nay

Ngày kiểm chứng: 06/11/2026 (giờ Việt Nam). Máy: Windows 11 Pro, SQL Server 2025 Developer (17.0), ODBC Driver 18, Microsoft Edge (Playwright 1.52), Python 3.12 (`uv.lock`), nhánh `feature/marketlab-working-product`.
Trạng thái: **PASS** = đã chạy và có bằng chứng; **NOT VERIFIED** = chưa thể kiểm chứng tại thời điểm này; **NOT IMPLEMENTED** = không làm (có lý do).

## 1. Kiến trúc (không đổi)

```text
Trình duyệt ──HTML (SSR, Jinja2)──► Ứng dụng web Python (FastAPI chỉ làm ASGI, 127.0.0.1) ──pyodbc──► SQL Server
                                                                                                   ├─ MarketLabVN30_Demo (SYNTHETIC)
EOD worker / Backfill (PowerShell, CLI, form web có token + CSRF) ──► SQL Server ─────────────────┤─ MarketLabVN30_Live (REAL_PRIVATE)
                                       └─ KBS qua vnstock (subprocess cô lập)                        └─ MarketLabVN30_Ops (audit, staging, checkpoint)
```

Không có API Gateway, REST JSON hay Swagger: `/api/docs`, `/api/openapi.json`, `/docs`, `/openapi.json`, `/redoc` đều trả 404. Trình duyệt không gửi request dữ liệu nào (CSP `connect-src 'none'`). Có một liên kết tải CSV, render phía máy chủ.

## 2. URL và lệnh

| Mục đích | Lệnh / URL |
|---|---|
| Web DEMO | `powershell -ExecutionPolicy Bypass -File scripts\Start-MarketLab.ps1` → http://127.0.0.1:8000/ |
| Web LIVE | `powershell -ExecutionPolicy Bypass -File scripts\Start-MarketLab.ps1 -Mode REAL_PRIVATE -Database MarketLabVN30_Live -Port 8001` → http://127.0.0.1:8001/ |
| Chạy nền / dừng | thêm `-Background -NoBrowser` · `scripts\Stop-MarketLab.ps1 -Port 8000` (hoặc 8001) |
| Backfill | `scripts\Backfill-MarketLab.ps1 -StartDate 2023-01-01 -EndDate latest -DryRun` → bỏ `-DryRun` để ghi → `-Resume` · `-Status` · `-Report` |
| EOD hằng ngày | `scripts\Run-MarketLab-EOD.ps1 -IfNeeded` (sau 16:10 giờ VN) · `-Date YYYY-MM-DD -DryRun` |
| Sau khi khởi động lại máy | Mỗi thành phần chạy độc lập bằng lệnh tương ứng ở trên; không cần dịch vụ nào khác ngoài SQL Server (MSSQLSERVER tự khởi động) |

Các URL đã kiểm chứng trên instance đang chạy: `/`, `/market`, `/market/export.csv`, `/forecast`, `/compare`, `/ops`, `/backfill`, `/backfill/jobs/<id>`, `/ops/jobs/<id>`, `/health`.

## 3. Dữ liệu LIVE sau backfill

| Mục | Giá trị (SQL Server, 06/11/2026) | Trạng thái |
|---|---|---|
| Universe | 30 mã thuộc universe được cấu hình (tham chiếu VN30 06/2026), không phải thành phần VN30 lịch sử | — |
| Khoảng dữ liệu | MIN(TradeDate) **2023-01-03** (02/01/2023 là ngày nghỉ), MAX **2026-11-05** (phiên hoàn chỉnh mới nhất lúc chạy: 06/11 chưa qua 16:10) | PASS |
| Tổng OHLCV | **28.097** dòng = 780 có sẵn + **27.317** thêm mới; 956 phiên (`dbo.TradingDay` = 956) | PASS |
| Theo năm | 2023: 249 phiên / 7.221 dòng · 2024: 250 / 7.250 · 2025: 249 / 7.386 · 2026: 208 / 6.240 | PASS |
| Thiếu | **0** mã-phiên MISSING. VPL: 583 phiên trước 2025-05-13 là NO_HISTORY (nguồn trả "Dữ liệu trống"), nên độ phủ được ghi trung thực là `PARTIAL_COVERAGE`, không phải FULL | PASS (có giới hạn nguồn) |
| Từ chối / xung đột | 0 dòng nguồn bị từ chối, 0 xung đột, hàng đợi đối soát trống | PASS |
| Dòng < 2023-01-01 | 0 (`DailyPrice` và `TradingDay`) | PASS |
| 780 dòng có sẵn | SHA-256 giá trị và `LoadedAt` trước/sau backfill **giống hệt** | PASS |
| Chạy lại cửa sổ 2023-01-01 → 2023-06-30 | 0 thêm, 3.509 không đổi, 0 xung đột; SHA-256 giá trị và `LoadedAt` giống hệt trước/sau | PASS |
| Toàn vẹn | 0 khóa trùng, 0 vi phạm OHLC, 0 dòng ngoài lịch, 0 TradingDay cuối tuần, 0 dòng thiếu lineage, vẫn **13 bảng**, `ObservedThrough` 2026-11-05 không đổi | PASS |
| Backup trước khi ghi | `MarketLabVN30_Live_preBackfill_20261106T110006.bak` + `MarketLabVN30_Ops_preBackfill_…bak`: CHECKSUM, VERIFYONLY, restore thử khớp số dòng, DB tạm đã xoá | PASS |
| Nguồn | KBS qua vnstock 3.5.1, gọi lúc 2026-11-06 04:02 UTC; 4 lần gọi bridge (mã × năm), 0 retry | PASS |
| EOD sau backfill | `Run-MarketLab-EOD -Date 2026-11-05` → SUCCESS, 0 thêm, 30 không đổi; `-Date 2026-11-06` lúc 11:0x → SKIPPED BEFORE_CUTOFF | PASS |
| EOD phiên 06/11/2026 | Chỉ chạy được sau 16:10 | NOT VERIFIED |

Chi tiết theo mã: [BACKFILL_COVERAGE_REPORT.md](BACKFILL_COVERAGE_REPORT.md). Vận hành và quan sát về nguồn: [BACKFILL_RUNBOOK.md](BACKFILL_RUNBOOK.md).

## 4. Chức năng giao diện

| Khu vực | Nội dung | Bằng chứng |
|---|---|---|
| A. Dashboard `/` | Nhãn LIVE/DEMO lớn ở header và tiêu đề; số mã có giá; phiên có dữ liệu; phạm vi ngày thực tế; số OHLCV; giá mới nhất và độ mới; tình trạng dữ liệu (thiếu = kỳ vọng − đã lưu); phiên EOD thành công gần nhất; job backfill chính; số dự báo đủ điều kiện; số giá chờ đối soát. Không có ROI hay accuracy suy từ giá | ảnh 01, 02, 15 |
| B. Lịch sử OHLCV `/market` | Ô mã có gợi ý 30 mã; lọc ngày (LIVE: `min=2023-01-01`, Từ ngày < 2023 → 422 và không truy vấn); mặc định 12 tháng; khoảng nhanh 3T/6T/1N/2N/Tất cả; biểu đồ Close + Volume (hai trục riêng, không dual-axis) có chú giải đơn vị, tooltip, kéo để phóng to, phím ←/→; phiên thiếu giá có vạch gạch, không nội suy; bảng OHLCV sắp xếp + phân trang 50 dòng; xuất CSV ≤ 5.000 dòng cùng bộ lọc và sàn; dòng nguồn (KBS, vnstock, job, thời điểm tải, PriceBasis, đơn vị). Truy vấn tham số hóa, `WHERE DatasetId, Ticker, TradeDate BETWEEN`, dùng PK `(DatasetId, StockId, TradeDate)` | ảnh 03–06, 13 |
| C. Dự báo `/forecast` | Đọc ModelRun/Prediction của đúng dataset; LIVE chưa có ModelRun → trạng thái rỗng "Chưa cấu hình mô hình tạo dự báo mới" | ảnh 09, 12 |
| D. So sánh `/compare` | `usp_CompareModels` trên tập quan sát giao; không có run hoặc không có quan sát chung → giải thích, không có điểm số | ảnh 10, 11 |
| E. Vận hành `/ops` + `/backfill` | EOD: nhật ký chỉ gồm lần chạy hằng ngày (phiên backfill xem riêng hoặc tích "Gồm cả phiên backfill"), lịch phiên, đối soát, form Dry run/Sync. Backfill: job, tiến độ, checkpoint mã × năm (nhận, staging, từ chối, nến đầu → cuối), phiên cần chú ý, dòng bị từ chối, độ phủ theo mã; form Dry run / Backfill thật / Tiếp tục có token, CSRF, ô xác nhận, hộp thoại xác nhận, chống bấm hai lần, giới hạn một job | ảnh 07, 08, 14 |
| Trạng thái lỗi | Không có dữ liệu, thiếu một phần, lỗi provider (`PROVIDER_NOT_CONFIGURED` báo ngay, không retry), SQL không kết nối (503 kèm cách khắc phục), sai token (401, khóa sau 5 lần), sai CSRF (403), thiếu xác nhận (422), job đang chạy (409); không có trang trắng hay stack trace | test web/E2E |
| Bảo mật | Chỉ bind 127.0.0.1; kiểm tra Host/Origin/Sec-Fetch-Site; CSP không cho inline script/style; token không bao giờ xuất hiện trong HTML, URL hay log; ô mã kiểm tra theo universe trước khi tạo job | test web |

Ảnh: `report/final/assets/web_final/` (16 ảnh, `manifest.json` ghi route, chế độ, viewport, thời điểm chụp và cách che). Ảnh LIVE làm mờ mọi ô giá/khối lượng, biểu đồ và tooltip; số đếm, ngày và trạng thái vẫn đọc được. Ảnh DEMO là dữ liệu mô phỏng nên không cần che.

## 5. Tốc độ (đo trên instance LIVE đang chạy, 15 request/kịch bản)

| Kịch bản | Trung vị | p90 | HTML |
|---|---|---|---|
| Dashboard `/` | 43 ms | 47 ms | 16 KB |
| Lịch sử OHLCV mặc định (12 tháng, ~249 điểm) | 22 ms | 27 ms | 63 KB |
| Đổi mã, toàn bộ 2023+ (~956 điểm) | 26 ms | 30 ms | 174 KB |
| Đổi khoảng ngày (2 năm) | 27 ms | 33 ms | 102 KB |
| Trang 10, sắp xếp theo Close | 27 ms | 38 ms | 174 KB |
| Xuất CSV một mã 2023+ | 27 ms | 28 ms | 77 KB |
| Backfill `/backfill` | 44 ms | 50 ms | 27 KB |
| EOD `/ops` | 20 ms | 41 ms | 19 KB |

Nguồn: `tests/product_evidence/web_perf_real.json` (`scripts/measure_web_perf.py`). Trước khi tối ưu, `coverage_summary` (LEFT JOIN từng mã-phiên) mất 152 ms; sau khi viết lại theo kiểu đếm còn 14 ms. Trình duyệt chỉ nhận tối đa 5.000 điểm cho một mã (một mã 2023+ có khoảng 956 điểm); bảng luôn phân trang.

## 6. Kiểm thử

| Bộ | Kết quả | Bằng chứng |
|---|---|---|
| `uv run pytest tests/product` | **140/140 passed**: unit 49 (normalize/lịch 30, bridge 8, backfill 11), tích hợp EOD 23, SQL regression 5, **tích hợp backfill 17**, web 31 + **web backfill 7**, E2E Edge 8 | `tests/product_evidence/logs/pytest_final_web.log`, `.xml` |
| Unit test gốc `python -m unittest discover -s tests` | 11/11 OK | console |
| Regression SQL gốc `scripts/run_public_regression.py --server .` | PASS: 44 ca SQL + 16 truy vấn + 2 live demo, hash 13 bảng trước = sau | `tests/product_evidence/logs/original_public_regression_final_web.log` |
| Đối chiếu UI ↔ SQL | DEMO **26/26**; LIVE **38/38** (6 mã/khoảng ngày chọn ngẫu nhiên với seed 20261106, sàn 2023 trên trang và CSV, CSV = SQL, độ phủ 30 mã) | `tests/product_evidence/web_vs_sql_demo.json`, `web_vs_sql_real_summary.json` |
| Audit UI: 2 chế độ × 4 khung (1440, 1280, 768, 390) × 6 trang | 48/48 không lỗi: 0 lỗi console, 0 request lỗi, 0 request dữ liệu từ trình duyệt, không tràn ngang | `tests/product_evidence/ui_audit/final_web/` (DEMO; ảnh LIVE ở thư mục private) |

Các ca kiểm thử mới, đối chiếu với danh sách yêu cầu:
1. **TradeDate < 2023**: không cấu hình được sàn sớm hơn; CLI/web từ chối; staging bỏ nến 2022 (`RowsOutOfWindow`); trang `/market`, CSV và form backfill trả 422; E2E kiểm tra thuộc tính `min` và thông báo.
2. **Độ phủ theo mã/phiên**: `coverage()` phân biệt MISSING, NO_HISTORY và đủ; không báo FULL_COVERAGE khi còn thiếu.
3. **Chạy lại không nhân bản; điều chỉnh hồi tố**: rerun → 0 thêm, hash không đổi; giá bị đổi → CONFLICT vào hàng đợi, giá lưu giữ nguyên, không tạo trùng mục đối soát.
4. **Retry, nguồn sập, OHLCV hỏng, thiếu mã, phiên partial, rollback**: retry hữu hạn với backoff 5 → 15 giây; resume chỉ tải lại mã lỗi; nguồn sập → FAILED, không ghi; OHLC hỏng → REJECTED_ROW; lỗi SQL ở một phiên chỉ rollback phiên đó, resume sửa lại; ngắt giữa chừng → resume không tải lại, không trùng; phiên đuôi all-or-nothing, `ObservedThrough` không nhảy qua lỗ hổng; khóa đồng thời; bắt buộc backup.
5. **Đối chiếu UI → SQL với lựa chọn ngẫu nhiên** trên DB LIVE; bằng chứng commit chỉ gồm hash và PASS/FAIL.
6. **Không có `/api/docs`, REST hay Swagger** (cả DEMO và LIVE, gồm `/api/backfill`).
7. **13 bảng và regression SQL gốc nguyên trạng**; DEMO không bị ghi (trang `/backfill` ở DEMO tắt form, POST trả 409).
8. **So sánh mô hình khi thiếu dữ liệu**: `NO_COMMON_MATURED_OBSERVATIONS` và trạng thái rỗng ở LIVE.
9. **Desktop và mobile không lỗi; form quản trị có CSRF**.
10. **Khởi động độc lập từ PowerShell**: Start/Stop web, `Run-MarketLab-EOD.ps1` và `Backfill-MarketLab.ps1` đều đã chạy trong phiên này.

## 7. Giới hạn và phần chưa triển khai

| Mục | Trạng thái |
|---|---|
| Lịch Task Scheduler 16:10 (`\MarketLab\MarketLab VN30 EOD`) | Đã cài nhưng đang **Disabled**, không tự bật → NOT VERIFIED |
| EOD phiên 06/11/2026 | Chưa tới giờ chốt 16:10 lúc kiểm chứng → NOT VERIFIED |
| Tạo dự báo mới / inference | Không có model artifact → NOT IMPLEMENTED (giao diện ghi rõ) |
| Thành phần VN30 tại từng thời điểm | Không có dữ liệu membership lịch sử; dùng universe 30 mã snapshot 06/2026 và ghi nhãn rõ |
| Lịch sử VPL trước 2025-05-13 | Nguồn không có dữ liệu ("Dữ liệu trống") → NO_HISTORY, không nội suy |
| Hệ số đơn vị giá (nghìn VND) | Chưa xác minh với nguồn chính thức; giữ nguyên đơn vị nguồn, không nhân 1.000 |
| Cổng `scripts/check_publication.py` | FAIL: allowlist băm của tác giả chưa có các tệp sản phẩm mới, và cổng quét cả `var/` (gitignored). Không sửa allowlist vì việc đó tương đương phê duyệt công bố |
| Push / pull request | Thực hiện theo quyền của tài khoản. Trạng thái thực tế được báo trong thông điệp bàn giao |
