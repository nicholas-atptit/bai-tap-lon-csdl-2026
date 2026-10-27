# Kiểm toán công bố GitHub

**PUSHED — commit nội dung đã được kiểm chứng trực tiếp từ GitHub.**

## Danh tính bản công bố

- Ngày/giờ push: **27/10/2026 22:44:13 (Asia/Saigon, UTC+07:00)**.
- Repository **công khai**: [nicholas-atptit/bai-tap-lon-csdl-2026](https://github.com/nicholas-atptit/bai-tap-lon-csdl-2026).
- Branch: `main`.
- Commit nội dung đã push, fetch, clone và tải kiểm tra: [`497ef300d1515e4f2026492c0120cd6476121ed5`](https://github.com/nicholas-atptit/bai-tap-lon-csdl-2026/commit/497ef300d1515e4f2026492c0120cd6476121ed5).
- Số tệp: **138**, đúng toàn bộ [allowlist](PUBLICATION_ALLOWLIST.json).
- Người dùng đã xác nhận trực tiếp công bố đúng 138 tệp và đích công khai trước thao tác push thành công.

Audit này và receipt máy đọc được được bổ sung bằng commit kế tiếp, không đổi SQL, mẫu, báo cáo, slide hoặc ERD. SHA của commit chứa chính audit không thể tự nhúng vì thay nội dung sẽ đổi SHA; xem History của file để lấy commit audit, rồi dùng các lệnh bên dưới đối chiếu HEAD hiện hành. Receipt kiểm tra HEAD cuối được giữ trong hồ sơ bàn giao cục bộ, độc lập với vòng tự tham chiếu của file Git.

## Kiểm chứng remote đã thực hiện

|Phép kiểm|Kết quả thực tế|
|---|---|
|`git push -u origin main`|Exit **0**, tạo nhánh main trên remote; không force push, không xóa nhánh/lịch sử|
|`git status`, `git log -1 --oneline`, `git rev-parse HEAD`|Working tree sạch, commit nội dung như trên|
|`git fetch origin main` + `git rev-parse origin/main`|Thành công; local HEAD = origin/main = SHA trực tiếp từ `git ls-remote`|
|GitHub API refs/heads/main|Xác nhận cùng SHA, độc lập với Git clone cục bộ|
|`git ls-tree -r --name-only HEAD`|138 đường dẫn đúng allowlist, không có đường dẫn riêng tư ngoài danh sách|
|Clone mới qua HTTPS từ GitHub|Đủ 138 tệp, SHA-256 của từng tệp khớp byte với bản công bố đã rà soát|
|README qua GitHub HTML API|HTTP200, 21 heading gồm tiêu đề và 20 mục yêu cầu, ảnh ERD và liên kết được render|
|Hai hướng dẫn báo cáo/slide và TEAM_HANDOFF|HTTP200, HTML do GitHub render; bảng, headings và speaker notes có mặt|
|Tải trực tiếp artifact bằng URL raw gắn commit|Cả 7 tệp dưới đây HTTP200 và hash khớp|

|Tệp tải từ GitHub|HTTP|Byte|SHA-256|
|---|---|---:|---|
|report/MarketLabVN30_Report.docx|200|300574|`9f4f752112a011399ab28fa836874d072788ab7866aebccfbaee9c538ce9a304`|
|report/MarketLabVN30_Report.pdf|200|539280|`5aa3f2ecee145acf74c5834e869e36fa35bbfac83a93723f101a244898b8bb6a`|
|slides/MarketLabVN30_Presentation.pptx|200|356766|`04eb27d85ddb477a72948929ec5590fc31cd5325d8e2f8154b99b094b9249da3`|
|slides/MarketLabVN30_Presentation.pdf|200|322946|`c7829e9b0f42bda048227f3de6754979ccfbb24e4ab38e9f5d197739bda0f312`|
|docs/diagrams/marketlab_erd.svg|200|227405|`29c675f1042e5dea316d0d759b9887f94a0cf5c08b48256687d720220e72df09`|
|docs/diagrams/marketlab_erd.pdf|200|38439|`8654bcf7110c05eccf0b3a3e0e7aedf7704a65ffa18e7b4ac244d014c2799c61`|
|sql/all_in_one.sql|200|107172|`6692e7dad0c734bd2e37fa60ab537d91bc81a49bc6b7503ba3339f9a1222bca0`|

Snapshot máy đọc được: [offline_checks.json — trường github_publication](../tests/publication_evidence/offline_checks.json). Đây là bằng chứng remote của commit nội dung, không phải receipt tự tạo trước khi push. Các HTML render và transcript Git đầy đủ được giữ riêng trong hồ sơ công bố cục bộ; không đưa log nội bộ lên repository.

## Bảo vệ nguồn và nội dung công khai

Đã clone remote ban đầu rỗng vào thư mục công bố riêng trên ổ K; không khởi tạo Git trong dự án gốc. **81 tệp được sao nguyên byte**, gồm SQL, mẫu, ERD, tài liệu đã duyệt và bằng chứng mô phỏng; các dẫn xuất có xử lý được kê ở [SOURCE_LINEAGE.csv](SOURCE_LINEAGE.csv). 1.757 tệp dự án gốc đã đối chiếu SHA-256 không đổi. Không rebuild/reset/xóa database, không sửa nguồn nghiên cứu, không huấn luyện lại và không đổi kết quả đã xác minh.

Danh sách cho phép là từng đường dẫn cụ thể, không chỉ gitignore. Trước commit đã đọc tên/kích thước/diff, kiểm từng blob index và so byte với bản rà soát. Quét mẫu secret trên văn bản, XML trong Office và text trích PDF; kiểm không có macro/tệp nhúng; ảnh tài liệu được rà bằng mắt. Đây là phạm vi kiểm thực tế, không phải tuyên bố phát hiện được mọi secret có thể tồn tại.

Không đưa lên GitHub: bản ghi OHLCV/dự báo nghiên cứu, private source manifests, dữ liệu chuẩn bị riêng, snapshot PRIVATE, log truy vấn trả bản ghi thật, lịch sử công cụ nội bộ, credentials/API keys/.env, database backups/.bak/.mdf/.ldf, caches, Office temp hoặc ZIP. [EXCLUDED_MATERIALS.csv](EXCLUDED_MATERIALS.csv) ghi lý do theo nhóm; bản gốc và các lần thất bại được giữ cục bộ. 1.676 tệp gốc không được sao nguyên byte gồm cả bản trùng, cache và tài liệu có bản dẫn xuất; không gọi toàn bộ số đó là dữ liệu nhạy cảm. Không tự cấp giấy phép mới cho dự án/dữ liệu nguồn.

## Kết quả kỹ thuật và tài liệu

- **Lượt công bố mới:** 44 ca SQL, từng 16 query và 2 lượt live demo PASS trên database mô phỏng đã có; preflight chạy trước mọi thao tác ghi. SQL/Python khớp hai run, mỗi run 128 quan sát. Hash mọi hàng/cột của cả 13 bảng, kể cả LoadedAt, khớp trước–sau; conflict 51100 rollback đúng. Không truy cập DB nghiên cứu.
- **Kiểm thử cục bộ:** 11 unit tests PASS; 192 liên kết Markdown nội bộ hợp lệ trước khi bổ sung audit, 196 liên kết hợp lệ sau khi bổ sung; dựng lại SQL từ JSON mô phỏng khớp byte với all_in_one.sql. Bản clone commit cục bộ cũng chạy lại thành công offline tests và tái tạo SQL.
- **Tài liệu:** DOCX/PPTX hợp lệ; báo cáo PDF 9 trang, slide PPTX/PDF 14 trang, ERD PDF 1 trang; không thiếu token so với Office, không có bbox chữ ngoài trang; đã rà render toàn bộ. Báo cáo/slide/ERD gốc giữ nguyên hash. Word native PDF vẫn BLOCKED, không tuyên bố bố cục từng trang DOCX/PDF giống nhau.
- **Lịch sử được giữ riêng phạm vi:** 44 ca khác nhau × 4 DB = 176 lượt PASS,16 query × 4= 64 lượt ở [summary lịch sử](../tests/reference_evidence/final_regression_summary.json). Không cộng lượt công bố mới để biến chúng thành nhiều ca độc lập hơn. [Kiểm toán lịch sử](HISTORICAL_FAILURE_AUDIT.md) vẫn 39 vấn đề: 30 RESOLVED/9 BLOCKED/0 OPEN.

## Vấn đề công cụ trong lần công bố

|Vấn đề|Xử lý và giới hạn|
|---|---|
|Git báo dubious ownership giữa tài khoản sandbox và tài khoản Windows|Dùng safe.directory chỉ cho từng lệnh trên đúng clone do tác vụ tạo và đã rà byte; không đổi global Git config. Commit thành công.|
|Automatic approval review chặn lần push đầu|Không có process push chạy và không dùng đường khác. Sau xác nhận trực tiếp của người dùng, push bình thường thành công; giữ lịch sử chặn.|
|PyMuPDF cảnh báo alias fitz deprecated|Script QA mới dùng pymupdf; chạy lại PASS, không đổi tài liệu.|
|Push in cảnh báo không ghi được `.git/config` cục bộ|Push vẫn exit0 và remote đúng. Đã đọc lại branch.main.remote=origin, branch.main.merge=refs/heads/main; fetch và so SHA/clone mới đều thành công. Không tuyên bố quyền ghi config đã được sửa, không đổi authentication/global config. Cảnh báo này không phải thất bại xác thực.|

## Giới hạn còn giữ

Express/2016 runtime **NOT VERIFIED**; compatibility 130 không thay thế engine thật. Native Word Save/PDF và UI automation còn BLOCKED/NOT VERIFIED theo lịch sử. Metadata ngành/tên pháp nhân/timestamp hoàn tất nguồn thiếu bằng chứng; adjustment và đơn vị quy đổi UNKNOWN; chỉ có snapshot VN30 tháng 06/2026. Quyền phân phối bản ghi nghiên cứu UNKNOWN nên dữ liệu đó không công bố. Bộ public tái hiện demo mô phỏng, không tái hiện toàn bộ nghiên cứu ở mức bản ghi. Không kết luận ưu thế mô hình hoặc hiệu quả đầu tư từ các tổng hợp đã duyệt.

## Tự kiểm lại HEAD hiện hành

```powershell
git status
git log -1 --oneline
git rev-parse HEAD
git fetch origin main
git rev-parse origin/main
git ls-tree -r --name-only HEAD
```

Hai SHA phải bằng nhau sau fetch. Không dùng số 138 hoặc receipt lịch sử để bỏ qua kiểm tra tệp mới ở một commit tương lai. [README](../README.md), [REPORT_WRITING_GUIDE](REPORT_WRITING_GUIDE.md), [SLIDE_BUILD_GUIDE](SLIDE_BUILD_GUIDE.md), [TEAM_HANDOFF](TEAM_HANDOFF.md), [CONTRIBUTING](../CONTRIBUTING.md) là các điểm bắt đầu cho nhóm.
