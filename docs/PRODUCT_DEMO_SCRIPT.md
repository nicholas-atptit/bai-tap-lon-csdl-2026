# Kịch bản demo 5–7 phút

## Chuẩn bị (trước giờ trình bày, ~2 phút)

```powershell
cd bai-tap-lon-csdl-2026
powershell -ExecutionPolicy Bypass -File scripts\Start-MarketLab.ps1 -Background -NoBrowser                     # DEMO :8000
powershell -ExecutionPolicy Bypass -File scripts\Start-MarketLab.ps1 -Mode REAL_PRIVATE -Database MarketLabVN30_Live -Port 8001 -Background -NoBrowser
```

Checklist: ☐ hai URL trả `/api/ready` = ready ☐ mở sẵn `.env` để copy token (không chiếu màn hình file này) ☐ máy có Internet nếu demo đồng bộ thật ☐ SSMS mở `MarketLabVN30_Live` để đối chiếu.

## Trình bày

| Phút | Nội dung | Thao tác | Điểm cần nói |
|---|---|---|---|
| 0:00 | Kiến trúc | `http://127.0.0.1:8000/api/docs` | Một gateway FastAPI cục bộ, SQL Server là lõi; API gọi view/function/procedure sẵn có; chỉ bind 127.0.0.1 |
| 0:45 | Tổng quan DEMO | `http://127.0.0.1:8000/` | Nhãn vàng SYNTHETIC; 280 giá, 256 dự báo đủ điều kiện (bằng `10_preflight_live.sql`); EOD "không áp dụng" |
| 1:30 | Market Explorer | Nhập DEMO03 → Xem; rê chuột trên chart; bấm tiêu đề Close | Hai panel, một trục mỗi panel; tooltip ghi đơn vị/basis; EOD không realtime; bảng có phân trang/sắp xếp |
| 2:15 | Phân tích dự báo | Tab Phân tích dự báo; lọc "Chưa trưởng thành" | Eligible vs pending theo `fn_EligiblePredictions(as_of)`; ngưỡng theo ModelRun; khung "Chưa cấu hình mô hình tạo dự báo mới"; không phải khuyến nghị |
| 3:00 | So sánh mô hình | Tab So sánh → So sánh | `usp_CompareModels` trên giao (StockId, OriginDate, TargetDate): 128 quan sát chung |
| 3:30 | REAL_PRIVATE | `http://127.0.0.1:8001/` | Nhãn đỏ; 30 mã VN30 snapshot 06/2026 (giới hạn đã ghi); 780 giá KBS 01/10–05/11/2026 |
| 4:00 | Vận hành dữ liệu | Tab Vận hành: thẻ ngày yêu cầu / phiên thành công / ObservedThrough / nến provider; bảng run; bấm một run để xem từng mã | Phân biệt rõ 4 mốc ngày; trạng thái SUCCESS/NO_SESSION/SKIPPED/FAILED có nghĩa chính xác |
| 4:45 | Dry run trực tiếp | Ngày = phiên gần nhất, dán token, **Dry run** → xác nhận | Nguồn thật được gọi, kiểm tra trong SQL rồi ROLLBACK: "thêm 0, không đổi 30" — chạy lại không tạo dòng mới |
| 5:30 | Bảo vệ | Token sai → INVALID_OPS_TOKEN; chọn ngày Chủ nhật → NO_SESSION | Không có token trong JS/URL; 5 lần sai bị khóa; dữ liệu thiếu không bao giờ báo SUCCESS |
| 6:00 | Đối chiếu SQL | SSMS: `SELECT COUNT(*) FROM dbo.DailyPrice` và `SELECT TOP 5 * FROM MarketLabVN30_Ops.ops.EodRun ORDER BY EodRunId DESC` | Số trên UI = số trong SQL; nhật ký ghi bằng transaction riêng |
| 6:30 | Kết | — | Hạn chế: không inference, universe snapshot, KBS điều chỉnh hồi tố → reconciliation có người duyệt |

## Phương án dự phòng

* Không có Internet: bỏ bước 4:45, trình bày run đã ghi trong bảng nhật ký (run 27/28: SUCCESS 30 → SUCCESS 0/30 idempotent).
* SQL Server dừng: `/api/health` vẫn `ok`, `/api/ready` → 503 và UI hiển thị `DB_UNAVAILABLE` (đó cũng là một điểm demo về xử lý lỗi).
* Dừng server: `scripts\Stop-MarketLab.ps1 -Port 8000` và `-Port 8001`.
