# Kịch bản demo 5–7 phút

## Chuẩn bị (~2 phút trước giờ trình bày)

```powershell
cd bai-tap-lon-csdl-2026
powershell -ExecutionPolicy Bypass -File scripts\Start-MarketLab.ps1 -Background -NoBrowser
powershell -ExecutionPolicy Bypass -File scripts\Start-MarketLab.ps1 -Mode REAL_PRIVATE -Database MarketLabVN30_Live -Port 8001 -Background -NoBrowser
```

Checklist: ☐ http://127.0.0.1:8000/ và http://127.0.0.1:8001/ mở được ☐ mở sẵn `.env` để copy token (không chiếu file này) ☐ có Internet nếu demo dry run thật ☐ SSMS mở `MarketLabVN30_Live` và `MarketLabVN30_Ops`.

## Trình bày

| Phút | Nội dung | Thao tác | Điểm cần nói |
|---|---|---|---|
| 0:00 | Kiến trúc | Sơ đồ trong báo cáo / runbook | Trình duyệt → ứng dụng web Python → SQL Server; trang dựng ở máy chủ từ view/function/procedure; không API Gateway, không Swagger (mở `/api/docs` → 404) |
| 0:45 | Tổng quan DEMO | `http://127.0.0.1:8000/` | Nhãn vàng SYNTHETIC; 280 giá, 256 dự báo đủ điều kiện (khớp `10_preflight_live.sql`); khối "Nguồn, đơn vị & giới hạn" |
| 1:30 | Giá & biểu đồ | Nhập DEMO03 → Xem; rê chuột lên biểu đồ; bấm tiêu đề Close; lọc Từ ngày 2025-02-01; F5 | Close và Volume hai panel; tooltip ghi dataset/basis/đơn vị; EOD không realtime; bộ lọc nằm trên URL nên F5 giữ nguyên |
| 2:15 | Dự báo & hiệu năng | Trang Dự báo; lọc "Chưa trưởng thành" | Đủ điều kiện vs chưa trưởng thành theo `fn_EligiblePredictions(as_of)`; "—" không phải 0; khung "Chưa cấu hình mô hình tạo dự báo mới"; không phải khuyến nghị |
| 3:00 | So sánh mô hình | Trang So sánh → So sánh | `usp_CompareModels` trên giao (StockId, OriginDate, TargetDate): 128 quan sát chung |
| 3:30 | REAL_PRIVATE | Bấm "Chuyển chế độ: REAL_PRIVATE" | Nhãn đỏ; 30 mã snapshot VN30 06/2026 (giới hạn đã ghi); 780 giá KBS 01/10–05/11/2026; trạng thái "Đã cập nhật" |
| 4:00 | Vận hành EOD | Trang Vận hành: 5 thẻ ngày; bảng nhật ký; bấm run #37 rồi #39 | Phân biệt ngày yêu cầu / phiên thành công / ObservedThrough / nến nguồn; #37 PARTIAL do nguồn (đã sửa), #39 DRY_RUN_OK |
| 4:45 | Dry run trực tiếp | Ngày 2026-11-05, dán token, Dry run → xác nhận → trang job tự làm mới | Form có CSRF + token; kiểm trong SQL Server rồi ROLLBACK: "thêm 0, không đổi 30" |
| 5:30 | Bảo vệ | Token sai → INVALID_OPS_TOKEN; Sync không tích xác nhận → CONFIRMATION_REQUIRED | Không token trong HTML/URL; 5 lần sai bị khóa; dữ liệu thiếu không bao giờ báo SUCCESS |
| 6:00 | Đối chiếu SQL | SSMS: `SELECT COUNT(*) FROM dbo.DailyPrice` (780); `SELECT TOP 5 * FROM MarketLabVN30_Ops.ops.EodRun ORDER BY EodRunId DESC` | Số trên trang = SQL; nhật ký ghi bằng transaction riêng |
| 6:30 | Kết | — | Hạn chế: không inference, universe snapshot, KBS điều chỉnh hồi tố → đối soát có người duyệt; lịch 16:10 chưa bật |

## Dự phòng

* Không có Internet: bỏ bước 4:45, trình bày run #27/#28 (SUCCESS 30 → SUCCESS 0/30) và #39 trong nhật ký.
* SQL Server dừng: `/health` vẫn `ok`, các trang trả 503 `DB_UNAVAILABLE` có nút "Thử lại".
* Dừng: `scripts\Stop-MarketLab.ps1 -Port 8000` và `-Port 8001`.
