# Hợp đồng dữ liệu EOD (End-of-Day) — MarketLab VN30

## 1. Nguồn

| Thuộc tính | Giá trị |
|---|---|
| Nguồn | KBS qua thư viện **vnstock** (`Quote(source="kbs").history(symbol, start, end, interval="1D")`) |
| Phiên bản đã kiểm chứng | vnstock 3.5.1 (interpreter người dùng, pandas 3.0.2) — dùng cho toàn bộ dữ liệu thật; 4.0.9 (bản hiện hành trên index vendor) cho cùng API và cùng giá trong smoke test cô lập |
| Cách gọi | Subprocess cô lập: `<MARKETLAB_PROVIDER_PYTHON> -I -X utf8 marketlab_app/eod/kbs_bridge.py req.json resp.json` (không shell, không biến môi trường bí mật, timeout cứng, kill khi quá hạn) |
| Ghi nhận phiên bản | `ops.EodRun.ProviderMeta` lưu `package_version`, `pandas_version`, cửa sổ yêu cầu, số lần thử, thời điểm gọi |
| Quyền sử dụng | Theo LICENSE.md: dữ liệu VNstock/KBS chịu điều kiện của bên thứ ba, quyền phân phối **UNKNOWN** ⇒ chỉ lưu cục bộ trong DB REAL_PRIVATE; không đưa bản ghi lên GitHub |
| Lưu ý vendor | vnstock in banner/quảng cáo và có thành phần telemetry (`vnai`); bridge chuyển toàn bộ stdout/stderr của thư viện vào bộ đệm, chỉ trả JSON |

## 2. Ngữ nghĩa giá

* **Đơn vị**: đơn vị báo giá nguồn KBS (quan sát ≈ nghìn VND/cổ phiếu, ví dụ ACB ≈ 20,5). **Không nhân 1.000**, chưa xác minh hệ số VND.
* **Basis**: `SOURCE_CLOSE` = giá như nhà cung cấp trả về **tại thời điểm đồng bộ**. KBS **điều chỉnh hồi tố** (đã quan sát FPT 09/2025 lệch ~9,1% so với bản trích xuất trước, cùng Volume). Chuỗi đã lưu có thể có điểm gãy basis tại sự kiện doanh nghiệp; không phải total return; không phải realtime.
* **Ngày giao dịch**: ngày lịch Asia/Ho_Chi_Minh. Nhãn naive `YYYY-MM-DD 07:00:00` hoặc `00:00:00` → lấy phần ngày; timestamp có offset → đổi sang Asia/Ho_Chi_Minh rồi lấy ngày; timestamp naive giờ khác → từ chối (`BAD_TIME_FORMAT`). Không bao giờ dùng ngày UTC.

## 3. Universe

`ops.EodConfig(IndexCode='VN30', UniverseAsOf=2026-06-30)` → các mã có `IndexMembership` của chỉ số VN30 hiệu lực tại 30/06/2026 trong cùng thị trường dataset, `IsSynthetic=0`. Nguồn: `vn30_constituents_2026_06.csv` (HOSE, kỳ 1/2026, sha256 `a961eeaefdfed2f7a48a0e756e6d7e14a62837a7c4a5c6e8588adcf8623cb998`), lưu trong `EvidenceNote`. **Giới hạn**: đây là snapshot 06/2026 dùng như universe cố định; không khẳng định là thành phần VN30 hiện hành hay lịch sử. Không mặc định mọi Stock cùng MarketId là VN30.

## 4. Quyết định phiên (theo thứ tự)

1. `SessionDate > hôm nay (VN)` → **SKIPPED / FUTURE_DATE**.
2. `SessionDate = hôm nay` và giờ VN < `MARKETLAB_EOD_CUTOFF` (mặc định 16:10) → **SKIPPED / BEFORE_CUTOFF**. 16:10 chỉ là mốc lập lịch, **không** phải bằng chứng dữ liệu đã chốt.
3. Thứ Bảy/Chủ nhật → **NO_SESSION / WEEKEND**.
4. Lấy chuỗi tham chiếu (`CalendarReferenceSymbol`, mặc định chỉ số `VN30`) trong [D−14, min(D+10, hôm nay)]:
   * có nến ngày D → phiên giao dịch;
   * không có nến D nhưng có nến sau D → **NO_SESSION / PROVIDER_CALENDAR_GAP** (lưu nến trước/sau làm bằng chứng);
   * không có nến D và chưa có nến nào sau D → **SKIPPED / DATA_NOT_YET_AVAILABLE** (dữ liệu trễ hoặc chưa rõ; chạy lại sau).
5. Nếu provider nói không có phiên nhưng `dbo.TradingDay` đã có ngày đó → **FAILED / CALENDAR_MISMATCH** (cần người xem).

## 5. Kiểm tra trước khi ghi (toàn bộ universe, cửa sổ [D−10, D])

| Quy tắc | Mã lỗi |
|---|---|
| open/high/low/close hữu hạn, > 0 | `NOT_FINITE`, `NON_POSITIVE_PRICE`, `BAD_NUMBER` |
| high ≥ max(open, close, low); low ≤ min(open, close, high) | `OHLC_RANGE` |
| volume nguyên, 0 ≤ volume ≤ 2⁶³−1 | `BAD_VOLUME` |
| ≤ 6 chữ số thập phân, < 10¹³ (decimal(19,6)) | `PRECISION` |
| Trùng ngày giống hệt → gộp (ghi chú); trùng ngày khác giá trị → từ chối | `SOURCE_DUPLICATE_CONFLICT` |
| Mỗi mã phải có nến ngày D | thiếu → `MISSING` |

Bất kỳ mã nào bị từ chối → **FAILED / VALIDATION_FAILED**. Bất kỳ mã nào thiếu → **PARTIAL / MISSING_TICKERS**. Cả hai trường hợp: **không ghi dòng nào**, không điền dữ liệu thay thế (`RequireCompleteUniverse=1`, ràng buộc CHECK trong v1).

## 6. Ghi (SQL Server, all-or-nothing)

`ops.usp_EodApplySession` (trong DB nghiệp vụ) với payload JSON (giá dạng chuỗi thập phân, không qua float):

1. Từ chối nếu đang có transaction, dataset không phải REAL_PRIVATE, ngày tương lai, universe thiếu/thừa/trùng (51140–51143, 51146).
2. `BEGIN TRANSACTION` + `sp_getapplock('MarketLab.EOD.<db>.<dataset>', Exclusive, Transaction, timeout 0)` → bận: **SKIPPED / LOCK_BUSY** (51144).
3. Nếu khóa (DatasetId, StockId, D) đã có giá **khác** → THROW 51145 → **FAILED / CONFLICT_REQUIRES_RECONCILIATION**; ghi `ops.PriceReconciliation` (PENDING_REVIEW) bằng transaction riêng. Không tự update.
4. Thêm `TradingDay` nếu chưa có (trigger `tr_TradingDay_Guard` bảo vệ horizon đã lưu).
5. Nâng `ObservedThrough` (chỉ khi D lớn hơn) với `SESSION_CONTEXT('MarketLab.EodRunRef')` — trigger đã sửa chỉ chấp nhận đúng trường hợp REAL_PRIVATE, tăng, các cột ngữ nghĩa khác không đổi.
6. Gọi `dbo.usp_InsertDailyPrice @AllowUpdate=0` cho từng mã (giữ nguyên mọi kiểm tra gốc). Lỗi bất kỳ → `XACT_ABORT` rollback toàn bộ.
7. `@DryRun=1`: chạy đủ bước 1–6 (trigger/constraint thật) rồi **ROLLBACK** → **DRY_RUN_OK**.

Chạy lại cùng dữ liệu: **SUCCESS** với `inserted=0, unchanged=N` (idempotent). Sau mỗi SUCCESS: ghi `ops.PriceLoadLineage`, chạy *drift probe* (so các ngày đã lưu trong cửa sổ với giá nguồn hiện tại → `HISTORY_DRIFT_PROBE` chờ duyệt, kèm cảnh báo trong message), và lưu `ops.EvaluationSnapshot` (đánh giá lại dự báo đã trưởng thành với `as_of = D` qua `fn_EligiblePredictions`).

## 7. Trạng thái và mã thoát

| Status | Ý nghĩa | Ghi dữ liệu? | Exit |
|---|---|---|---|
| SUCCESS | đủ universe, hợp lệ, đã commit (có thể 0 dòng mới nếu chạy lại) | có | 0 |
| DRY_RUN_OK | đã kiểm trong SQL và rollback | không | 0 |
| NO_SESSION | cuối tuần / nghỉ theo bằng chứng provider | không | 0 |
| SKIPPED | tương lai / trước cutoff / dữ liệu chưa có / khóa bận | không | 10 |
| PARTIAL | thiếu ≥ 1 mã | không | 20 |
| FAILED | lỗi cấu hình/nguồn/validation/SQL/xung đột | không | 30 |
| (setup) | thiếu ops DB / EodConfig / cấu hình | không có run | 2 |

Bảng `ops.EodRun` có CHECK: SUCCESS bắt buộc `IsDryRun=0`, `Received=Requested`, `Inserted+Unchanged=Requested`, `Rejected=0`; mọi trạng thái khác ngoài SUCCESS/RUNNING phải có `InsertedCount=0`; FAILED/PARTIAL/SKIPPED/NO_SESSION phải có `ErrorCode`. Nhật ký mở run (RUNNING) và kết thúc run là các transaction riêng ở DB ops, độc lập với transaction dữ liệu; run bị bỏ dở có thể đánh dấu `FAILED/ABANDONED`.

## 8. Retry, timeout, rate limit

Mỗi mã: tối đa `MARKETLAB_PROVIDER_MAX_ATTEMPTS` (3) lần, backoff 1 s → 2 s → 4 s (trần 8 s); khoảng cách tối thiểu 0,4 s giữa các lời gọi; toàn bộ bridge bị kill sau `MARKETLAB_PROVIDER_TIMEOUT_SECONDS` (180 s) → `PROVIDER_TIMEOUT`. Backfill tải một cửa sổ rộng một lần rồi phục vụ từng phiên từ bộ nhớ; giới hạn `--max-sessions` (mặc định 40 ngày thường) và dừng ở phiên FAILED/PARTIAL/SKIPPED đầu tiên. Dữ liệu trễ: Task Scheduler chạy 16:10, 17:30, 19:30 (giờ VN) với `-IfNeeded`.

## 9. Reconciliation (cần người duyệt)

```powershell
.venv\Scripts\python -m marketlab_app.cli eod reconcile list --status PENDING_REVIEW
.venv\Scripts\python -m marketlab_app.cli eod reconcile reject  --id 7 --reviewer "<tên>" --note "giữ giá gốc"
.venv\Scripts\python -m marketlab_app.cli eod reconcile approve --id 7 --reviewer "<tên>" --note "<lý do>" --i-understand-this-overwrites-a-closed-price
```

`approve` là thao tác duy nhất ghi đè giá đã chốt, đi qua `usp_InsertDailyPrice @AllowUpdate=1`, có người duyệt và ghi chú. Lưu ý: ghi đè một phần chuỗi bằng giá đã điều chỉnh sẽ trộn basis — nên tạo dataset mới nếu muốn chuyển toàn bộ sang basis mới.
