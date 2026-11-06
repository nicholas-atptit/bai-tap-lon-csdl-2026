# Kiểm tra trước bàn giao GitHub — 06/11/2026

Đích công bố: `nicholas-atptit/bai-tap-lon-csdl-2026`, nhánh
`feature/marketlab-working-product`, PR vào `main`. Đây là biên bản kiểm tra
trước push; việc nhánh và tệp đã tồn tại trên GitHub phải được xác minh sau push.

## Báo cáo nộp bài

- [DOCX FINAL](../report/final/MarketLabVN30_FINAL_CHUAN_HOA_SSMS.docx)
- [PDF FINAL](../report/final/MarketLabVN30_FINAL_CHUAN_HOA_SSMS.pdf)

Hai tệp giữ nguyên byte từ commit `7b82653`. Không dựng lại báo cáo. Bản nền
chuẩn hóa có 42 trang; bản bổ sung bằng chứng có 54 trang A4, 12 ảnh SSMS thật
và sáu trang chức năng Web. Đã xem bản render của cả 54 trang và kiểm tra 129
liên kết mục lục/danh mục: không có sai lệch trang. DOCX không có comments hoặc
tracked changes. Các bản cũ trong `archive/`, `base/` và `report/team/` là tư liệu
nguồn; tệp nộp bài là cặp có hậu tố `FINAL_CHUAN_HOA_SSMS` ở trên.

Đọc lại SQL tổng hợp từ Live cho kết quả 28.097 dòng OHLCV, 30 mã, 956 phiên,
từ 03/01/2023 đến 05/11/2026. VPL có 373 phiên từ 13/05/2025; báo cáo ghi rõ
583 phiên trước đó không có dữ liệu nguồn. Không đưa lại log lỗi dài hay bảng
kỹ thuật đã loại bỏ. Truy vấn, Views, Stored Procedures, Functions và kiểm thử
đều có trong báo cáo.

## Kiểm thử thực chạy

| Lệnh | Kết quả ngày 06/11/2026 |
|---|---|
| `uv run pytest tests/product` | **140 passed**, không fail/skip; 93,29 giây; một cảnh báo deprecation của thư viện |
| `python scripts/run_public_regression.py` | **44/44** ca SQL, **16/16** truy vấn, hai lượt live demo; hash dữ liệu của cả 13 bảng không đổi |
| `python -m unittest discover -s tests -p 'test_*.py' -v` | **14 passed**, gồm ba kiểm tra phạm vi publication |

Kết nối SQL bằng Windows Authentication và bộ kiểm thử product cần chạy ngoài
sandbox của môi trường kiểm tra. Regression dùng DEMO tổng hợp; integration
test dùng database có tên và tag riêng. Không sửa database nghiên cứu/Live/Ops.

## Phạm vi và quyền công bố

Đã kiểm tra 7 commit chưa xuất bản tại `7b82653` so với các ref origin vừa fetch:
492 blob duy nhất tính cả base công khai; văn bản, XML/metadata Office, văn bản
và metadata PDF, cùng 174 ảnh duy nhất được kiểm tra. Không phát hiện secret
theo các mẫu quét, giá trị secret từ cấu hình local, Office embedding, database
backup, SQL dump giá thật hoặc tệp dữ liệu thị trường hạn chế trong tập Git này.
Các tệp dữ liệu công khai là DEMO tổng hợp. Ảnh giá thật đã che ô giá/khối lượng
và nhãn biểu đồ; ảnh SSMS dùng DEMO hoặc số liệu tổng hợp. Danh tính tác giả và
học phần thuộc nội dung báo cáo được yêu cầu công bố. Đây là kết quả kiểm toán
có phạm vi, không phải bảo đảm tuyệt đối hoặc bằng chứng quyền phân phối dữ liệu
của KBS/vnstock.

[Allowlist](PUBLICATION_ALLOWLIST.json) ghi đúng từng tệp, phân loại, số byte và
SHA-256 sau rà soát. Gate vẫn kiểm tra đầy đủ allowlist/hash/secret/link/SQL/DEMO.
Phạm vi local được khai báo tường minh (`.env`, `.venv`, `var`, cache, kết quả
chạy và bằng chứng private); nếu một tệp thuộc phạm vi này bị đưa vào Git index,
gate từ chối. Gate không dùng `.gitignore` để quyết định tệp công khai và vẫn
phát hiện tệp chưa được duyệt. Tham chiếu hệ thống `msdb.dbo.backupset` của EOD
preflight được phân biệt với đối tượng ứng dụng; đối tượng dbo không xác định
vẫn bị từ chối. Không vô hiệu hóa assertion hoặc bỏ publication gate.

Trước push chạy `python scripts/check_publication.py` và bản `--staged` để đối
chiếu toàn bộ byte trong Git index với đúng tập đã duyệt. Không cần sửa lịch sử
7 commit vì không tìm thấy nội dung bị cấm trong phạm vi đã kiểm tra. Không
force push, không thay đổi lịch sử public, không merge PR.

Receipt kiểm tra và SHA-256 hai báo cáo:
[FINAL_DELIVERY_20261106.json](../tests/publication_evidence/FINAL_DELIVERY_20261106.json).
