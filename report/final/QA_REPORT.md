# QA báo cáo FINAL – MarketLab VN30

Ngày QA: 06/11/2026. Máy: Windows 11 Pro, Microsoft Word for Microsoft 365 (COM), Poppler `pdftoppm`/`pdfinfo`/`pdffonts` (MiKTeX).

## 1. Tệp bàn giao

| Tệp | Nội dung |
|---|---|
| `report/final/MarketLabVN30_FINAL.docx` | Bản FINAL dựng từ **bản sao** template 44 trang (`report/team/MarketLabVN30_BaoCao_CHI_TIET_GIU_FORM_GOC.docx`, sha256 `47554c43…`, trùng byte với bản trong Downloads) |
| `report/final/MarketLabVN30_FINAL.pdf` | Xuất bằng Word, **65 trang A4**, mọi font được nhúng (Times New Roman, Calibri, Cambria, Consolas, Segoe UI Symbol, Symbol, Arial) |
| `report/final/CLAIMS_EVIDENCE_MATRIX.md` | 34 tuyên bố → lệnh/artefact kiểm chứng → trạng thái |
| `report/final/assets/architecture_final.png` | Sơ đồ kiến trúc cuối (Hình 3, do nhóm vẽ bằng `scripts/draw_architecture.py`) |
| `report/final/assets/screens/*.png` + `screens_manifest.json` | 17 ảnh chụp tự động giao diện (đã có từ commit `701d0c5`) |

Template gốc và báo cáo cũ (`report/MarketLabVN30_Report.*`, `report/team/*`) **không bị sửa** – script chỉ đọc template và ghi ra `report/final/`.

Mã nguồn ứng dụng được mô tả: commit `701d0c5` (nhánh `feature/marketlab-working-product`). Báo cáo, script dựng và tệp QA này nằm trong commit kế tiếp trên cùng nhánh (SHA ghi ở `git log -- report/final/QA_REPORT.md`).

## 2. Cách tái tạo

```powershell
uv run --no-project --with python-docx --with pillow python scripts/build_final_report.py   # dựng DOCX từ bản sao template
powershell -ExecutionPolicy Bypass -File scripts\Finalize-Report.ps1                        # Word: cập nhật TOC/danh mục, xuất PDF
uv run --no-project --with pillow python scripts/render_report_pages.py                    # PDF -> PNG + trang tổng hợp (var/report_render, gitignored)
```

Kiểm tra cấu trúc OOXML: `validate.py report/final/MarketLabVN30_FINAL.docx --original <template>` → *All validations PASSED*. Script tự kiểm tra không trùng số Hình/Bảng (17 hình; 41 bảng, các bảng chèn thêm dùng hậu tố a/b để giữ nguyên số tham chiếu của template).

## 3. Kiểm tra từng trang

Đã render cả 65 trang (70 dpi, 11 trang tổng hợp 6 trang/tấm) và xem từng tấm. Kiểm tra bổ sung bằng `pdftotext` (số dòng chữ mỗi trang – không có trang trắng) và `pdfimages -list` (vị trí ảnh).

| Hạng mục | Kết quả |
|---|---|
| Bìa (logo, tên đề tài, giảng viên, sinh viên, mã SV) | Giữ nguyên template; chỉ đổi dòng phụ đề "Mở rộng: …" |
| Mục lục, Danh mục hình (17), Danh mục bảng (41) | Trường Word thật (`TOC \o "1-3"`, `TOC \t "Caption Figure,1"`, `TOC \t "Caption Table,1"`), Word cập nhật 2 lượt; số trang khớp vị trí thực (đối chiếu ngẫu nhiên: Ch.5 → tr.41, Hình 13 → tr.51, Bảng 28 → tr.55) |
| Header / số trang | Giữ của template trên mọi trang |
| Font tiếng Việt | Không lỗi dấu trong bản render; mọi font nhúng |
| Chương bắt đầu trang mới | Có (CHƯƠNG 1–5, KẾT LUẬN, TÀI LIỆU THAM KHẢO, PHỤ LỤC A, B) |
| Bảng | Không dòng nào bị cắt ngang trang; bảng ngắn không tách khỏi chú thích; tiêu đề cột lặp lại khi sang trang |
| Ảnh | Không ảnh nào tràn lề hoặc chiếm trọn trang; ảnh toàn trang quá cao được cắt lấy phần đầu (ghi rõ "phần đầu trang" trong dòng nguồn) |
| Đoạn mã / output SQL | Khối ≤ 12 dòng không bị tách trang |
| Phụ lục Claude Code | Đã loại bỏ; `pdftotext | grep -c Claude` = 0 |
| "Swagger"/"API Gateway" | 10 lần xuất hiện, tất cả mô tả việc **đã gỡ** (không còn là kiến trúc cuối) |

### Lỗi phát hiện khi QA và đã sửa

| # | Lỗi | Sửa |
|---|---|---|
| Q1 | Word treo > 20 phút khi xuất PDF trong cùng phiên vừa cập nhật TOC; lần 2 treo khi xuất trực tiếp từ cùng tiến trình | `Finalize-Report.ps1`: phiên 1 cập nhật trường + lưu; phiên 2 là tiến trình `powershell.exe` riêng mở bản chỉ đọc, `SaveAs2` ra `%TEMP%` rồi chép vào `report/final` (≈ 9 giây) |
| Q2 | XML sai thứ tự phần tử (`jc`, `tblLayout`, `shd`, `cantSplit`) làm Word hiện hộp thoại ẩn "unreadable content" | Chèn đúng thứ tự schema; validator PASS |
| Q3 | Trang trắng sau mục 3.6 (nội dung chèn sau đoạn ngắt trang của chương) | Neo nội dung trước đoạn ngắt trang; thay đoạn ngắt bằng "page break before" ở tiêu đề chương |
| Q4 | Chương 1 và Danh mục hình không sang trang mới (đoạn mang ngắt trang bị trường danh mục thay thế) | Đặt "page break before" cho mọi tiêu đề chương/phụ lục |
| Q5 | Chú thích hình quá dài (route, viewport, giờ) làm danh mục hình rối | Chú thích ngắn; thông tin nguồn ở dòng riêng in nghiêng dưới chú thích, bằng tiếng Việt |
| Q6 | Ảnh toàn trang 1440×2569 chiếm cả trang | Cắt phần đầu (≤ 1250 px), ghi rõ trong dòng nguồn |
| Q7 | Hình 16/17 (điện thoại) mỗi ảnh một trang, nhiều khoảng trắng | Đặt cạnh nhau trong bảng không viền, mỗi ô có chú thích riêng |
| Q8 | Đoạn văn chèn thêm căn trái, không thụt đầu dòng như template | Căn đều, thụt 0,75 cm như đoạn gốc; tài liệu tham khảo [14]–[20] cùng định dạng [1]–[13] |
| Q9 | Ô bảng 3 mất định dạng (TNR 10pt) khi thay chữ | `set_text` giữ run có định dạng của template |
| Q10 | Cột "Mã" bảng 1–2 quá hẹp ("M01" xuống dòng), cột bảng 3a/18a bị cắt chữ | Nới độ rộng cột |
| Q11 | Bảng chèn sát đoạn văn kế tiếp | Thêm khoảng cách 8 pt sau bảng |
| Q12 | Đoạn trích thủ tục quá dài (thông báo lỗi nguyên văn tiếng Anh tràn dòng) | Rút gọn, giữ đúng nguyên văn logic của `sql/13_eod_extension.sql` (đã đối chiếu dòng 105–128) |

## 4. Ảnh trong báo cáo

| Loại | Số lượng | Nguồn | Thật/không thật |
|---|---|---|---|
| Ảnh giao diện web (Hình 4–15, 17) | 13 ảnh | `scripts/capture_final_screenshots.py`, Edge, ứng dụng đang chạy, 06/11/2026 00:50–00:51 | Thật; DEMO = dữ liệu mô phỏng (ghi nhãn), REAL = dữ liệu thật đã làm mờ giá |
| Ảnh "trước khi hoàn thiện" (Hình 16) | 1 ảnh | `tests/product_evidence/ui_audit/before/`, 06/11/2026 00:02, giao diện commit `da7b27b` | Thật (giao diện cũ) |
| Sơ đồ kiến trúc (Hình 3) | 1 | `scripts/draw_architecture.py` | Sơ đồ thiết kế, không phải ảnh chụp |
| Hình 1–2 (ERD, nhóm chức năng) | 2 | Template của nhóm | Giữ nguyên |
| Ảnh SSMS | 0 | — | **NOT DONE**: báo cáo dùng output `sqlcmd` dạng văn bản (chạy ngày 06/11/2026); danh sách ảnh cần chụp ở Phụ lục A.1 |

Tổng ảnh giao diện thật: **14** (13 ảnh ứng dụng cuối + 1 ảnh trước khi hoàn thiện). Không có ảnh nào được dựng/giả lập.

## 5. Kết quả kiểm chứng được trích trong báo cáo

| Hạng mục | Kết quả | Trạng thái |
|---|---|---|
| 44 ca SQL gốc + 16 truy vấn + live demo + hash 13 bảng | PASS (`tests/runs/public_20261105T175220966677Z/`) | PASS |
| Bộ kiểm thử phần mở rộng | 102 passed (unit 36, EOD 23, SQL regression 5, web 31, E2E 7) | PASS |
| Kiểm tra giao diện 4 kích thước × 2 chế độ × 5 trang | 40/40, 0 console error, 0 request lỗi, 0 fetch tới origin ứng dụng | PASS |
| Đối chiếu số liệu trang ↔ SQL | DEMO 9/9, REAL 11/11 | PASS |
| Bảng 22 trên DB nghiên cứu (chỉ đọc) | 600 quan sát, khớp | PASS |
| Lịch 16:10 tự chạy | Task cài ở trạng thái tắt | NOT VERIFIED |
| Migration DB nghiên cứu | Không thực hiện | NOT DONE |
| Tạo dự báo mới hằng ngày | Không có model artifact | NOT IMPLEMENTED |
| Ảnh SSMS | Chưa chụp | NOT DONE |
| Push nhánh / pull request | Bị chặn quyền | BLOCKED |

## 6. Dữ liệu riêng tư

Không có giá OHLCV thật, token, mật khẩu hay chuỗi kết nối trong DOCX/PDF/MD. Ảnh REAL làm mờ ô giá, khối lượng và biểu đồ giá; các ảnh vận hành REAL chỉ có số đếm, ngày và trạng thái. Ma trận tuyên bố không ghi giá trị giá cụ thể của nguồn KBS.
