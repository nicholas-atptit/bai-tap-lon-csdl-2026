# Báo cáo backfill OHLCV lịch sử – MarketLab VN30 (REAL_PRIVATE)

Sinh tự động bởi `python -m marketlab_app.cli backfill report` lúc 2026-11-06T04:05:55+00:00 (UTC). Chỉ chứa số đếm, ngày và hash; **không chứa giá**, token, mật khẩu hay chuỗi kết nối. Dữ liệu giá nằm trong SQL Server cục bộ (`MarketLabVN30_Live`), không đưa lên GitHub (quyền phân phối dữ liệu nguồn: UNKNOWN).

## 1. Phạm vi

| Mục | Giá trị |
|---|---|
| Universe | 30 mã thuộc universe được cấu hình (tham chiếu VN30 2026-06), không phải thành phần VN30 lịch sử |
| Cửa sổ yêu cầu | 2023-01-01 → 2026-11-05 (sàn lịch sử 2023-01-01; EndDate spec `latest`) |
| Lịch phiên | phiên của backfill job de6eb8c9-e37d-4abd-b6b7-8427ba146a27: ngày có nến VN30 hoặc có nến của ≥ 50% mã: **956 phiên**, 2023-01-03 → 2026-11-05 (bằng chứng: REFERENCE+TICKERS: 956) |
| Khoảng dữ liệu thực tế đã lưu | MIN(TradeDate) = 2023-01-03, MAX(TradeDate) = 2026-11-05 |
| Nguồn | KBS qua vnstock 3.5.1 (bridge subprocess), lấy lúc 2026-11-06T04:02:02.721932+00:00 UTC |
| Quy ước giá | PriceBasis `SOURCE_CLOSE`: giá nguồn như KBS trả về tại thời điểm tải (KBS điều chỉnh hồi tố theo sự kiện doanh nghiệp; không phải total return). Đơn vị: Don vi bao gia nguon KBS (quan sat ~nghin VND/co phieu); chua xac minh he so VND |
| ObservedThrough | 2026-11-05 |

## 2. Kết quả nạp

| Chỉ số | Giá trị |
|---|---|
| Job | `de6eb8c9-e37d-4abd-b6b7-8427ba146a27` · trạng thái **COMPLETED_WITH_GAPS** · resume 0 lần |
| Số mã xử lý | 30 |
| Phiên đã xử lý / kế hoạch | 956 / 956 |
| Dòng thêm mới (INSERTED) | 27317 |
| Dòng bỏ qua vì đã có, cùng giá trị (UNCHANGED) | 780 |
| Mã-phiên thiếu (MISSING) | 0 |
| Mã-phiên trước lịch sử nguồn (NO_HISTORY) | 583 |
| Dòng nguồn bị từ chối khi validate | 0 (không có) |
| Xung đột giá (cần đối soát) | 0 · hàng đợi: trống |
| Lần gọi provider / retry | 4 / 0 · chunk tải lỗi còn lại: 0 |
| Backup trước khi ghi | MarketLabVN30_Live_preBackfill_20261106T110006.bak, MarketLabVN30_Ops_preBackfill_20261106T110006.bak (xác minh 2026-11-06T04:00:13.668000 UTC) |
| Thời gian job | 2026-11-06T04:00:06.426000 → 2026-11-06T04:03:34.173000 UTC |

## 3. Kiểm tra toàn vẹn trên SQL Server

| Kiểm tra | Kết quả |
|---|---|
| Tổng dòng OHLCV của dataset | 28097 (trong cửa sổ: 28097) |
| Phiên có giá trong cửa sổ / dbo.TradingDay | 956 / 956 |
| Dòng giá TradeDate < 2023-01-01 | 0 (TradingDay: 0) |
| Khóa trùng (DatasetId, StockId, TradeDate) | 0 |
| Vi phạm OHLC/Volume | 0 |
| Dòng giá ngoài lịch dbo.TradingDay | 0 |
| TradingDay rơi vào thứ Bảy/Chủ Nhật | 0 |
| Dòng trong cửa sổ chưa có lineage (ops.PriceLoadLineage) | 0 |
| SHA-256 giá trị (StockId, TradeDate, OHLCV) | `180A634F1B779C915972309F7AC34C98895B336DA6EFE48FDFD38BB50C7B6F70` (28097 dòng) |
| SHA-256 LoadedAt | `D3C6423B6B8124BE5E8AAF27E508FFB7976D845AC4E32EE67068E8A31964BED2` |
| **Độ phủ** | **PARTIAL_COVERAGE**: 0 mã-phiên thiếu, 583 mã-phiên trước lịch sử nguồn |

### Theo năm

| Năm | Phiên có giá | Dòng OHLCV |
|---|---|---|
| 2023 | 249 | 7221 |
| 2024 | 250 | 7250 |
| 2025 | 249 | 7386 |
| 2026 | 208 | 6240 |

## 4. Độ phủ theo mã

Phiên kỳ vọng của một mã = các phiên của lịch tham chiếu kể từ nến đầu tiên mà nguồn có cho mã đó. Biến động Close liên tiếp > 7.5% (biên độ HOSE ±7%) được đếm để rà soát điểm gãy điều chỉnh giá; đây là cờ kiểm tra, không phải lỗi tự động.

| Mã | Dòng | Phiên đầu – cuối đã lưu | Nến nguồn đầu tiên | Kỳ vọng | Thiếu | Trước lịch sử nguồn | Δ>7,5% | Δ>15% |
|---|---|---|---|---|---|---|---|---|
| ACB | 956 | 2023-01-03 – 2026-11-05 | 2023-01-03 | 956 | 0 | 0 | 0 | 0 |
| BID | 956 | 2023-01-03 – 2026-11-05 | 2023-01-03 | 956 | 0 | 0 | 0 | 0 |
| CTG | 956 | 2023-01-03 – 2026-11-05 | 2023-01-03 | 956 | 0 | 0 | 0 | 0 |
| DGC | 956 | 2023-01-03 – 2026-11-05 | 2023-01-03 | 956 | 0 | 0 | 0 | 0 |
| FPT | 956 | 2023-01-03 – 2026-11-05 | 2023-01-03 | 956 | 0 | 0 | 0 | 0 |
| GAS | 956 | 2023-01-03 – 2026-11-05 | 2023-01-03 | 956 | 0 | 0 | 0 | 0 |
| GVR | 956 | 2023-01-03 – 2026-11-05 | 2023-01-03 | 956 | 0 | 0 | 0 | 0 |
| HDB | 956 | 2023-01-03 – 2026-11-05 | 2023-01-03 | 956 | 0 | 0 | 0 | 0 |
| HPG | 956 | 2023-01-03 – 2026-11-05 | 2023-01-03 | 956 | 0 | 0 | 0 | 0 |
| LPB | 956 | 2023-01-03 – 2026-11-05 | 2023-01-03 | 956 | 0 | 0 | 0 | 0 |
| MBB | 956 | 2023-01-03 – 2026-11-05 | 2023-01-03 | 956 | 0 | 0 | 0 | 0 |
| MSN | 956 | 2023-01-03 – 2026-11-05 | 2023-01-03 | 956 | 0 | 0 | 0 | 0 |
| MWG | 956 | 2023-01-03 – 2026-11-05 | 2023-01-03 | 956 | 0 | 0 | 0 | 0 |
| PLX | 956 | 2023-01-03 – 2026-11-05 | 2023-01-03 | 956 | 0 | 0 | 0 | 0 |
| SAB | 956 | 2023-01-03 – 2026-11-05 | 2023-01-03 | 956 | 0 | 0 | 0 | 0 |
| SHB | 956 | 2023-01-03 – 2026-11-05 | 2023-01-03 | 956 | 0 | 0 | 0 | 0 |
| SSB | 956 | 2023-01-03 – 2026-11-05 | 2023-01-03 | 956 | 0 | 0 | 0 | 0 |
| SSI | 956 | 2023-01-03 – 2026-11-05 | 2023-01-03 | 956 | 0 | 0 | 0 | 0 |
| STB | 956 | 2023-01-03 – 2026-11-05 | 2023-01-03 | 956 | 0 | 0 | 0 | 0 |
| TCB | 956 | 2023-01-03 – 2026-11-05 | 2023-01-03 | 956 | 0 | 0 | 0 | 0 |
| TPB | 956 | 2023-01-03 – 2026-11-05 | 2023-01-03 | 956 | 0 | 0 | 0 | 0 |
| VCB | 956 | 2023-01-03 – 2026-11-05 | 2023-01-03 | 956 | 0 | 0 | 0 | 0 |
| VHM | 956 | 2023-01-03 – 2026-11-05 | 2023-01-03 | 956 | 0 | 0 | 0 | 0 |
| VIB | 956 | 2023-01-03 – 2026-11-05 | 2023-01-03 | 956 | 0 | 0 | 0 | 0 |
| VIC | 956 | 2023-01-03 – 2026-11-05 | 2023-01-03 | 956 | 0 | 0 | 0 | 0 |
| VJC | 956 | 2023-01-03 – 2026-11-05 | 2023-01-03 | 956 | 0 | 0 | 0 | 0 |
| VNM | 956 | 2023-01-03 – 2026-11-05 | 2023-01-03 | 956 | 0 | 0 | 0 | 0 |
| VPB | 956 | 2023-01-03 – 2026-11-05 | 2023-01-03 | 956 | 0 | 0 | 0 | 0 |
| VPL | 373 | 2025-05-13 – 2026-11-05 | 2025-05-13 | 373 | 0 | 583 | 0 | 0 |
| VRE | 956 | 2023-01-03 – 2026-11-05 | 2023-01-03 | 956 | 0 | 0 | 0 | 0 |

## 5. Chạy lại cùng cửa sổ (idempotency)

| Job | Cửa sổ | Trạng thái | Thêm mới | Không đổi | Thiếu | Trước lịch sử nguồn | Xung đột |
|---|---|---|---|---|---|---|---|
| `de6eb8c9-e37d-4abd-b6b7-8427ba146a27` | 2023-01-01 → 2026-11-05 | COMPLETED_WITH_GAPS | 27317 | 780 | 0 | 583 | 0 |
| `c6900fc4-d1db-4244-ba77-ec411a047f34` | 2023-01-01 → 2023-06-30 | COMPLETED_WITH_GAPS | 0 | 3509 | 0 | 121 | 0 |

SHA-256 giá trị của cửa sổ chạy lại: trước `9CADD3C05FA1787FD10E5376E105DEFB793A0ED9DE7114FB29B2EB88ABAFC558`, sau `9CADD3C05FA1787FD10E5376E105DEFB793A0ED9DE7114FB29B2EB88ABAFC558` → **giống hệt**.
