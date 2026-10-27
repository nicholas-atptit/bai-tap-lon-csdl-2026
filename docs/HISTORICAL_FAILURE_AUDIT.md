# Kiểm toán lỗi lịch sử — bản công khai

Bản tóm lược từ kiểm toán đã bàn giao ngày 27/10/2026. Toàn bộ log nội bộ và snapshot gốc được giữ cục bộ, không đưa lên repository công khai. Không xóa hoặc chuyển trạng thái các blocker vì việc công bố GitHub.

39 vấn đề: 28 vấn đề có từ trước, 11 vấn đề phát hiện/phát sinh trong đợt hoàn thiện; 30 RESOLVED, 9 BLOCKED, 0 OPEN, 0 NOT REPRODUCIBLE.

30 ca SQL âm trong mỗi bộ 44 ca chủ động yêu cầu từ chối đúng lỗi rồi ROLLBACK. Mã 51100 (xung đột nạp) và 51200 (migration mâu thuẫn) là kết quả mong đợi, không phải lỗi bị che.

|Mã|Vấn đề|Nguyên nhân / cách xử lý|Trạng thái cuối|
|---|---|---|---|
|H01|Đọc tiếng Việt sai encoding|Get-Content mặc định đọc UTF-8 bằng encoding không phù hợp. Đọc UTF-8 rõ ràng; mọi nguồn văn bản của pipeline dùng UTF-8.|RESOLVED|
|H02|SQLCMD/SSL/SSPI trong ngữ cảnh hạn chế|Các lần thử trong sandbox không có Windows credentials dùng được; cùng tài khoản cục bộ ngoài ngữ cảnh đó kết nối được. Không suy đoán lỗi cấu hình TLS của server. Dùng Windows Authentication trong ngữ cảnh Windows đã được kiểm chứng; không đổi authentication/server config.|RESOLVED|
|H03|sqlcmd -h và -y 0 xung đột|Hai tùy chọn xuất kết quả không tương thích cùng xuất hiện. Bỏ -h khi dùng -y 0; dùng SELECT scalar JSON.|RESOLVED|
|H04|Fixture rollback bị truncation trước lỗi cần kiểm tra|MarketCode ROLLBACK_TEST dài 13 trong VARCHAR(12); gây 2628 trước xung đột Prediction. Đổi fixture thành ROLLBACK_T; giữ nguyên lỗi 51100 cần kiểm tra.|RESOLVED|
|H05|JSON bị ngắt giữa chuỗi|FOR JSON/sqlcmd chèn newline giữa các chunk; json.loads trên chuỗi chưa ghép bị lỗi. Ghép raw line separators; giữ escape newline trong giá trị; scalar JSON rõ ràng.|RESOLVED|
|H06|Phụ thuộc bộ phận TargetDate trong thiết kế 12 bảng|(RunId,OriginDate) xác định TargetDate nhưng khóa Prediction còn StockId. Tách ForecastOrigin, FK ghép; migration kiểm tra sao chép hai chiều trước bỏ trường lặp.|RESOLVED|
|H07|Style Source Code chưa tồn tại|Truy cập doc.styles[Source Code] trước khi tạo style. Tạo style nếu chưa có trước khi đặt font.|RESOLVED|
|H08|PowerShell chặn cách gọi script trực tiếp|Execution policy hiện hữu chặn invocation trực tiếp. Tài liệu dùng powershell -NoProfile -ExecutionPolicy Bypass -File cho process tin cậy này; không đổi policy máy.|RESOLVED|
|H09|COM 80070520 trong sandbox|COM không có logon session dùng được trong ngữ cảnh hạn chế. Chạy công cụ Office trong session Windows cục bộ; PowerPoint export được. Word được tạo và repaginate trong probe, nhưng lỗi export riêng vẫn BLOCKED.|RESOLVED|
|H10|Word Save trực tiếp lên ổ K|Word báo file permission error; nguyên nhân nội bộ của riêng thao tác Save chưa được chẩn đoán độc lập. Không gộp nó với lỗi khóa Pandoc đã sửa. DOCX bàn giao được Pandoc ghi và kiểm tra. Điều đó không biến thao tác Word Save chưa được kiểm chứng thành PASS.|BLOCKED|
|H11|Word ExportAsFixedFormat không trả về|Word mở và repaginate được nhưng native ExportAsFixedFormat không hoàn tất; nguyên nhân nội bộ cần môi trường/quyền chẩn đoán thêm. Probe bản sao cục bộ read-only có giới hạn 45 giây; dừng đúng worker/Word của probe; PDF bàn giao dùng cùng nguồn Markdown qua Edge.|BLOCKED|
|H12|UI app approval hết hạn|App approval cho kiểm tra cửa sổ Word không hoàn tất trước timeout. Không diễn giải thành lệnh từ chối vĩnh viễn. Không bỏ qua permission; chuẩn bị hướng dẫn SSMS chính xác và kiểm thử SQL bằng sqlcmd theo mục tiêu.|BLOCKED|
|H13|Edge headless không in PDF trong sandbox|Lần chạy trong ngữ cảnh hạn chế không tạo được PDF; không có bằng chứng để quy cho một cấu hình server cụ thể. Chạy renderer cục bộ ngoài ngữ cảnh hạn chế, cùng HTML/Markdown, không đổi thiết lập máy.|RESOLVED|
|H14|Pandoc bị khóa file DOCX|Word automation còn giữ DOCX sau lần xuất treo. Chỉ dọn process automation do tác vụ tạo; producer DOCX không phụ thuộc Word và probe chỉ mở bản sao.|RESOLVED|
|H15|Python 3.12 tồn tại ở host nhưng không ở sandbox|Hai ngữ cảnh có filesystem/PATH/package khác nhau. Chọn môi trường Python thực sự có PyMuPDF; SQL demo không phụ thuộc Python.|RESOLVED|
|H16|Marshal.GetActiveObject không có trong runtime|Lệnh chẩn đoán dùng API không có trong runtime PowerShell/.NET đang gọi. Công cụ hiện tại không phụ thuộc API này; theo dõi PID riêng của worker và Word mới tạo.|RESOLVED|
|H17|Pandoc --no-highlight bị deprecate|Dùng tham số cũ. Dùng --syntax-highlighting=none.|RESOLVED|
|H18|Pandoc chia thành 15 slide, có trang tiếp nối thừa|Bảng kèm đoạn body tiếp theo tạo slide tiếp nối. Chuyển diễn giải sau bảng sang speaker notes.|RESOLVED|
|H19|Bảng slide xanh và SQL syntax có màu|Theme bảng PowerPoint và syntax highlighting mặc định. Đặt fill/text/border bảng trắng/đen; tắt syntax highlight; CSS mã màu đen.|RESOLVED|
|H20|ERD nhiều khoảng trắng và cạnh khó theo dõi|Khung trục cố định và một số cạnh đi qua box. Cắt khoảng trống theo bounds thực, định tuyến cạnh qua gutter; cung cấp SVG/PDF để phóng to.|RESOLVED|
|H21|Trang cuối PDF chỉ có vài dòng tham khảo|Khối tham khảo tràn sang một trang gần rỗng. Định dạng tham khảo gọn hơn, giữ đủ nội dung.|RESOLVED|
|H22|Chưa kiểm thử binary Express|Ba instance trong registry là Developer; hai instance đang chạy cũng đã xác minh Developer. Không có kết nối Express dùng để kiểm thử. Giữ NOT VERIFIED trong giới hạn; Developer và compatibility 130 được ghi riêng.|BLOCKED|
|H23|Thiếu ngành và tên pháp nhân nguồn|Nguồn không cung cấp metadata đã xác minh. Giữ NULL; chỉ có ngành/công ty mô phỏng trong demo.|BLOCKED|
|H24|Adjustment và đơn vị quy đổi chưa rõ|Không có adjusted_close hoặc bằng chứng adjustment/hệ số VND được xác minh. Giữ SOURCE_CLOSE và UNKNOWN; không tự nhân hệ số.|BLOCKED|
|H25|Không có lịch sử thành phần VN30 đầy đủ|Chỉ có danh sách khóa tháng 06/2026. Khoảng snapshot chỉ 01–30/06/2026; view StudyUniverse cho phạm vi nghiên cứu.|BLOCKED|
|H26|Timestamp hoàn tất run nguồn chưa xác minh|Nguồn không chứng minh thời gian hoàn tất run. CompletedAt để NULL; LoadedAt chỉ là lúc nạp UTC.|BLOCKED|
|H27|Quyền phân phối nguồn chưa rõ|Provider/publication rights UNKNOWN; không suy diễn giấy phép. Whitelist gói nộp chỉ có mô phỏng, mã/tài liệu và tổng hợp.|BLOCKED|
|N01|Verifier coi thiếu JSON là kết quả rỗng|Fallback [] khi không thấy JSON có thể làm thiếu bằng chứng trông như kết quả rỗng. parse_json_output bắt buộc array hợp lệ, lỗi khi mất output.|RESOLVED|
|N02|Verifier không yêu cầu đủ run trong metric output|Chỉ lặp trên các hàng SQL trả về; output rỗng/thiếu run có thể không bị phát hiện. require_run_coverage kiểm tra đầy đủ và không trùng run.|RESOLVED|
|N03|Hợp đồng JSON rỗng gây regression khi siết verifier|Top-level FOR JSON với 0 hàng có thể không phát ra row qua sqlcmd; Industry nghiên cứu thực sự rỗng. SELECT scalar COALESCE((... FOR JSON ...),N[]); thiếu output vẫn fail closed.|RESOLVED|
|N04|Live demo lỗi 1934 QUOTED_IDENTIFIER|XML .value dùng cho danh sách PK yêu cầu QUOTED_IDENTIFIER; mặc định sqlcmd khác SSMS. Script 09/10 đặt QUOTED_IDENTIFIER ON và ANSI_NULLS ON trong session.|RESOLVED|
|N05|Migration tạo ForecastOrigin trước kiểm tra ambiguity|Check ambiguity cũ nằm sau CREATE ForecastOrigin ngoài transaction; có thể để lại table rỗng khi từ chối. Không ghi thành một lỗi runtime đã xảy ra ở production. Kiểm tra ambiguity trước cả CREATE table; vẫn giữ kiểm tra copy trong transaction.|RESOLVED|
|N06|Generator/finalizer cũ có thể ghi đè nội dung đã duyệt|Template cũ ghi lại guide/slide và finalizer cố định số trang/test/gói cũ. Giữ Markdown đã duyệt bằng marker; finalizer mới dựa receipt thực và tạo ZIP tên mới.|RESOLVED|
|S01|Tạo goal khi đã có goal active|create_goal không chấp nhận một goal chưa kết thúc. Đọc và tiếp tục goal hiện hữu, không tạo goal khác.|RESOLVED|
|S02|Cú pháp foreach pipe trong lệnh registry|Pipe đặt trực tiếp sau statement foreach tạo empty pipe element. Thu kết quả vào array rồi ConvertTo-Json.|RESOLVED|
|S03|Encoding console/pipeline làm hỏng tiếng Việt|stdout CP1252 không in được ký tự Việt; pipeline PowerShell sang Python còn chuyển literal tiếng Việt thành dấu hỏi, khiến replace không khớp. Dùng file/apply_patch UTF-8 và assert nội dung artifact; -X utf8 không tự sửa encoding của producer PowerShell.|RESOLVED|
|S04|Raw string registry kết thúc bằng backslash|Raw string Python có backslash cuối trước dấu nháy không hợp lệ. Ghép các thành phần đường dẫn; py_compile trước chạy.|RESOLVED|
|S05|Patch xóa/thêm cùng path bị tool từ chối|apply_patch không chấp nhận hai operation cùng target. Cập nhật guide qua file mới trong workspace rồi thay nội dung đã có backup.|RESOLVED|
|N07|Receipt aliveness cũ không chứng minh helper đã dừng|Một cờ aliveness cũ còn True, không có thời điểm/kiểm tra OS đủ mạnh để dùng làm trạng thái hiện tại. Không suy diễn PID/worker_state là process còn sống. Giữ nguyên receipt cũ; kiểm tra CIM có timestamp và query thành công, xác minh cả hai PID vắng mặt; gate từ chối thiếu bằng chứng hoặc còn process.|RESOLVED|

Bằng chứng công khai: [kết quả hồi quy lịch sử](../tests/reference_evidence/final_regression_summary.json), [44 ca demo](../tests/reference_evidence/44_tests_existing_demo.log), [migration giữ dữ liệu](../tests/reference_evidence/migration_lossless.log), [từ chối migration mâu thuẫn](../tests/reference_evidence/expected_migration_refusal.log). Lượt kiểm chứng công bố được ghi riêng, không cộng dồn thành số ca độc lập mới.
