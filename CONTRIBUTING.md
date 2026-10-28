# Hướng dẫn đóng góp

Đọc [README](README.md) và [TEAM_HANDOFF](docs/TEAM_HANDOFF.md) trước. `main` là bản nhóm dùng để demo; đề nghị thay đổi qua nhánh và pull request. Không có quy tắc bảo vệ branch nào được tự cấu hình trong lần công bố này.

## Quy trình cơ bản

```powershell
git clone https://github.com/nicholas-atptit/bai-tap-lon-csdl-2026.git
cd bai-tap-lon-csdl-2026
git switch main
git pull --ff-only origin main
git switch -c report/bo-sung-thiet-ke
# Sửa file bản làm việc, lưu và kiểm tra.
git status --short
git diff -- docs/REPORT_WRITING_GUIDE.md
git add -- report/team/bao-cao-nhom.md
git diff --cached --stat
git diff --cached
git commit -m "docs: bổ sung phần thiết kế báo cáo"
git push -u origin report/bo-sung-thiet-ke
```

Ví dụ trên chỉ minh họa tên nhánh/file; `git add` phải chỉ đúng file bạn đã tạo/sửa, không dán lệnh cho đường dẫn chưa có. Dùng `slides/...` cho slide, `docs/...` cho hướng dẫn. Không `git add .` khi chưa xem toàn bộ file chưa theo dõi. Nếu chưa có quyền push, dùng Fork trên GitHub rồi mở PR từ fork; không chia sẻ token/mật khẩu.

Trên GitHub: Pull requests → New pull request → base `main`, compare nhánh của bạn → xem Files changed → điền nội dung → Create pull request. Mô tả vấn đề, file đổi, nguồn bằng chứng, cách kiểm và phần chưa xác minh. Nhờ vai trò phụ trách review; technical owner kiểm mọi thay đổi số liệu/schema, người trình bày kiểm lời dẫn và thời gian.

## Bản tham khảo cần review trước khi thay

- `sql/00...12` và `sql/all_in_one.sql`: SQL đã kiểm chứng; giữ nguyên nếu chỉ viết tài liệu.
- `data/sample`: mẫu cố định, không sửa xác suất/giá để tạo kết quả mong muốn.
- `report/MarketLabVN30_Report.*`, `slides/MarketLabVN30_Presentation.*`, `docs/diagrams/marketlab_erd.*`: bản đã duyệt, hash gốc ở [source lineage](docs/SOURCE_LINEAGE.csv).
- `tests/reference_evidence`, `tests/publication_evidence`: bằng chứng của các lần đã chạy; không sửa log cũ thành PASS mới.

Tạo `report/team/` hoặc `slides/team/` khi thật sự có bản làm việc, không tạo thư mục rỗng. Không có sẵn tên thành viên hoặc phân công cá nhân; nhóm tự xác nhận.

## Kiểm tra trước commit/PR

1. Dẫn đúng file/commit và gắn nhãn SYNTHETIC hay nghiên cứu riêng. Không bịa kết quả/ảnh/citation hoặc đổi BLOCKED thành PASS.
2. Kiểm tiếng Việt, Markdown links, bảng/hình và bản PDF xuất từ file bạn sửa. Xem tất cả trang/slide; không chỉ đếm trang.
3. Chạy unit tests và check_publication khi thay mã/hướng dẫn. Nếu thay SQL, technical owner review và chạy hồi quy đúng phạm vi, giữ log thất bại.
4. Repo dùng allowlist cụ thể [PUBLICATION_ALLOWLIST.json](docs/PUBLICATION_ALLOWLIST.json). File thêm mới chưa có allowlist phải được review rồi cập nhật phân loại/hashes, không tắt gate. Hash của bản đã đổi cần được cập nhật từ byte đã review; log/receipt lịch sử không cập nhật theo.
5. Không commit `.env`, token, mật khẩu, dữ liệu/ngành/timestamp tự điền, record nghiên cứu, private manifests, backup DB, caches/Office temp hoặc ZIP không cần thiết. `.gitignore` chỉ hỗ trợ, không thay đọc staged files.

## Review công việc của nhau

Mở PR → Files changed; kiểm logic, nguồn, nhãn phạm vi và link. Với DOCX/PPTX, tải file trong PR để mở, đọc PDF đồng hành, đối chiếu nguồn text/notes; Git không cho review binary như diff text. Để comment cụ thể theo mục/slide. Chỉ merge sau khi giải quyết ý kiến; cập nhật local main bằng `git pull --ff-only` sau merge. Không force push hoặc viết lại lịch sử main.

## Xử lý xung đột đơn giản

Lưu/commit công việc hiện tại trước. Trên nhánh của bạn:

```powershell
git fetch origin
git merge origin/main
git status
```

Với file Markdown có conflict: mở file, đọc hai phía giữa `<<<<<<<`, `=======`, `>>>>>>>`, thống nhất nội dung có bằng chứng rồi xóa marker, lưu, đọc lại toàn mục. `git add -- <file-da-sua>` rồi `git commit` và push nhánh thường. Không giữ hai số liệu mâu thuẫn để “giữ cả hai”. Nếu chưa rõ, `git merge --abort` khi merge đang dở để trở lại trạng thái trước merge, rồi nhờ technical owner; không dùng reset/hard hoặc xóa file.

DOCX/PPTX/PDF là binary: đừng sửa marker hoặc chọn ours/theirs mù quáng. Hai người trao đổi phiên bản, một người ghép bằng ứng dụng, xuất PDF mới và review; giữ bản còn lại riêng cho tới khi xác nhận. [Hướng dẫn chính thức GitHub](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/resolving-a-merge-conflict-using-the-command-line).

## Checklist cuối cho hai vai trò tài liệu

**Người viết báo cáo:** đề cương và bảng ánh xạ đủ; schema/khóa/3NF đúng; ảnh SSMS thật hoặc placeholder; phân biệt 44 ca/176 lượt và demo/nghiên cứu; tham khảo kiểm được; DOCX/PDF không cắt nội dung; PR nêu bằng chứng.

**Người làm slide:** 14 slide, kế hoạch 10–15 phút gồm 4 phút demo; notes/câu chuyển rõ; trắng–đen, font đọc được; ERD dùng vector/phóng to; không bịa accuracy; rehearsal ghi đúng là đo hay dự kiến; PPTX/PDF đồng bộ; presenter đã review.

## Bản quyền và quyền sử dụng dữ liệu

Dữ liệu thị trường thực tế của dự án được thu thập và truy xuất qua **VNstock**. VNstock là công cụ truy xuất; dữ liệu gốc tiếp tục chịu quyền và điều kiện của các nhà cung cấp hoặc chủ thể quyền bên thứ ba. Việc truy xuất không chuyển quyền sở hữu hoặc quyền phân phối lại dữ liệu nguồn cho dự án.

Kết quả dự báo, phân tích và tài sản nghiên cứu được ghi nhận trong hoạt động nghiên cứu của **Lương Minh Quân** và **DATCOM Lab**, theo đóng góp và quyền hợp pháp của các bên. Ghi nhận này không khẳng định DATCOM Lab là pháp nhân đồng sở hữu độc quyền mọi tài sản.

Dữ liệu **mô phỏng** trong bộ demo được tạo để phục vụ bài tập lớn, không phải bản ghi thị trường thu thập từ VNstock hoặc kết quả nghiên cứu thực tế. Nhóm được phân công và giảng viên chỉ sử dụng tài liệu được chia sẻ hợp pháp trong phạm vi bài tập/đánh giá; nghiên cứu khác hoặc việc khai thác tài sản hạn chế ngoài phạm vi được ủy quyền cần được cho phép trước bằng email hoặc văn bản từ chủ thể có thẩm quyền. Gửi yêu cầu mà chưa được chấp thuận không tạo sự cho phép.

Xem [LICENSE.md](LICENSE.md) — **MarketLab VN30 — Restricted Research and Academic Use License (2026)**. Đây là giấy phép riêng hạn chế, không phải giấy phép nguồn mở được OSI công nhận. Quyền theo pháp luật, giấy phép có trước, điều kiện bên thứ ba và các quyền áp dụng theo GitHub vẫn được giữ nguyên.

Chỉ đóng góp nội dung bạn có quyền cung cấp và cấp phép trong phạm vi phù hợp. Không thay giấy phép hoặc xóa thông báo của thành phần bên thứ ba; không đưa bộ dữ liệu nghiên cứu hạn chế vào commit, PR hoặc dịch vụ khác.
