# Runbook – Backfill OHLCV lịch sử (REAL_PRIVATE)

Tài liệu vận hành cho việc nạp OHLCV thật từ **2023-01-01** đến phiên giao dịch hoàn chỉnh mới nhất vào `MarketLabVN30_Live`, cho **30 mã thuộc universe được cấu hình (tham chiếu VN30 06/2026)**. Đây không phải danh sách thành phần VN30 tại từng thời điểm, vì repository chưa có membership point-in-time.

Kết quả lần chạy thật và số liệu kiểm chứng nằm ở [BACKFILL_COVERAGE_REPORT.md](BACKFILL_COVERAGE_REPORT.md). Nghiệm thu web xem [FINAL_WEB_ACCEPTANCE.md](FINAL_WEB_ACCEPTANCE.md).

## 1. Thiết kế: mở rộng pipeline EOD, không tạo đường nạp thứ hai

```text
KBS (vnstock 3.5.1, subprocess kbs_bridge.py)        ← cùng adapter với EOD hằng ngày
  └─► validate_candle (cùng quy tắc EOD)             ← giá > 0, hữu hạn, ≤ 6 chữ số thập phân, Low ≤ Open/Close ≤ High, Volume ≥ 0
       └─► ops.BackfillStaging  (DB Ops)             ← staging; checkpoint mã × năm ở ops.BackfillFetch; dòng lỗi ở ops.BackfillReject
            └─► ops.usp_EodApplySession              ← cùng procedure với EOD; MỘT transaction cho MỖI phiên
                 └─► dbo.DailyPrice / dbo.TradingDay (13 bảng giữ nguyên)
                 └─► ops.EodRun (TriggerKind BACKFILL) + EodRunItem + PriceLoadLineage + PriceReconciliation + ops.BackfillSession
```

| Quy tắc | Cách thực hiện |
|---|---|
| Sàn lịch sử 2023-01-01 | `MARKETLAB_HISTORY_START` chỉ được dời **muộn hơn** 2023-01-01. CLI và form web từ chối ngày bắt đầu sớm hơn. Staging bỏ mọi nến nguồn trước sàn (`RowsOutOfWindow`). Trang web, bảng, biểu đồ và CSV ở chế độ LIVE luôn lọc `TradeDate ≥ 2023-01-01` |
| `EndDate latest` | Ứng viên là hôm nay nếu đã qua 16:10 (Asia/Ho_Chi_Minh), ngược lại là phiên trước; bỏ qua thứ Bảy/Chủ Nhật. Sau đó lấy **nến VN30 cuối cùng ≤ ứng viên** theo nguồn. Nến tạm thời của phiên đang diễn ra bị loại |
| Lịch phiên | Một ngày là phiên khi có nến chỉ số tham chiếu VN30 **hoặc** ≥ 50% mã của job có nến. Bằng chứng của từng ngày ghi trong `ops.BackfillSession.Message` (`[calendar REFERENCE+TICKERS / REFERENCE_ONLY / TICKERS_ONLY]`). Thứ Bảy/Chủ Nhật và ngày lễ không bao giờ bị tính là thiếu |
| Trùng khóa | Cùng (DatasetId, StockId, TradeDate) và cùng giá trị → `UNCHANGED`. Khác giá trị → **CONFLICT**: vào `ops.PriceReconciliation` (`SESSION_CONFLICT`, `PENDING_REVIEW`); dòng đã lưu **không bị ghi đè**; các mã khác của phiên vẫn được ghi |
| Phiên lịch sử (≤ `ObservedThrough`) | Ghi các mã có nến hợp lệ. Mã thiếu được phân loại: `MISSING` (nguồn có lỗ hổng hoặc tải lỗi), `NO_HISTORY` (nguồn không có nến nào đến ngày đó, ví dụ niêm yết sau; chỉ khi các chunk trước đã tải thành công), `REJECTED_ROW`. Phiên như vậy là **PARTIAL**, không bao giờ được tính là "30/30 SUCCESS" |
| Phiên sau `ObservedThrough` | Áp dụng quy tắc all-or-nothing như EOD hằng ngày: đủ universe mới ghi. Nếu một phiên đuôi không ghi được, mọi phiên sau đó cũng không ghi (`TAIL_BLOCKED_BY_EARLIER_GAP`), nên `ObservedThrough` không bao giờ nhảy qua lỗ hổng |
| Atomic theo batch | Mỗi phiên là một transaction (`sp_getapplock` + `SET XACT_ABORT`). Lỗi SQL chỉ rollback phiên đó, các phiên trước giữ nguyên. Sau 3 phiên lỗi liên tiếp thì dừng |
| Retry / backoff | Bridge: tối thiểu 1 giây giữa hai lần gọi, tối đa 3 lần thử mỗi mã (backoff 1, 2, 4 giây), timeout cứng 180 giây mỗi lần gọi. Job: tối đa 3 lượt tải lại các (mã, năm) lỗi, chờ 5 rồi 15 giây. Lỗi cấu hình (chưa cài provider) dừng ngay, không retry |
| Resume | `--resume` dùng lại dữ liệu đã staging (không tải lại toàn bộ), chỉ tải lại các chunk `FAILED`. Phiên đã `COMPLETE` hoặc `PARTIAL` chỉ do `NO_HISTORY` được bỏ qua; phiên lỗi, thiếu hoặc chưa ghi được xử lý lại. Các `EodRun` bị bỏ dở ở trạng thái `RUNNING` được đóng là `ABANDONED` |
| Đồng thời | Khóa `sp_getapplock` mức session trong DB Ops (`MarketLab.Backfill.<db>.<dataset>`), được giải phóng tường minh vì pyodbc dùng pooling. Chỉ một job chạy tại một thời điểm, dù chạy từ CLI hay web |
| Backup | Job ghi thật yêu cầu backup đã xác minh của DB nghiệp vụ và DB Ops, xem mục 3 |

Migration duy nhất của lần mở rộng này nằm ở **DB Ops**: `sql/16_ops_schema_v3_backfill.sql` (có rollback). Business DB `MarketLabVN30_Live` không đổi schema: 13 bảng, procedure và trigger giữ nguyên. DB nghiên cứu gốc không bị đụng tới.

## 2. Lệnh PowerShell

```powershell
cd "K:\btl he quan tri csdl\bai-tap-lon-csdl-2026"
# 1) dry run: tải nguồn -> staging -> kiểm tra trong SQL Server rồi ROLLBACK; in số lượng dự kiến
powershell -ExecutionPolicy Bypass -File .\scripts\Backfill-MarketLab.ps1 -StartDate 2023-01-01 -EndDate latest -DryRun
# 2) ghi thật: tự backup + xác minh (BACKUP WITH CHECKSUM, RESTORE VERIFYONLY, restore thử) rồi ghi từng phiên
powershell -ExecutionPolicy Bypass -File .\scripts\Backfill-MarketLab.ps1 -StartDate 2023-01-01 -EndDate latest
# 3) tiếp tục sau gián đoạn (Ctrl+C, mất mạng, tắt máy)
powershell -ExecutionPolicy Bypass -File .\scripts\Backfill-MarketLab.ps1 -Resume
# trạng thái / báo cáo coverage (ghi docs\BACKFILL_COVERAGE_REPORT.md, JSON ở var\reports)
powershell -ExecutionPolicy Bypass -File .\scripts\Backfill-MarketLab.ps1 -Status
powershell -ExecutionPolicy Bypass -File .\scripts\Backfill-MarketLab.ps1 -Report
# chỉ backup + xác minh
powershell -ExecutionPolicy Bypass -File .\scripts\Backfill-MarketLab.ps1 -BackupOnly
# một tập con mã (luôn là PARTIAL, không bao giờ SUCCESS 30/30)
powershell -ExecutionPolicy Bypass -File .\scripts\Backfill-MarketLab.ps1 -StartDate 2025-01-01 -EndDate 2025-12-31 -Tickers FPT,VNM -DryRun
```

Mã thoát: `0` COMPLETED / DRY_RUN_OK · `10` khóa đang bận · `20` COMPLETED_WITH_GAPS · `30` FAILED / INTERRUPTED / lỗi nguồn hoặc DB · `2` đầu vào bị từ chối. Nhật ký ở `var\logs\backfill_task_<ngày>.log`, không chứa token.

CLI tương đương: `python -m marketlab_app.cli backfill run|backup|status|report|hash` (xem `marketlab_app/backfill_cli.py`).

Từ web: tab **Backfill lịch sử** (`/backfill`), cần token vận hành và CSRF, phải tích xác nhận trước khi ghi thật; trình duyệt hỏi lại lần nữa và job chạy nền trong tiến trình server.

## 3. Backup, xác minh và khôi phục

`marketlab_app/eod/backup.py` chạy cho cả `MarketLabVN30_Live` và `MarketLabVN30_Ops`:

1. Kiểm tra dung lượng trống của ổ backup: cần ≥ 2 × dung lượng đã dùng của DB + 256 MB.
2. `BACKUP DATABASE … WITH COPY_ONLY, CHECKSUM, INIT, FORMAT` vào thư mục backup mặc định của SQL Server (không làm gãy log chain).
3. `RESTORE VERIFYONLY … WITH CHECKSUM` và `RESTORE HEADERONLY` (khớp tên DB, có checksum).
4. Restore thử vào `MarketLabVN30_RestoreCheck_<loại>_<thời điểm>`, so số dòng các bảng chính với DB gốc, rồi DROP DB tạm.
5. Ghi manifest `var\backups\backup_manifest_<thời điểm>.json` (gitignored); job lưu tên tệp và thời điểm xác minh.

Khôi phục là quyết định của người vận hành, không tự động. Ví dụ với SSMS hoặc sqlcmd:

```sql
-- dừng web và worker trước (scripts\Stop-MarketLab.ps1 -Port 8001)
ALTER DATABASE [MarketLabVN30_Live] SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
RESTORE DATABASE [MarketLabVN30_Live]
  FROM DISK = N'C:\Program Files\Microsoft SQL Server\MSSQL17.MSSQLSERVER\MSSQL\Backup\MarketLabVN30_Live_preBackfill_<thời điểm>.bak'
  WITH REPLACE, CHECKSUM;
ALTER DATABASE [MarketLabVN30_Live] SET MULTI_USER;
-- làm tương tự với MarketLabVN30_Ops bằng backup cùng thời điểm để audit khớp dữ liệu
```

Các tệp `.bak` không bao giờ được commit (`*.bak` có trong `.gitignore`).

## 4. Quan sát thực tế về nguồn KBS (06/11/2026)

| Quan sát | Xử lý |
|---|---|
| Lịch sử trả về từ 03/01/2023 (02/01/2023 là ngày nghỉ) | Phiên đầu tiên thực tế là 2023-01-03; không có dòng nào trước sàn |
| VPL: nguồn trả `ValueError "Dữ liệu trống cho mã VPL với interval 1D"` cho 2023 và 2024; nến đầu tiên là 2025-05-13 | Bridge nhận diện câu trả lời "dữ liệu trống" tường minh của nguồn, khác với lỗi mạng (`empty_reason`). Các phiên trước 13/05/2025 được xếp `NO_HISTORY`, không phải `MISSING`; thông điệp nguyên văn của nguồn được lưu trong `ops.BackfillFetch.Message`. Lần dry run đầu (trước khi sửa) xếp nhầm 583 mã-phiên là `MISSING`; lỗi này được phát hiện và sửa trước khi ghi thật |
| Chuỗi chỉ số VN30 năm 2025 có 249 nến ở một lần gọi nhưng chỉ 248 nến ở lần gọi sau vài phút (thiếu 2025-04-04), trong khi cả 30 mã đều có nến ngày đó và giá trị giống hệt nhau | Lịch phiên lấy hợp của nến tham chiếu và nến của ≥ 50% mã (mục 1). Nếu chỉ dựa vào chuỗi tham chiếu, phiên này sẽ bị bỏ sót âm thầm |
| `end` của KBS có thể không bao gồm ngày cuối; nến của phiên đang giao dịch xuất hiện trong giờ giao dịch | Gọi tới D+1 (không vượt hôm nay) rồi loại nến sau D. Thấy 1 nến 2026-11-06 bị loại (`RowsOutOfWindow`) |
| Giá đã điều chỉnh hồi tố (trước một số sự kiện doanh nghiệp, giá có nhiều chữ số thập phân hơn bước giá niêm yết) | `PriceBasis SOURCE_CLOSE`: giá như KBS trả về tại thời điểm tải, không phải total return. 780 dòng 10–11/2026 tải từ trước khớp tuyệt đối với lần tải mới (0 xung đột), nên toàn chuỗi cùng một hệ quy chiếu tại thời điểm tải. Biến động Close liên tiếp lớn nhất là 7,06% (biên độ HOSE ±7%), không có bước nhảy > 7,5%, nên không thấy điểm gãy do giá chưa điều chỉnh. Nếu sau này KBS điều chỉnh lại, các phiên bị đổi sẽ vào hàng đợi đối soát, không ghi đè |
| Quyền sử dụng | Theo LICENSE.md và EOD_DATA_CONTRACT.md: dữ liệu VNstock/KBS có quyền phân phối **UNKNOWN**, chỉ lưu cục bộ, không đưa bản ghi giá lên GitHub. Báo cáo chỉ chứa số đếm, ngày và hash |

## 5. Xử lý sự cố

| Triệu chứng | Nguyên nhân / cách khắc phục |
|---|---|
| `PROVIDER_NOT_CONFIGURED` | Đặt `MARKETLAB_PROVIDER_PYTHON` trong `.env` là `python.exe` đã cài vnstock |
| `PROVIDER_TIMEOUT`, `PROVIDER_ERROR`, chunk `FAILED` | Mạng hoặc nguồn tạm lỗi. Chạy `-Resume`: chỉ tải lại các chunk lỗi |
| `LOCK_BUSY` (mã 10) | Một job backfill khác đang chạy (CLI hoặc web). Chờ job đó xong |
| `BACKUP_REQUIRED` hoặc `BACKUP ERROR` | Thiếu dung lượng hoặc quyền ghi thư mục backup của SQL Server. Kiểm tra ổ đĩa rồi chạy `-BackupOnly` |
| `COMPLETED_WITH_GAPS` (mã 20) | Còn `NO_HISTORY`, `MISSING` hoặc xung đột. Xem tab Backfill hoặc `-Status`. `MISSING` có thể chạy lại sau; `NO_HISTORY` là giới hạn của nguồn |
| `CONFLICT` / `PENDING_REVIEW` | Nguồn đổi giá đã lưu. Duyệt bằng `python -m marketlab_app.cli eod reconcile list` rồi `approve` hoặc `reject` (có xác nhận ghi đè) |
| `OPS_SCHEMA_V3_MISSING` | Chạy `python -m marketlab_app.deploy ops-db` (áp dụng 14 → 15 → 16, idempotent) |
