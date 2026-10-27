# Kiểm toán công bố GitHub

Ngày chuẩn bị: 27/10/2026 (Asia/Saigon). Repository công khai: https://github.com/nicholas-atptit/bai-tap-lon-csdl-2026, branch main.

Trạng thái tại commit chuẩn bị: **VERIFIED LOCALLY, NOT YET PUSHED**. Không có SHA remote để báo PUSHED ở thời điểm này; audit sẽ ghi commit nội dung sau khi push và fetch thực tế.

Đã clone vào thư mục công bố riêng, remote ban đầu rỗng. Dự án gốc không khởi tạo Git hay sửa đổi. 81 file implementation/tài liệu/bằng chứng được sao nguyên byte; các dẫn xuất được kê ở [SOURCE_LINEAGE](SOURCE_LINEAGE.csv). Danh sách tệp được phép ở [PUBLICATION_ALLOWLIST](PUBLICATION_ALLOWLIST.json), lý do loại ở [EXCLUDED_MATERIALS](EXCLUDED_MATERIALS.csv).

Kiểm chứng mới: 44 ca SQL/16 query/2 lượt live demo trên DB mô phỏng có sẵn; chỉ tiêu SQL/Python khớp; hash mọi hàng/cột của cả13bảng không đổi; không rebuild hoặc mở DB nghiên cứu. 11 unit tests PASS; tái tạo SQL khớp byte. Báo cáo9trang/slide14trang/ERD1trang mở và render được, token không thiếu, không text vượt trang; đã rà contact sheets. [SQL receipt](../tests/publication_evidence/PUBLIC_REGRESSION.json), [QA tài liệu](../tests/publication_evidence/document_checks.json).

Kết quả176lượtSQL/64query ở [reference summary](../tests/reference_evidence/final_regression_summary.json) thuộc đợt lịch sử, không được tính như kiểm chứng mới. [39 vấn đề lịch sử](HISTORICAL_FAILURE_AUDIT.md) vẫn giữ30RESOLVED/9BLOCKED/0OPEN.

Không công bố bản ghi nghiên cứu, private manifest/snapshot, internal logs, database backup, cache, credentials hoặc ZIP. Không cấp giấy phép mới cho dữ liệu hoặc nội dung có quyền chưa rõ. Giới hạn còn giữ: Express/2016 runtime NOT VERIFIED; Word Save/native PDF/UI và metadata/adjustment/membership/CompletedAt/rights BLOCKED theo kiểm toán. Source research không tái hiện record-level từ repo công khai.

Lần QA đầu phát cảnh báo import fitz đã deprecated; chuyển sang pymupdf trong script mới, không thay tài liệu/SQL. Không phát hiện lỗi SQL trong lượt công bố mới. Các lỗi công cụ/gate nếu có sẽ được lưu trong bằng chứng cục bộ và bổ sung trước công bố.
