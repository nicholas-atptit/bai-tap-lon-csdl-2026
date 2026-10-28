# Hướng dẫn chuẩn bị PowerPoint MarketLab VN30

Đọc bản tham khảo [PPTX](../slides/MarketLabVN30_Presentation.pptx), [PDF](../slides/MarketLabVN30_Presentation.pdf) và [Markdown có notes](../slides/MarketLabVN30_Presentation.md). Deck đã duyệt có **14 slide**; giữ thứ tự đang có, demo ở slide 13. Đề cương gợi ý không phải lý do viết lại deck. Tạo nhánh `slides/<chu-de>` và bản làm việc trong `slides/team/`; chỉ thay bản tham khảo sau review.

Mục tiêu **13 phút 45 giây**, gồm **4 phút demo**; đây là kế hoạch, chưa phải thời gian rehearsal đo thực tế. Không tự điền tên thành viên, lớp hoặc giảng viên. Nội dung nghiên cứu trên slide 3/11 chỉ là tổng hợp đã duyệt; SQL trực tiếp chạy bằng dữ liệu mô phỏng.

## Slide 1 — MARKETLAB VN30

- **Thông điệp:** bài tập thiết kế CSDL quản lý thị trường và dự báo có sẵn.
- **Nội dung:** tên đề tài, học phần, thông tin nhóm đã được xác nhận.
- **Hình/bố cục:** trang bìa trắng–đen, ít chữ, không cần ảnh trang trí tài chính.
- **Nguồn:** [PROJECT_OVERVIEW](PROJECT_OVERVIEW.md), trang bìa deck gốc.
- **Thời gian:** 20 giây.
- **Speaker notes:** giới thiệu trọng tâm 3NF, ràng buộc, truy vấn và transaction; không nói hệ thống huấn luyện AI.
- **Chuyển ý:** “Dữ liệu giá và dự báo rời rạc gây ra những vấn đề nào?”

## Slide 2 — Bài toán

- **Thông điệp:** cần ghép đúng nguồn, mã và thời điểm, chỉ chấm khi đủ dữ liệu.
- **Nội dung:** nguy cơ trùng khóa, ghép sai ngày, thiếu giá mục tiêu; mục tiêu toàn vẹn và SQL dùng lại được.
- **Hình/bố cục:** ba khối giá → dự báo → đánh giá, ghi rõ đây là sơ đồ luồng do nhóm vẽ.
- **Nguồn:** [REQUIREMENTS](REQUIREMENTS.md), [báo cáo §1–2](../report/MarketLabVN30_Report.md).
- **Thời gian:** 40 giây.
- **Speaker notes:** dự báo chưa trưởng thành chưa có nhãn thực; CSDL tiếp nhận forecast, không tạo forecast và không cần website.
- **Chuyển ý:** “Phạm vi dữ liệu được tách thành hai phần rõ ràng.”

## Slide 3 — Phạm vi và dữ liệu

- **Thông điệp:** nghiên cứu riêng và demo công khai có phạm vi khác nhau.
- **Nội dung:** nghiên cứu tổng hợp 30 mã/40 phiên/1.200 giá/1.200 dự báo; demo 8 mã/280 giá/258 dự báo. Ghi retrospective và snapshot 06/2026.
- **Hình/bố cục:** bảng hai cột “NGHIÊN CỨU RIÊNG” / “MÔ PHỎNG DEMO”, hoặc phân biệt bằng notes nếu giữ slide gốc.
- **Nguồn:** [DATA_INVENTORY](DATA_INVENTORY.md), [sample README](../data/sample/README.md), slide 3 gốc.
- **Thời gian:** 45 giây.
- **Speaker notes:** bản ghi nghiên cứu không công bố vì quyền chưa rõ; live chạy mẫu có nhãn. Snapshot không chứng minh thành phần VN30 năm 2025.
- **Chuyển ý:** “Từ phạm vi đó, hệ thống cần những chức năng nào?”

## Slide 4 — Chức năng hệ thống

- **Thông điệp:** ba nhóm nghiệp vụ dẫn đến 13 bảng.
- **Nội dung:** danh mục/chỉ số; giá/lịch; mô hình/run/dự báo; tra cứu và đánh giá. Đặt luồng nạp → kiểm tra → truy vấn.
- **Hình/bố cục:** sơ đồ overview ba nhóm, không thêm màn hình hoặc dashboard chưa xây.
- **Nguồn:** [PROJECT_OVERVIEW](PROJECT_OVERVIEW.md), [DATABASE_DESIGN](DATABASE_DESIGN.md).
- **Thời gian:** 40 giây.
- **Speaker notes:** kể đường đi từ ModelRun đến Prediction và tập chấm; giới thiệu vai trò thực thể thay vì đọc cả 13 tên.
- **Chuyển ý:** “Các nhóm liên kết bằng khóa như sơ đồ sau.”

## Slide 5 — ERD: 13 bảng liên kết

- **Thông điệp:** quan hệ giữ đúng nguồn, lịch và lần chạy.
- **Nội dung:** 13 thực thể, 16 FK; Industry tùy chọn; IndexMembership giải N–N; FK ghép Prediction → ForecastOrigin.
- **Hình/bố cục:** [ERD SVG](diagrams/marketlab_erd.svg) hoặc [PDF](diagrams/marketlab_erd.pdf); phóng to nhóm forecast khi chữ nhỏ.
- **Nguồn:** [01](../sql/01_create_tables.sql), [từ điển](DATA_DICTIONARY.md), [catalog FK](../tests/reference_evidence/schema_foreign_keys.json).
- **Thời gian:** 60 giây.
- **Speaker notes:** chỉ DailyPrice → TradingDay; PK DailyPrice là (DatasetId,StockId,TradeDate). Không dùng ERD 12 bảng cũ làm thiết kế cuối.
- **Chuyển ý:** “Vì sao cần ForecastOrigin thay vì lưu TargetDate trong Prediction?”

## Slide 6 — Vì sao tách ForecastOrigin?

- **Thông điệp:** loại phụ thuộc bộ phận để đạt 2NF và hoàn thiện 3NF.
- **Nội dung:** khóa Prediction gồm run/mã/ngày gốc, nhưng run/ngày gốc xác định ngày mục tiêu; tách rồi JOIN không mất thông tin. Nhắc 1NF nguyên tử, 3NF không lưu lặp tên/ngữ nghĩa.
- **Hình/bố cục:** hai lược đồ trước/sau, gạch chân phần khóa xác định TargetDate; ghi thiết kế cũ là lịch sử.
- **Nguồn:** [NORMALIZATION](NORMALIZATION.md), [migration](../tests/reference_evidence/migration_lossless.log).
- **Thời gian:** 45 giây.
- **Speaker notes:** một run/ngày có nhiều mã nhưng cùng ngày mục tiêu; migration giữ 258 dự báo và LoadedAt. FK tới PK giúp JOIN không nhân hàng.
- **Chuyển ý:** “Ngoài chuẩn hóa, dữ liệu nhập sai còn được chặn trực tiếp.”

## Slide 7 — Kiểu dữ liệu và toàn vẹn

- **Thông điệp:** PK/FK/CHECK và trigger bảo vệ các quy tắc khác nhau.
- **Nội dung:** DECIMAL cho giá/xác suất, BIGINT cho Volume; PK/FK/UNIQUE/NOT NULL/DEFAULT/CHECK; trigger cho horizon, overlap và phạm vi.
- **Hình/bố cục:** bảng quy tắc → cơ chế; ảnh S06 thật nếu đã chụp, có thể để ảnh cho phần demo.
- **Nguồn:** [01](../sql/01_create_tables.sql), [02](../sql/02_constraints_indexes.sql), DATA_DICTIONARY.
- **Thời gian:** 45 giây.
- **Speaker notes:** Volume ≥0 dùng CHECK; cùng thị trường và đúng horizon là quy tắc liên bảng. Không nói mọi quy tắc đều do CHECK thực hiện.
- **Chuyển ý:** “Khi nạp lại, hệ thống cũng phải giữ nhất quán.”

## Slide 8 — Nhập dữ liệu có thể chạy lại

- **Thông điệp:** trùng giống nhau được bỏ qua; xung đột không âm thầm ghi đè.
- **Nội dung:** cùng khóa/cùng giá trị → bỏ qua; khác giá trị → lỗi 51100 và ROLLBACK cả batch; mẫu đã nhúng trong SQL.
- **Hình/bố cục:** flowchart ngắn hoặc receipt RowsInput/RowsInserted từ log mô phỏng.
- **Nguồn:** [import_data.py](../scripts/import_data.py), [03](../sql/03_insert_sample_data.sql), [expected conflict](../tests/reference_evidence/expected_import_conflict_demo.log).
- **Thời gian:** 40 giây.
- **Speaker notes:** batch 200 hàng, transaction bảo vệ cả lần nạp. Public renderer chỉ tạo SQL từ mẫu; không tuyên bố toàn pipeline riêng có trong repo.
- **Chuyển ý:** “Dữ liệu được dùng để trả lời 16 câu hỏi nghiệp vụ.”

## Slide 9 — Truy vấn tiêu biểu

- **Thông điệp:** mỗi phép SQL phục vụ một câu hỏi cụ thể.
- **Nội dung:** Q02 JOIN, Q06 HAVING, Q07 subquery; FULL JOIN/EXCEPT đối chiếu phạm vi. Không dán cả 16 khối SQL lên slide.
- **Hình/bố cục:** đoạn SQL 5–8 dòng hoặc ảnh S04 thật, kèm mục đích/kết quả.
- **Nguồn:** [07](../sql/07_business_queries.sql), [BUSINESS_QUERIES](BUSINESS_QUERIES.md), log query mô phỏng.
- **Thời gian:** 40 giây.
- **Speaker notes:** giải thích WHERE khác HAVING; subquery cùng dataset/mã; truy vấn phát hiện thiếu có 0 hàng vẫn có thể đúng.
- **Chuyển ý:** “Logic dùng nhiều lần được đóng gói thành thủ tục, hàm và view.”

## Slide 10 — Thủ tục, hàm và view

- **Thông điệp:** 4 thủ tục, 3 hàm, 4 view tách logic ghi, tính và đọc.
- **Nội dung:** InsertDailyPrice/AddPrediction; GetModelPerformance/CompareModels; các hàm và view đã có. Nhấn mạnh EligiblePredictions.
- **Hình/bố cục:** bảng ba nhóm, ảnh S05 thật nếu có; không đọc mọi tham số.
- **Nguồn:** [04](../sql/04_functions.sql), [05](../sql/05_views.sql), [06](../sql/06_stored_procedures.sql).
- **Thời gian:** 45 giây.
- **Speaker notes:** cần hai giá và TargetDate ≤ AsOfDate/ObservedThrough. Nhãn thực bằng 1 khi tăng nghiêm ngặt; hàm so ba dấu không thay nhãn nhị phân.
- **Chuyển ý:** “So sánh các run còn cần đúng giao quan sát.”

## Slide 11 — So sánh công bằng trên tập con

- **Thông điệp:** common support tránh so hai tập khác nhau; kết quả chỉ mô tả nghiên cứu riêng.
- **Nội dung:** giữ bảng đã duyệt: 600/600 quan sát; Accuracy 0,580000/0,568333; Brier 0,247666/0,252362; log loss 0,688478/0,698052 cho baseline/logistic. Gắn nhãn retrospective.
- **Hình/bố cục:** bảng trắng–đen trong deck gốc; không dùng màu để gợi ý mô hình “thắng”.
- **Nguồn:** [báo cáo đã duyệt](../report/MarketLabVN30_Report.md), [slide gốc](../slides/MarketLabVN30_Presentation.md), procedure CompareModels trong 06.
- **Thời gian:** 45 giây.
- **Speaker notes:** số liệu lịch sử đã đối chiếu SQL/Python, không chứng minh ưu thế thống kê/hiệu quả đầu tư. Live sẽ có 128 quan sát/run mô phỏng. Muốn bỏ bảng nghiên cứu phải review; không thay bằng số demo rồi vẫn gọi là thật.
- **Chuyển ý:** “Độ đúng của CSDL được kiểm bằng các ca sau.”

## Slide 12 — Kiểm thử thực tế

- **Thông điệp:** kết quả phải có đúng phạm vi, ca âm và kiểm tra rollback.
- **Nội dung:** 44 ca ×4 DB =176 lượt lịch sử; 64 lượt query; migration 12→13; invariance 13 bảng; engine Developer, Express chưa kiểm.
- **Hình/bố cục:** bảng phép kiểm/kỳ vọng/bằng chứng; ảnh S08 thật nếu có.
- **Nguồn:** [tests/README](../tests/README.md), [summary lịch sử](../tests/reference_evidence/final_regression_summary.json), [PUBLICATION_AUDIT](PUBLICATION_AUDIT.md), [08](../sql/08_validation_tests.sql).
- **Thời gian:** 45 giây.
- **Speaker notes:** 44 ca khác nhau, không phải 176 ca độc lập. Lỗi dự kiến 547 không phải FAIL; còn 9 blocker lịch sử. Chưa kiểm tải lớn.
- **Chuyển ý:** “Sau đây là khoảng 4 phút chạy SQL trên dữ liệu mô phỏng.”

## Slide 13 — Demo trực tiếp

- **Thông điệp:** chứng minh hành vi thật, kết thúc không đổi dữ liệu.
- **Nội dung:** chuyển sang SSMS, preflight đã chạy trước giờ; F5 cả file 09. Năm nhóm: PK/FK; JOIN/HAVING/subquery; procedure/functions; CHECK; ROLLBACK.
- **Hình/bố cục:** SSMS thật; backup bằng log được gắn nhãn lịch sử, không giả ảnh hoặc live PASS.
- **Nguồn:** [DEMO_GUIDE](DEMO_GUIDE.md), [10](../sql/10_preflight_live.sql), [09](../sql/09_live_demo.sql).
- **Thời gian:** 240 giây.
- **Speaker notes:** theo mốc 0:00–0:40 / 0:40–1:30 / 1:30–2:10 / 2:10–2:50 / 2:50–3:50; 10 giây để quay về slide. Chỉ đúng lỗi 547/constraint; V,V+1,V; hash trước=sau, transaction0. Phần 4–5 chạy cùng file.
- **Chuyển ý:** “Demo xác nhận các quy tắc, đồng thời kết luận phải giữ các giới hạn.”

## Slide 14 — Kết quả, giới hạn và Q&A

- **Thông điệp:** hoàn thành bài tập CSDL trong phạm vi đã kiểm, còn giới hạn nguồn/môi trường.
- **Nội dung:** 3NF, SQL độc lập, test/demo; metadata NULL, adjustment UNKNOWN, snapshot và rights; link repo/Q&A.
- **Hình/bố cục:** hai cột kết quả/giới hạn, URL đọc được; không cần QR nếu chưa thử.
- **Nguồn:** [HISTORICAL_FAILURE_AUDIT](HISTORICAL_FAILURE_AUDIT.md), [DEFENSE_QA](DEFENSE_QA.md), README.
- **Thời gian:** 35 giây.
- **Speaker notes:** bộ công khai tái hiện demo; nghiên cứu giữ riêng. Hướng mở rộng là metadata có nguồn và thử engine khác, không thêm accuracy mới.
- **Chuyển ý:** mời câu hỏi, mở ERD/SQL phù hợp thay vì đoán câu trả lời.

## Checklist ảnh cần tự chụp

Dùng S01–S08 trong [REPORT_WRITING_GUIDE](REPORT_WRITING_GUIDE.md): môi trường; PK/FK; preflight; query; procedure/functions; CHECK; ROLLBACK; 44 tests. Mỗi ảnh ghi database=SYNTHETIC, ngày, file SQL; không chụp dữ liệu nghiên cứu hoặc credentials.

**[CAPTURE SSMS SCREENSHOT HERE]** — giữ placeholder đến khi có ảnh thật. Không vẽ cửa sổ SSMS, không gọi contact sheet PDF/log sqlcmd là screenshot SSMS. Cắt ảnh phải giữ câu lệnh và output đủ hiểu; ghi caption nếu có cắt/che định danh.

## Bố cục, font và notes

- Nền trắng, chữ đen; dùng độ đậm và nét để phân biệt, không cần gradient.
- Gợi ý title 28–32 pt, body 22–26 pt, caption 18–20 pt; code 18–20 pt nếu ít dòng. Không thu ERD đến mức không đọc được; dùng vector/phóng to.
- Mỗi slide một thông điệp, khoảng 3–5 ý. Bảng có đơn vị, phạm vi và nguồn ngay trên slide; tên SQL giữ đúng chính tả.
- Notes chứa lời giải thích, câu chuyển, giới hạn và thời gian. Không nhồi notes lên canvas. Một người chỉnh PPTX mỗi lượt để tránh conflict binary.
- Xuất PDF từ PPTX làm việc bằng PowerPoint, rà cả 14 trang ở chế độ toàn màn hình, gồm tiếng Việt, ERD, bảng. Không ghi đè bản đã duyệt trước review.
- Thời gian từng slide: 20,40,45,40,60,45,45,40,40,45,45,45,240,35 giây =825 giây. Rehearsal có bấm giờ; nếu chưa đo thì ghi “dự kiến”. Nếu Q&A nằm trong giới hạn 15 phút, rút phần đọc chữ, thống nhất lại kế hoạch.

## Các câu hỏi thường gặp

Chuẩn bị từ [30 Q&A](DEFENSE_QA.md): vì sao 13 bảng; phụ thuộc bộ phận TargetDate; PK DailyPrice/FK ghép; CHECK khác trigger; WHERE/HAVING; transaction/savepoint/ROLLBACK; thiếu endpoint; common observations; demo/thật; latest/snapshot; vì sao không kết luận mô hình tốt hơn; Express đã chạy chưa. Trả lời ngắn rồi chỉ đúng SQL object/ERD/log.

## Dự phòng khi live SQL lỗi

1. Trước giờ chạy 10 rồi 09 trên đúng máy, lưu output mới riêng; mở sẵn SSMS và PDF. Kiểm tra instance, Windows Auth, zoom và máy chiếu.
2. Nếu lỗi kết nối, dành tối đa 30 giây xác định và giữ Messages. Không cài SQL, đổi cấu hình, reset DB hoặc tắt constraint trước lớp.
3. Dùng [preflight log](../tests/reference_evidence/10_preflight.log), [demo log](../tests/reference_evidence/09_live_demo.log), [44 tests](../tests/reference_evidence/44_tests_existing_demo.log). Nói rõ “đây là kết quả lần trước; live trên máy này chưa xác minh”.
4. Giải thích quy tắc qua SQL/ERD trong thời gian còn lại. Gửi lỗi thật cho technical owner sau buổi; giữ FAIL/NOT VERIFIED đúng phạm vi.

## Checklist gửi PR

Đúng 14 slide, kế hoạch 10–15 phút gồm 4 phút demo; số liệu đúng phạm vi và có nguồn; ảnh thật hoặc placeholder; trắng–đen, không cắt chữ, ERD đọc được; notes/câu chuyển đủ; PPTX/PDF cùng revision; rehearsal có ghi đúng trạng thái. Không sửa SQL/metrics. Technical owner và presenter review theo [CONTRIBUTING](../CONTRIBUTING.md).

## Bản quyền và quyền sử dụng dữ liệu

Dữ liệu thị trường thực tế của dự án được thu thập và truy xuất qua **VNstock**. VNstock là công cụ truy xuất; dữ liệu gốc tiếp tục chịu quyền và điều kiện của các nhà cung cấp hoặc chủ thể quyền bên thứ ba. Việc truy xuất không chuyển quyền sở hữu hoặc quyền phân phối lại dữ liệu nguồn cho dự án.

Kết quả dự báo, phân tích và tài sản nghiên cứu được ghi nhận trong hoạt động nghiên cứu của **Lương Minh Quân** và **DATCOM Lab**, theo đóng góp và quyền hợp pháp của các bên. Ghi nhận này không khẳng định DATCOM Lab là pháp nhân đồng sở hữu độc quyền mọi tài sản.

Dữ liệu **mô phỏng** trong bộ demo được tạo để phục vụ bài tập lớn, không phải bản ghi thị trường thu thập từ VNstock hoặc kết quả nghiên cứu thực tế. Nhóm được phân công và giảng viên chỉ sử dụng tài liệu được chia sẻ hợp pháp trong phạm vi bài tập/đánh giá; nghiên cứu khác hoặc việc khai thác tài sản hạn chế ngoài phạm vi được ủy quyền cần được cho phép trước bằng email hoặc văn bản từ chủ thể có thẩm quyền. Gửi yêu cầu mà chưa được chấp thuận không tạo sự cho phép.

Xem [LICENSE.md](../LICENSE.md) — **MarketLab VN30 — Restricted Research and Academic Use License (2026)**. Đây là giấy phép riêng hạn chế, không phải giấy phép nguồn mở được OSI công nhận. Quyền theo pháp luật, giấy phép có trước, điều kiện bên thứ ba và các quyền áp dụng theo GitHub vẫn được giữ nguyên.

Khi chuẩn bị slide, dùng hình, bảng và kết quả đã được phép chia sẻ; giữ nhãn dữ liệu mô phỏng/nghiên cứu cùng ghi nhận nguồn. Không tải bản ghi nghiên cứu hạn chế lên công cụ trình chiếu hoặc dịch vụ khác khi chưa được cho phép.
