# Runbook Windows — MarketLab VN30 local product

Sản phẩm chạy **cục bộ** trên Windows: một FastAPI gateway (API + Swagger + giao diện web tĩnh) bind `127.0.0.1`, đọc SQL Server qua pyodbc, cộng một worker EOD (CLI / nút có bảo vệ / Task Scheduler). Không phải sàn giao dịch, không phải khuyến nghị đầu tư, không tạo dự báo mới.

## 1. Kiến trúc

```text
 Trình duyệt (Edge/Chrome) ──HTTP 127.0.0.1:8000──►  FastAPI gateway (marketlab_app/api.py)
   index.html + app.js + charts.js (SVG, không CDN)    │  Host/Origin check, CSP, token cho POST, chống brute-force
                                                      │  pyodbc (Windows Auth / SQL Auth), query tham số hóa, timeout
                                                      ▼
            ┌──────────── SQL Server (MSSQLSERVER) ───────────────────────────────────────────┐
            │ MarketLabVN30_Demo            SYNTHETIC, 13 bảng — chỉ đọc (DEMO_OFFLINE)         │
            │ MarketLabVN30_Live            REAL_PRIVATE, 13 bảng + schema ops (1 proc, 0 bảng) │
            │ MarketLabVN30_Research_2026…  REAL_PRIVATE nghiên cứu — chỉ đọc, không migrate    │
            │ MarketLabVN30_Ops             ops.EodRun/EodRunItem/PriceReconciliation/…         │
            └───────────────────────────────────────────────────────────────────────────────────┘
                                                      ▲
 Task Scheduler / CLI / nút UI ──► EodService (marketlab_app/eod/service.py)
                                     │ lịch phiên (Asia/Ho_Chi_Minh) • validate OHLCV • ops.usp_EodApplySession
                                     └─► subprocess: <python có vnstock> -I kbs_bridge.py  ──► KBS (Internet)
```

Luồng EOD: quyết định phiên → tải đủ universe → validate → `ops.usp_EodApplySession` (applock, TradingDay, ObservedThrough, `usp_InsertDailyPrice @AllowUpdate=0`, all-or-nothing) → lineage/drift probe → đánh giá lại dự báo đã trưởng thành → nhật ký. Chi tiết: [EOD_DATA_CONTRACT.md](EOD_DATA_CONTRACT.md).

## 2. Cài đặt lần đầu

Yêu cầu: SQL Server (đã chạy `sql/all_in_one.sql` cho demo), ODBC Driver 18, `uv`, PowerShell.

```powershell
git clone https://github.com/nicholas-atptit/bai-tap-lon-csdl-2026.git
cd bai-tap-lon-csdl-2026
git checkout feature/marketlab-working-product
powershell -ExecutionPolicy Bypass -File scripts\Setup-MarketLab.ps1
```

`Setup-MarketLab.ps1`: kiểm tra uv/ODBC → `uv sync --frozen` (phiên bản ghim trong `uv.lock`, chỉ PyPI) → tạo `.env` từ `.env.example`, sinh `MARKETLAB_OPS_TOKEN` ngẫu nhiên (không in ra) → `cli check`. Không tạo database, task, firewall rule hay service.

## 3. Chạy DEMO_OFFLINE (không cần Internet, không cần dữ liệu riêng)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\Start-MarketLab.ps1
```

Mở `http://127.0.0.1:8000/` (UI) và `http://127.0.0.1:8000/api/docs` (Swagger, tài sản cục bộ). Nhãn vàng "DEMO_OFFLINE · DỮ LIỆU MÔ PHỎNG (SYNTHETIC)". Đồng bộ EOD bị tắt (không đưa dữ liệu thật vào CSDL mô phỏng). `-Background` chạy ẩn, dừng bằng `scripts\Stop-MarketLab.ps1 -Port 8000`.

## 4. Chạy REAL_PRIVATE

### 4.1 Database REAL_PRIVATE mới cho EOD (không đụng DB nghiên cứu)

```powershell
$env:MARKETLAB_MODE='REAL_PRIVATE'; $env:MARKETLAB_SQL_DATABASE='MarketLabVN30_Live'
.venv\Scripts\python -m marketlab_app.deploy live-db --database MarketLabVN30_Live `
  --universe-csv "<thư mục nghiên cứu riêng>\config\vn30_constituents_2026_06.csv" --observed-through 2026-09-30
```

Tạo DB mới (từ chối tên demo/research, từ chối DB có sẵn không gắn tag), schema 00–06, migration 13, seed Market/Stock/VN30 snapshot/Dataset (không giá, không dự báo), DB `MarketLabVN30_Ops` (schema 14) và `ops.EodConfig`.

### 4.2 Interpreter có vnstock (nguồn thật)

vnstock không còn trên PyPI; người dùng tự cài vào một interpreter riêng (ví dụ `pip install vnstock --extra-index-url https://vnstocks.com/api/simple` trong venv của bạn), rồi:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\Setup-MarketLab.ps1 -EodDatabase MarketLabVN30_Live `
  -ProviderPython "C:\Users\<you>\AppData\Local\Programs\Python\Python312\python.exe"
```

### 4.3 Khởi động giao diện REAL_PRIVATE

```powershell
powershell -ExecutionPolicy Bypass -File scripts\Start-MarketLab.ps1 -Mode REAL_PRIVATE -Database MarketLabVN30_Live -Port 8001
```

Nhãn đỏ "REAL_PRIVATE · DỮ LIỆU THẬT RIÊNG TƯ". Server **từ chối phục vụ** nếu dataset trong DB không khớp chế độ (`503 MODE_DATASET_MISMATCH`) — không tự chuyển chế độ. Có thể trỏ REAL_PRIVATE chỉ-đọc vào DB nghiên cứu (`-Database MarketLabVN30_Research_20261027 -Port 8002`): xem giá/dự báo/so sánh; EOD tắt vì DB đó chưa có migration.

## 5. Đồng bộ EOD

```powershell
# một phiên (mặc định = hôm nay theo giờ VN), dry run trước:
powershell -ExecutionPolicy Bypass -File scripts\Run-MarketLab-EOD.ps1 -Date 2026-11-04 -DryRun
powershell -ExecutionPolicy Bypass -File scripts\Run-MarketLab-EOD.ps1 -Date 2026-11-04
# backfill có giới hạn:
powershell -ExecutionPolicy Bypass -File scripts\Run-MarketLab-EOD.ps1 -Backfill -From 2026-10-01 -To 2026-10-31 -DryRun
# trạng thái:
.venv\Scripts\python -m marketlab_app.cli eod status
```

Mã thoát: 0 SUCCESS/DRY_RUN_OK/NO_SESSION, 10 SKIPPED, 20 PARTIAL, 30 FAILED, 2 lỗi cấu hình. Log: `var\logs\eod_task_<ngày>.log`, `var\logs\eod_<ngày>.log`.

Trên UI (tab **Vận hành dữ liệu**): nhập ngày + token (đọc từ `.env`, ô mật khẩu, không lưu trình duyệt) → **Dry run** hoặc **Sync selected session** → hộp xác nhận → job nền, trạng thái lấy từ API thật.

## 6. Task Scheduler (chỉ khi bạn chủ động)

```powershell
.\scripts\Install-MarketLab-EODTask.ps1            # cài DISABLED: T2–T6 16:10, 17:30, 19:30 (giờ VN, tự quy đổi)
.\scripts\Install-MarketLab-EODTask.ps1 -Show      # xem trạng thái, LastTaskResult (= exit code)
.\scripts\Install-MarketLab-EODTask.ps1 -RunNow    # chạy thử một lần (task vẫn disabled)
.\scripts\Install-MarketLab-EODTask.ps1 -Enable    # chỉ bật khi đã có lần chạy tay SUCCESS (không dry run)
.\scripts\Install-MarketLab-EODTask.ps1 -Disable
.\scripts\Install-MarketLab-EODTask.ps1 -Uninstall
```

Task chạy bằng user hiện tại, chỉ khi đã đăng nhập (không lưu mật khẩu), working directory = repo, interpreter = `.venv\Scripts\python.exe`, `-IfNeeded` (bỏ qua phiên đã SUCCESS), không chạy song song, giới hạn 1 giờ. Đích ghi là `MARKETLAB_EOD_DATABASE` trong `.env` — dashboard có thể vẫn ở DEMO_OFFLINE.

## 7. Migration database có dữ liệu thật (ví dụ DB nghiên cứu) — cần backup + xác nhận

```powershell
sqlcmd -S . -E -C -b -W -s "|" -d <DB> -i sql\13_eod_preflight.sql          # chỉ đọc
sqlcmd -S . -E -C -Q "BACKUP DATABASE [<DB>] TO DISK=N'D:\Backup\<DB>_pre_eod_v1.bak' WITH COPY_ONLY, CHECKSUM, INIT"
sqlcmd -S . -E -C -Q "RESTORE VERIFYONLY FROM DISK=N'D:\Backup\<DB>_pre_eod_v1.bak' WITH CHECKSUM"
.venv\Scripts\python -m marketlab_app.deploy migrate --database <DB> --confirm-backup D:\Backup\<DB>_pre_eod_v1.bak
```

Rollback: `sqlcmd -S . -E -C -b -d <DB> -i sql\13_eod_extension_rollback.sql` (khôi phục nguyên văn trigger gốc, bỏ procedure/schema `ops`; **không** hoàn tác dữ liệu đã đồng bộ — dùng backup). Ops DB: `sqlcmd … -d MarketLabVN30_Ops -v ConfirmDropOps=YES -i sql\14_ops_database_rollback.sql` (xóa lịch sử nhật ký — backup trước).

## 8. Ví dụ JSON (dữ liệu mô phỏng)

`GET /api/health`
```json
{"status":"ok","version":"0.1.0","mode":"DEMO_OFFLINE","server_time_vn":"2026-11-05T23:14:57+07:00"}
```
`GET /api/prices?dataset_id=1&ticker=DEMO01&limit=1`
```json
{"items":[{"Ticker":"DEMO01","StockId":1,"TradeDate":"2025-02-19","OpenPrice":25.6003,"HighPrice":26.2288,"LowPrice":25.1003,"ClosePrice":25.7288,"Volume":17800,"LoadedAt":"2026-10-27T09:42:02"}],"total":35,"limit":1,"offset":0,"price_unit":"Đơn vị mô phỏng","price_basis":"SOURCE_CLOSE"}
```
`GET /api/performance?dataset_id=1&as_of=2026-07-01` (rút gọn)
```json
{"as_of":"2026-07-01","items":[{"RunId":1,"ModelCode":"demo_baseline","TotalPredictions":129,"EvaluatedRows":128,"PendingNotMatured":1,"MissingEndpoint":0,"Accuracy":0.546875,"BrierScore":0.25,"NaturalLogLoss":0.6931471805599462}]}
```
Lỗi có mã: `GET /api/prices?dataset_id=1&date_from=2025-02-10&date_to=2025-01-01` → `422`
```json
{"error":{"code":"INVALID_DATE_RANGE","message":"date_from must be <= date_to"}}
```
`POST /api/ops/eod` (header `X-MarketLab-Ops-Token`, body `{"session_date":"2026-11-05","dry_run":true,"confirm":"DRY_RUN"}`) → `202 {"job_id":"…","state":"RUNNING","poll":"/api/ops/jobs/…"}`; kết quả job (REAL, chỉ số đếm):
```json
{"eod_run_id":32,"session_date":"2026-11-05","status":"DRY_RUN_OK","requested":30,"received":30,"inserted":0,"unchanged":30,"would_insert":0,"exit_code":0}
```

## 9. Bảo mật cục bộ

Chỉ bind loopback (cấu hình từ chối host khác); Host header phải là `127.0.0.1/localhost:<port>` (421); POST từ Origin khác hoặc `Sec-Fetch-Site: cross-site` bị chặn (403); không bật CORS; CSP `default-src 'self'` (không inline script); token so sánh hằng thời gian, 5 lần sai/10 phút → 429; một job EOD tại một thời điểm; secret không có trong log, JS, URL hay `/api/meta`. `.env` bị git bỏ qua.

## 10. Hạn chế còn lại

* Không có inference: không model artifact → không phát hành dự báo mới (UI ghi rõ).
* Universe = snapshot VN30 06/2026 cố định; không phải thành phần hiện hành.
* Giá KBS được điều chỉnh hồi tố; chuỗi lưu có thể gãy basis; drift probe chỉ phát hiện trong cửa sổ 10 ngày.
* Lịch nghỉ suy từ chuỗi chỉ số của chính provider (nếu provider sai, lịch sai theo); không có lịch HOSE chính thức máy-đọc-được trong repo.
* Task chạy khi user đăng nhập; máy tắt/ngủ thì bỏ lỡ (StartWhenAvailable chạy bù khi bật lại).
* Express/SQL Server 2016 runtime chưa kiểm chứng; chỉ kiểm trên SQL Server 2025 Developer.
* `scripts/check_publication.py` FAIL trên nhánh này đến khi allowlist được cập nhật có review.
