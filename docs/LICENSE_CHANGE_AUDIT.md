# Kiểm toán thay đổi giấy phép — 28/10/2026

## Cơ sở GitHub đã đồng bộ

- Repository: [nicholas-atptit/bai-tap-lon-csdl-2026](https://github.com/nicholas-atptit/bai-tap-lon-csdl-2026), branch `main`.
- Commit cơ sở mới nhất đã fetch và pull fast-forward trước khi sửa: `74ee3f640296bb9360daa5739f1c4e322a48ad72`.
- Working tree ban đầu sạch. Remote có các commit mới so với bản công bố trước, trong đó đã có LICENSE.md do tác giả thêm; không dùng bản cũ để ghi đè chúng.
- Bản gốc `MarketLabVN30` không có Git; làm việc trên clone công bố đã xác minh đúng origin. Không khởi tạo Git hoặc sửa dữ liệu/tài liệu trong bản gốc.

## Tệp được thay đổi

|Tệp|Mục đích|
|---|---|
|[LICENSE.md](../LICENSE.md)|Cập nhật giấy phép hạn chế đã có thành văn bản tiếng Việt, thêm ranh giới quyền và thông báo tiếng Anh ngắn|
|[README.md](../README.md)|Thêm mục bản quyền/nguồn dữ liệu và liên kết giấy phép|
|[CONTRIBUTING.md](../CONTRIBUTING.md)|Thêm điều kiện sử dụng và đóng góp hợp pháp, giữ quyền bên thứ ba|
|[TEAM_HANDOFF.md](TEAM_HANDOFF.md)|Nêu quyền của nhóm bài tập, giảng viên và giới hạn chia sẻ lại|
|[REPORT_WRITING_GUIDE.md](REPORT_WRITING_GUIDE.md)|Hướng dẫn ghi nguồn/đóng góp và không đưa bản ghi hạn chế vào báo cáo|
|[SLIDE_BUILD_GUIDE.md](SLIDE_BUILD_GUIDE.md)|Hướng dẫn ghi nguồn/nhãn mô phỏng và chỉ dùng tài liệu được phép chia sẻ|
|[PUBLICATION_ALLOWLIST.json](PUBLICATION_ALLOWLIST.json)|Cập nhật metadata tài liệu, ghi nhận LICENSE.md đã có trên upstream và audit mới; không đổi script kiểm tra|
|LICENSE_CHANGE_AUDIT.md|Ghi lại phạm vi, căn cứ và kết quả kiểm tra của lần thay đổi này|

Các nội dung có sẵn trong năm tài liệu hướng dẫn được giữ nguyên byte làm tiền tố; chỉ nối mục bản quyền vào cuối. Không khôi phục phần README mà tác giả đã xóa trên GitHub. Allowlist của bản trước chưa liệt kê LICENSE.md mới trên upstream và còn hash README cũ; cập nhật tài liệu kiểm soát này để phản ánh đúng cây công bố hiện tại, không bỏ qua gate. Cây dự kiến có 140 tệp, từ 139 tệp của commit cơ sở cộng audit này.

## Giấy phép trước và phạm vi cập nhật

Đã đọc toàn bộ LICENSE.md tại commit cơ sở: đây đã là giấy phép restricted research/academic, có bảo lưu quyền hợp pháp và quyền bên thứ ba; không phải MIT/Apache/GPL. Không tìm thấy tệp LICENSE/COPYING/NOTICE khác trong cây Git áp dụng một giấy phép mở cho toàn bộ repository. Việc nhắc MIT/Apache/GPL trong văn bản mới là để nói rõ không áp dụng các giấy phép đó, không phải cấp phép theo chúng.

Bản cũ ghi DATCOM Laboratory; bản cập nhật dùng cách ghi DATCOM Lab theo chỉ dẫn tác giả, không dựa vào tên gọi để xác nhận tư cách pháp nhân hoặc đồng sở hữu độc quyền. Không phát hiện xung đột cấp phép đối với tài liệu gốc trong phạm vi kiểm tra này; điều đó không thay thế hồ sơ xác lập quyền của các bên. Không xóa hoặc cấp phép lại thành phần bên thứ ba, không thu hồi quyền đã được cấp hợp pháp trước đây.

## Điều khoản chính và dữ liệu bên thứ ba

- Ghi nhận Lương Minh Quân thực hiện/phát triển nghiên cứu và DATCOM Lab đồng hành; quyền được bảo lưu theo đóng góp và quyền sở hữu hợp pháp.
- VNstock là công cụ truy xuất. Dữ liệu thị trường gốc thuộc phạm vi quyền/điều kiện của nhà cung cấp hoặc chủ thể quyền liên quan; không khẳng định tác giả hoặc Lab sở hữu độc quyền dữ liệu đó.
- Phân biệt bản ghi thị trường với dữ liệu SYNTHETIC tạo cho bài tập/demo; không công bố dữ liệu nghiên cứu nội bộ.
- Cho phép nhóm được phân công, giảng viên và cộng tác viên có ủy quyền dùng tài liệu được cung cấp hợp pháp đúng phạm vi. Việc nghiên cứu/tái phân phối/thương mại hóa hoặc dùng dự báo hạn chế huấn luyện/đánh giá trong dự án khác cần chấp thuận trước, trừ quyền sử dụng độc lập được bảo lưu.
- Email chính và học thuật theo tác giả cung cấp; phải được trả lời chấp thuận từ người có thẩm quyền. Im lặng hoặc gửi yêu cầu chưa đủ; tài sản nhiều chủ thể cần đúng thẩm quyền/thỏa thuận.
- Không áp điều khoản này lên dữ kiện/phương pháp chung, giấy phép riêng, quyền đã cấp hợp pháp hoặc quyền theo pháp luật/GitHub.

## Nguồn chính thức đã kiểm tra ngày 28/10/2026

- [VNstock LICENSE.md](https://github.com/thinh-vu/vnstock/blob/main/LICENSE.md): phân biệt quyền phần mềm với quyền dữ liệu nguồn; không đưa mã VNstock hoặc giấy phép của họ vào dự án này.
- [Trang giấy phép VNstock](https://www.vnstocks.com/policies/license): tại lúc kiểm tra hiển thị bản 2026.11, công bố 24/10/2026 và hiệu lực 30/11/2026, **chưa tới ngày hiệu lực**. File GitHub của VNstock vẫn nhắc 2026.09. Không suy rằng bản mới tự áp dụng cho phiên bản phần mềm hay dữ liệu nghiên cứu lịch sử; chưa xác minh bản/điều kiện thực sự áp dụng khi thu thập.
- [GitHub Terms of Service, mục D](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service): giữ các quyền áp dụng của dịch vụ, gồm xem/fork; giấy phép riêng không hứa chặn mọi cách sử dụng nội dung đã đăng công khai.

Các liên kết được dùng để kiểm tra ranh giới quyền, không được xem như chứng cứ rằng nhà cung cấp đã cấp quyền phân phối dữ liệu nghiên cứu.

## Quyền sở hữu hoặc điều kiện chưa thể xác minh

**NOT VERIFIED:** tư cách pháp nhân của DATCOM Lab; thỏa thuận đóng góp/chuyển giao/đồng sở hữu cụ thể; tỷ lệ và thẩm quyền cấp phép từng tài sản; danh sách cộng tác viên được ủy quyền; quyền truy xuất/lưu trữ/phân phối theo đúng nhà cung cấp và phiên bản nguồn tại thời điểm nghiên cứu. Ghi nhận tác giả và Lab theo thông tin do tác giả cung cấp, không chế tạo chứng cứ cho các vấn đề này.

**Không cấp quyền phân phối nguồn:** giấy phép dự án không giải quyết thay các quyền bên thứ ba còn UNKNOWN. Dữ liệu nghiên cứu nội bộ tiếp tục được giữ riêng. Nội dung PUBLIC vẫn có thể được truy cập theo quyền GitHub; thông báo hạn chế không biến repository thành nơi bảo mật.

## Kiểm tra an toàn và nội dung không thay đổi

|Kiểm tra|Kết quả thực tế trước commit|
|---|---|
|Phạm vi thay đổi|PASS: đúng 8 tệp giấy phép/tài liệu, không có tệp ngoài phạm vi|
|SQL, scripts, dữ liệu, test/receipt, báo cáo, slide và ERD|PASS: 113 tệp thuộc nhóm bảo vệ khớp SHA-256 với commit GitHub cơ sở|
|Các tệp Git khác không liên quan|PASS: 132 tệp cũ giữ nguyên SHA-256|
|Bản gốc MarketLabVN30|PASS: 1757 tệp giữ nguyên SHA-256, không thêm/xóa tệp|
|Hướng dẫn nhóm|PASS: phần thân trước đây của 5 tài liệu giữ nguyên byte, chỉ nối mục bản quyền|
|Attribution và quyền|PASS trong phạm vi biên tập: chủ thể theo thông tin tác giả, VNstock/công cụ/dữ liệu bên thứ ba/mô phỏng phân biệt rõ; không khẳng định DATCOM Lab là pháp nhân đồng sở hữu độc quyền|
|Giấy phép có trước|PASS kiểm tra phạm vi: chỉ có giấy phép restricted đã nêu, không có MIT/Apache/GPL toàn repo cần xóa; bảo lưu giấy phép riêng và quyền đã cấp hợp pháp|
|Cổng công bố hiện hành|PASS: 140 tệp đúng allowlist, các liên kết nội bộ được kiểm; không sửa script gate|
|Dữ liệu nhạy cảm mới|PASS kiểm tra phạm vi: chỉ 8 tệp text giấy phép/tài liệu được phép thay; không thêm raw/private dataset, backup, token hoặc credentials|
|Quét nội dung|PASS trong phạm vi mẫu kiểm tra: không phát hiện mẫu secret trong văn bản/Office XML được gate rà; các binary không đổi hash. Hai email liên hệ là địa chỉ công khai do tác giả cung cấp, không phải credentials|
|Mâu thuẫn tài liệu|Không phát hiện trong phạm vi đọc LICENSE mới/cũ, README và các thông báo nhóm; các quyền nguồn UNKNOWN và kiểm toán cũ vẫn giữ nguyên|


Không chạy SQL Server, không tạo/reset/xóa database, không sửa schema/script, không huấn luyện mô hình, không thay kết quả nghiên cứu hoặc báo cáo kiểm thử. Không sửa ERD, DOCX, PDF, PPTX hoặc dữ liệu hiện có. Các log/test receipt và kiểm toán công bố cũ vẫn là bằng chứng lịch sử, không được viết lại thành kết quả của lần sửa giấy phép.

Audit này ghi kết quả trước commit. Chỉ báo PUSHED và remote PASS sau khi push thành công, fetch lại và so SHA/nội dung thực tế; receipt đối chiếu commit cuối được lưu riêng trong hồ sơ thao tác cục bộ để tránh tự tham chiếu SHA của chính tệp Git.
