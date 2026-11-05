# Runbook Windows — MarketLab VN30 (ứng dụng web cục bộ)

Ứng dụng web Python chạy **cục bộ** trên Windows, bind `127.0.0.1`, dựng toàn bộ trang HTML phía máy chủ từ SQL Server, cộng một worker EOD (CLI / Task Scheduler / form web có bảo vệ). Không có API Gateway, không REST JSON cho giao diện, không Swagger. Không phải sàn giao dịch, không phải khuyến nghị đầu tư, không tạo dự báo mới.

## 1. Kiến trúc

```text
 Trình duyệt (Edge/Chrome) ──HTTP, HTML──►  Ứng dụng web Python  (marketlab_app/web_app.py)
   CSS + enhance.js + charts.js              FastAPI (framework ASGI) + Jinja2 templates
   (không gọi mạng: CSP connect-src 'none')  Host/Origin check, CSP, CSRF, token, khóa brute-force
                                             queries.py (truy vấn tham số hóa) ─ pyodbc ─┐
                                                                                         ▼
            ┌──────────── SQL Server (MSSQLSERVER) ───────────────────────────────────────────────┐
            │ MarketLabVN30_Demo            SYNTHETIC, 13 bảng — chỉ đọc (DEMO_OFFLINE)             │
            │ MarketLabVN30_Live            REAL_PRIVATE, 13 bảng + schema ops (1 proc, 0 bảng)     │
            │ MarketLabVN30_Research_2026…  dữ liệu nghiên cứu — chỉ đọc (RESEARCH_READ_ONLY)       │
            │ MarketLabVN30_Ops             ops.EodRun / EodRunItem / PriceReconciliation / …  (v2) │
            └───────────────────────────────────────────────────────────────────────────────────────┘
                                                                                         ▲
 EOD Worker: Task Scheduler / CLI / form /ops/eod ──► EodService (marketlab_app/eod/service.py)
   lịch phiên Asia/Ho_Chi_Minh • validate OHLCV • ops.usp_EodApplySession (all-or-nothing) • nhật ký Ops
   └─► subprocess: <python có vnstock> -I kbs_bridge.py ──► KBS (Internet)
```

Trang: `/` Tổng quan · `/market` Giá & biểu đồ · `/forecast` Dự báo & hiệu năng · `/compare` So sánh mô hình · `/ops` Vận hành EOD (`/ops/jobs/<id>` theo dõi job). `/health` chỉ trả `ok …` dạng text để script khởi động kiểm tra tiến trình sống.

## 2. Cài đặt lần đầu

Yêu cầu: SQL Server đã chạy `sql/all_in_one.sql` (demo), ODBC Driver 18, `uv`, PowerShell.

```powershell
git clone https://github.com/nicholas-atptit/bai-tap-lon-csdl-2026.git
cd bai-tap-lon-csdl-2026
git checkout feature/marketlab-working-product
powershell -ExecutionPolicy Bypass -File scripts\Setup-MarketLab.ps1
```

`Setup-MarketLab.ps1`: kiểm tra uv/ODBC → `uv sync --frozen` (phiên bản ghim trong `uv.lock`, chỉ PyPI: fastapi, uvicorn, jinja2, pyodbc, tzdata) → tạo `.env` từ `.env.example`, sinh `MARKETLAB_OPS_TOKEN` ngẫu nhiên (không in ra) → `cli check`. Không tạo database, task, firewall rule hay service.

## 3. Chạy (một lệnh)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\Start-MarketLab.ps1
```

Mở **http://127.0.0.1:8000/**. Script kiểm tra `.venv`, dependency, `.env`, ODBC, kết nối SQL, schema, khớp chế độ ↔ dataset và cổng trống, rồi chạy server (Ctrl+C để dừng). `-Background` chạy ẩn (dừng: `scripts\Stop-MarketLab.ps1 -Port 8000`).

Dữ liệu thật riêng tư (instance thứ hai, tùy chọn):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\Start-MarketLab.ps1 -Mode REAL_PRIVATE -Database MarketLabVN30_Live -Port 8001
```

Nhãn: vàng **DEMO_OFFLINE** (mô phỏng), đỏ **REAL_PRIVATE** (dữ liệu thật, có EOD), tím **RESEARCH_READ_ONLY** (REAL nhưng DB không có migration EOD, ví dụ `-Database MarketLabVN30_Research_20261027`). Máy chủ từ chối phục vụ nếu dataset trong DB không khớp chế độ (HTTP 503 `MODE_DATASET_MISMATCH`), không tự chuyển chế độ. Liên kết "Chuyển chế độ" trên header trỏ sang instance kia (chỉ URL loopback, cấu hình `MARKETLAB_PEERS`).

### Lỗi thường gặp

| Hiện tượng | Xử lý |
|---|---|
| `Pre-start check failed` / trang 503 `DB_UNAVAILABLE` | Bật dịch vụ `MSSQLSERVER`; kiểm tra `MARKETLAB_SQL_SERVER` |
| `ODBC driver not found` | Cài ODBC Driver 18 hoặc đặt `MARKETLAB_SQL_DRIVER` |
| `Port 8000 is already in use` | `scripts\Stop-MarketLab.ps1 -Port 8000` hoặc `-Port 8002` |
| 503 `MODE_DATASET_MISMATCH` | Sửa `MARKETLAB_MODE`/`MARKETLAB_SQL_DATABASE` trong `.env` |
| Form EOD: `CSRF_FAILED` | Tải lại trang `/ops` (phiên biểu mẫu hết hạn sau 8 giờ) |
| Form EOD: `INVALID_OPS_TOKEN` / `TOO_MANY_AUTH_FAILURES` | Lấy `MARKETLAB_OPS_TOKEN` trong `.env` trên máy chủ; sai 5 lần thì chờ 10 phút |
| Job EOD `PROVIDER_NOT_CONFIGURED` | Đặt `MARKETLAB_PROVIDER_PYTHON` (mục 4.2) |

## 4. Database REAL_PRIVATE và nguồn

### 4.1 Tạo DB REAL_PRIVATE mới (không đụng DB nghiên cứu)

```powershell
$env:MARKETLAB_MODE='REAL_PRIVATE'; $env:MARKETLAB_SQL_DATABASE='MarketLabVN30_Live'
.venv\Scripts\python -m marketlab_app.deploy live-db --database MarketLabVN30_Live `
  --universe-csv "<thư mục nghiên cứu riêng>\config\vn30_constituents_2026_06.csv" --observed-through 2026-09-30
```

Tạo DB mới (từ chối tên demo/research, từ chối DB có sẵn không gắn tag), schema 00–06, migration 13, seed danh mục, DB `MarketLabVN30_Ops` (14 + 15) và `ops.EodConfig`. Không nạp giá, không tạo dự báo.

### 4.2 Interpreter có vnstock

vnstock không còn trên PyPI; người dùng tự cài vào interpreter riêng, rồi:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\Setup-MarketLab.ps1 -EodDatabase MarketLabVN30_Live `
  -ProviderPython "C:\Users\<you>\AppData\Local\Programs\Python\Python312\python.exe"
```

## 5. Đồng bộ EOD

```powershell
powershell -ExecutionPolicy Bypass -File scripts\Run-MarketLab-EOD.ps1 -Date 2026-11-05 -DryRun
powershell -ExecutionPolicy Bypass -File scripts\Run-MarketLab-EOD.ps1 -Date 2026-11-05
powershell -ExecutionPolicy Bypass -File scripts\Run-MarketLab-EOD.ps1 -Backfill -From 2026-10-01 -To 2026-10-31 -DryRun
.venv\Scripts\python -m marketlab_app.cli eod status
```

Mã thoát: 0 SUCCESS/DRY_RUN_OK/NO_SESSION, 10 SKIPPED, 20 PARTIAL, 30 FAILED, 2 lỗi cấu hình. Log: `var\logs\eod_task_<ngày>.log`, `var\logs\eod_<ngày>.log`; log web: `var\logs\web_<ngày>.log`.

Trên web (trang **Vận hành EOD**, chỉ chế độ REAL_PRIVATE): chọn ngày, nhập token (ô mật khẩu, không lưu), **Dry run** hoặc **Sync selected session** (bắt buộc tích ô xác nhận) → hộp xác nhận → máy chủ kiểm CSRF + Origin + token + khóa brute-force + chỉ một job → chuyển sang trang job tự làm mới tới khi xong → liên kết tới chi tiết run.

## 6. Task Scheduler (chỉ khi bạn chủ động)

```powershell
.\scripts\Install-MarketLab-EODTask.ps1            # cài DISABLED: T2–T6 16:10, 17:30, 19:30 (giờ VN)
.\scripts\Install-MarketLab-EODTask.ps1 -Show
.\scripts\Install-MarketLab-EODTask.ps1 -RunNow    # chạy thử một lần (task vẫn disabled)
.\scripts\Install-MarketLab-EODTask.ps1 -Enable    # chỉ bật khi đã có lần chạy tay SUCCESS
.\scripts\Install-MarketLab-EODTask.ps1 -Disable
.\scripts\Install-MarketLab-EODTask.ps1 -Uninstall
```

Task chạy bằng user hiện tại khi đã đăng nhập, working directory = repo, `-IfNeeded`, không chạy song song, giới hạn 1 giờ; đích ghi là `MARKETLAB_EOD_DATABASE` trong `.env`. EOD hoạt động độc lập với ứng dụng web (không cần server web chạy).

## 7. Migration và rollback

| Script | Áp lên | Rollback |
|---|---|---|
| `sql/13_eod_preflight.sql` (chỉ đọc) → `sql/13_eod_extension.sql` | DB nghiệp vụ REAL_PRIVATE | `sql/13_eod_extension_rollback.sql` (khôi phục nguyên văn trigger gốc) |
| `sql/14_ops_database.sql` | DB Ops | `sql/14_ops_database_rollback.sql -v ConfirmDropOps=YES` |
| `sql/15_ops_schema_v2.sql` (TriggerKind `WEB`) | DB Ops | `sql/15_ops_schema_v2_rollback.sql` (từ chối nếu đã có run WEB) |

DB có dữ liệu thật (ví dụ DB nghiên cứu) chỉ migrate sau backup đã kiểm và xác nhận của chủ dữ liệu:

```powershell
sqlcmd -S . -E -C -b -W -s "|" -d <DB> -i sql\13_eod_preflight.sql
sqlcmd -S . -E -C -Q "BACKUP DATABASE [<DB>] TO DISK=N'<DB>_pre_eod_v1.bak' WITH COPY_ONLY, CHECKSUM, INIT"
.venv\Scripts\python -m marketlab_app.deploy migrate --database <DB> --confirm-backup <đường dẫn .bak>
```

## 8. Bảo mật cục bộ

Chỉ bind loopback; Host header phải là `127.0.0.1/localhost:<port>` (421); POST từ Origin khác hoặc `Sec-Fetch-Site: cross-site` bị chặn (403); CSRF double-submit (cookie HttpOnly SameSite=Strict + trường ẩn, so sánh hằng thời gian); token so sánh hằng thời gian, 5 lần sai/10 phút → 429; xác nhận bắt buộc cho ghi thật; CSP `default-src 'self'; connect-src 'none'; form-action 'self'`; không CORS; không có endpoint chạy SQL tùy ý; lỗi SQL hiển thị mã + thông điệp đã khử chuỗi kết nối; secret không có trong HTML, JS, URL, log. `.env` bị git bỏ qua.

## 9. Hạn chế còn lại

* Không có inference: không model artifact → không phát hành dự báo mới (giao diện ghi rõ).
* Universe = snapshot VN30 06/2026 cố định, không phải thành phần hiện hành.
* Giá KBS được điều chỉnh hồi tố; chuỗi lưu có thể gãy basis; drift probe chỉ phát hiện trong cửa sổ 10 ngày; đối soát cần người duyệt.
* Lịch nghỉ suy từ chuỗi chỉ số của chính nguồn; không có lịch HOSE chính thức máy-đọc-được.
* Task chạy khi user đăng nhập; lịch tự động 16:10 chưa được bật/kiểm chứng.
* Express / SQL Server 2016: NOT VERIFIED.
* `scripts/check_publication.py` FAIL trên nhánh này cho tới khi allowlist được cập nhật có review.
