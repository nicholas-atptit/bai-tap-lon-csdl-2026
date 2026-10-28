# Bàn giao nhóm MarketLab VN30

Repository: [nicholas-atptit/bai-tap-lon-csdl-2026](https://github.com/nicholas-atptit/bai-tap-lon-csdl-2026), nhánh `main`. Bộ này chạy demo SQL độc lập; bản ghi nghiên cứu riêng không được đưa vào repository. Không gán tên hoặc vai trò cho cá nhân khi chưa được nhóm xác nhận.

## Bốn vai trò và đầu ra

|Vai trò|Cần làm|Đầu ra / người review|
|---|---|---|
|Database / technical owner|Giữ SQL/ERD/khóa nhất quán; giải thích 3NF; kiểm thay đổi có ảnh hưởng đến dữ liệu hoặc kết quả; chạy hồi quy demo có log|Review kỹ thuật cho báo cáo/slide; log test riêng; không sửa bằng chứng lịch sử|
|Người viết báo cáo|Đọc hướng dẫn 22 mục, triển khai lập luận theo source/evidence; chụp ảnh SSMS đúng phạm vi hoặc giữ placeholder; xuất bản DOCX/PDF làm việc|PR `report/...`; technical owner review nội dung, presenter kiểm khả năng giải thích|
|Người làm slide|Dùng deck 14 slide đã duyệt làm tham khảo; chỉnh notes/hình/bố cục khi cần; phân biệt nghiên cứu và demo; xuất PPTX/PDF và tập bấm giờ|PR `slides/...`; technical owner kiểm số liệu, presenter duyệt kịch bản|
|Người trình bày / tester|Chạy preflight trên máy trình bày; tập 5 nhóm demo; chuẩn bị Q&A/backup; ghi PASS/FAIL/BLOCKED/NOT VERIFIED đúng phạm vi|Checklist rehearsal và log mới; góp ý PR tài liệu, không sửa metrics để khớp lời nói|

## 30 phút đầu cho người mới

1. Clone bằng lệnh trong [CONTRIBUTING](../CONTRIBUTING.md). Nếu chỉ cần đọc, mở README trên GitHub hoặc tải DOCX/PPTX bằng nút Download raw file.
2. Đọc [PROJECT_OVERVIEW](PROJECT_OVERVIEW.md), [DATABASE_DESIGN](DATABASE_DESIGN.md), [NORMALIZATION](NORMALIZATION.md). Mở [ERD PDF](diagrams/marketlab_erd.pdf), tìm DailyPrice và ForecastOrigin/Prediction.
3. Đọc [INSTALLATION_GUIDE](INSTALLATION_GUIDE.md), chạy demo trên SQL Server được phép. SQL đã nằm trong [all_in_one](../sql/all_in_one.sql); không cần nguồn K của tác giả.
4. Người viết báo cáo đọc [REPORT_WRITING_GUIDE](REPORT_WRITING_GUIDE.md), người làm slide đọc [SLIDE_BUILD_GUIDE](SLIDE_BUILD_GUIDE.md). Mở bản tham khảo ở report/ hoặc slides/ để đối chiếu.
5. Người trình bày đọc [DEMO_GUIDE](DEMO_GUIDE.md) và [30 câu Q&A](DEFENSE_QA.md). Technical owner đọc [tests/README](../tests/README.md) và [PUBLICATION_AUDIT](PUBLICATION_AUDIT.md).

## Tìm file theo công việc

|Cần tìm|Nơi đọc|
|---|---|
|Schema/khóa/constraint|sql/01_create_tables.sql, 02_constraints_indexes.sql; DATA_DICTIONARY|
|16 truy vấn|sql/07_business_queries.sql; BUSINESS_QUERIES|
|4 SP / 3 hàm / 4 views|sql/06 / 04 / 05|
|Demo và kiểm trước demo|sql/09_live_demo.sql, 10_preflight_live.sql; DEMO_GUIDE|
|Mẫu công khai|data/sample/; data/manifests/demo_manifest.json|
|Bằng chứng cũ / mới|tests/reference_evidence/ / tests/publication_evidence/; phân biệt ngày và scope|
|Bản báo cáo / slide đã duyệt|report/MarketLabVN30_Report.* / slides/MarketLabVN30_Presentation.*|
|Lỗi còn giữ hiển thị|HISTORICAL_FAILURE_AUDIT; PUBLICATION_AUDIT|

## Cách sửa và nộp

Dùng nhánh `report/<chu-de>`, `slides/<chu-de>`, `docs/<chu-de>`. Tạo bản làm việc riêng trong `report/team/` hoặc `slides/team/`; chỉ tạo thư mục khi có nội dung. Không cùng sửa một PPTX/DOCX ở hai nhánh mà chưa hẹn người ghép. Sửa Markdown có diff dễ review hơn, nhưng không bắt buộc chuyển Word của bạn sang Markdown.

Đọc `git status`, chọn đúng file bằng `git add -- <duong-dan>`, đọc `git diff --cached`/`--stat`, commit có ý nghĩa rồi `git push -u origin <ten-nhanh>`. Mở Pull request vào main, nêu mục/slide đã đổi, nguồn, ảnh còn thiếu và cách kiểm. Hướng dẫn từng lệnh, quyền push/fork, review và xử lý conflict ở [CONTRIBUTING](../CONTRIBUTING.md). Không push thẳng main để bỏ qua review của nhóm; đây là quy ước, không tuyên bố repository đã bật protection.

Bản đã duyệt khóa theo hash trong [SOURCE_LINEAGE](SOURCE_LINEAGE.csv). Không đổi SQL, sample, kết quả cũ, ERD hoặc bản tham khảo chỉ để khớp ý viết mới. Khi thực sự cần sửa, PR giải thích và có bằng chứng; technical owner quyết định sau review. Không xóa log lỗi hoặc reset DB.

## Checklist nghiệm thu nhóm

- Báo cáo: 22 nội dung đã ánh xạ/gộp rõ; đúng 13 bảng, khóa DailyPrice, ForecastOrigin/3NF, CHECK/FK/transaction; citation mở được; hình/bảng đánh số; ảnh SSMS thật hoặc placeholder có nhãn.
- Slide: 14 slide; tổng dự kiến 13:45 gồm demo 4 phút; rehearsal có ghi thời gian thực; chữ/ERD đọc được; notes/câu chuyển; output demo không gọi là kết quả nghiên cứu.
- Kỹ thuật: preflight PASS trên đúng máy hoặc ghi blocker; demo không để transaction mở; giữ số 44 ca khác nhau và 176 lượt lịch sử; không có khẳng định Express đã PASS.
- Công khai: không source record/private manifest/secret/backup; allowlist và link check phù hợp file mới; review staged files thay vì chỉ tin gitignore.
- Bàn giao: bản làm việc + PDF cùng revision, PR và người review rõ; presenter biết file chạy và backup. Các blocker nguồn/Word/Express/UI vẫn được công bố trung thực.

## Tin nhắn có thể gửi nhóm

“Repo bài CSDL: https://github.com/nicholas-atptit/bai-tap-lon-csdl-2026. Mọi người đọc README và docs/TEAM_HANDOFF.md trước. Bạn viết báo cáo làm theo REPORT_WRITING_GUIDE.md, tham khảo DOCX/PDF đã duyệt và tự chụp ảnh SSMS trên dữ liệu mô phỏng. Bạn làm slide đọc SLIDE_BUILD_GUIDE.md, giữ deck 14 slide, chuẩn bị notes và 4 phút demo. Tạo nhánh report/... hoặc slides/..., làm bản riêng rồi mở PR vào main để review; đừng ghi đè bản gốc hoặc đưa dữ liệu nghiên cứu riêng lên repo.”

## Bản quyền và quyền sử dụng dữ liệu

Dữ liệu thị trường thực tế của dự án được thu thập và truy xuất qua **VNstock**. VNstock là công cụ truy xuất; dữ liệu gốc tiếp tục chịu quyền và điều kiện của các nhà cung cấp hoặc chủ thể quyền bên thứ ba. Việc truy xuất không chuyển quyền sở hữu hoặc quyền phân phối lại dữ liệu nguồn cho dự án.

Kết quả dự báo, phân tích và tài sản nghiên cứu được ghi nhận trong hoạt động nghiên cứu của **Lương Minh Quân** và **DATCOM Lab**, theo đóng góp và quyền hợp pháp của các bên. Ghi nhận này không khẳng định DATCOM Lab là pháp nhân đồng sở hữu độc quyền mọi tài sản.

Dữ liệu **mô phỏng** trong bộ demo được tạo để phục vụ bài tập lớn, không phải bản ghi thị trường thu thập từ VNstock hoặc kết quả nghiên cứu thực tế. Nhóm được phân công và giảng viên chỉ sử dụng tài liệu được chia sẻ hợp pháp trong phạm vi bài tập/đánh giá; nghiên cứu khác hoặc việc khai thác tài sản hạn chế ngoài phạm vi được ủy quyền cần được cho phép trước bằng email hoặc văn bản từ chủ thể có thẩm quyền. Gửi yêu cầu mà chưa được chấp thuận không tạo sự cho phép.

Xem [LICENSE.md](../LICENSE.md) — **MarketLab VN30 — Restricted Research and Academic Use License (2026)**. Đây là giấy phép riêng hạn chế, không phải giấy phép nguồn mở được OSI công nhận. Quyền theo pháp luật, giấy phép có trước, điều kiện bên thứ ba và các quyền áp dụng theo GitHub vẫn được giữ nguyên.

Phân công nhóm chỉ cho phép dùng tài liệu hợp pháp trong công việc được giao; không mặc nhiên cho phép chia sẻ tiếp dữ liệu nội bộ hoặc dùng cho một nghiên cứu độc lập khác.
