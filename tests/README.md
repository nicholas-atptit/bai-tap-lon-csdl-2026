# Kiểm chứng công khai

## Không cần SQL Server

```powershell
python -X utf8 -m unittest discover -s tests -p "test_*.py" -v
python -X utf8 scripts/check_publication.py
python -X utf8 scripts/import_data.py
```

7 ca kiểm tra JSON/độ phủ run được giữ logic từ verifier cũ; chỉ đổi import sang module không phụ thuộc private data. 4 ca delivery gate giữ nguyên. check_publication kiểm tra file/allowlist/hash, SQL objects, Markdown links, dữ liệu mô phỏng, container Office/PDF/ERD và quét mẫu secret; đây không phải chứng nhận bảo mật tuyệt đối. import_data ghi SQL mới vào tests/generated và so byte với all-in-one; không thay bản SQL đã duyệt. Nếu output đã có, chọn `--output` mới để giữ lần trước.

## SQL trên demo có sẵn

```powershell
python -X utf8 scripts/run_public_regression.py --server .
```

Cần sqlcmd ODBC với các cờ đã nêu trong INSTALLATION_GUIDE và Windows Authentication. Script chạy preflight chỉ đọc trước; chỉ chấp nhận MarketLabVN30_Demo với đúng mẫu mô phỏng. Không triển khai lại schema, không mở database nghiên cứu. Chạy hai lần live demo, 44 ca SQL, từng16query, đối chiếu metric SQL/Python, conflict late-batch51100, JSON Unicode và hash mọi hàng/cột của13bảng trước/sau. Các thao tác ghi có kiểm soát đều rollback; mỗi lần có thư mục tests/runs mới, không ghi đè thất bại trước.

Database chưa có: tạo demo bằng all_in_one theo [cài đặt](../docs/INSTALLATION_GUIDE.md), rồi chạy kiểm chứng. Không đổi USE sang DB thật hoặc xóa DB để làm PASS.

## QA tài liệu tùy chọn

```powershell
python -m pip install -r requirements.txt
python -X utf8 scripts/check_documents.py
```

PyMuPDF/Pillow chỉ cần cho QA PDF/render, không cần cho SQL. Không dựng lại DOCX/PPTX đã duyệt. QA mở container OOXML, xác nhận 14slides/9trang, đối chiếu văn bản và kiểm khung chữ, render PDF/ERD để xem. Cần rà ảnh render bằng mắt; số trang/token đơn lẻ không chứng minh bố cục đẹp hoặc Word/PDF giống nhau.

## Bằng chứng lịch sử

`reference_evidence` là các tệp đã rà soát từ đợt bàn giao trước, gồm log mô phỏng, schema và tổng hợp4DB. 176 lượtSQL/64lượtquery là lịch sử, không phải lần chạy mới của người clone. `fixtures/legacy12` chứa DDLgốc có hash cho migration12→13, không phải bộ triển khai hiện hành. Các log nội bộ/thất bại gốc vẫn được giữ riêng; [kiểm toán công khai](../docs/HISTORICAL_FAILURE_AUDIT.md) giữ mọi trạng thái và blocker. Không đưa research query rows, private manifests, transcript nội bộ lên GitHub.

Quy ước: PASS có bằng chứng đúng phạm vi; FAIL có phép kiểm không đạt; BLOCKED thiếu điều kiện bên ngoài; NOT VERIFIED chưa được kiểm đúng phạm vi. Chỉ số 0 hàng hợp lệ không đồng nghĩa thiếu outputJSON được coi là mảng rỗng.
