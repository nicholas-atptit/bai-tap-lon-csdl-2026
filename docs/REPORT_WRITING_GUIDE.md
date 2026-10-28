# Hướng dẫn viết báo cáo MarketLab VN30

## Cách sử dụng

Đọc [README](../README.md), [thiết kế](DATABASE_DESIGN.md), [từ điển](DATA_DICTIONARY.md), [chuẩn hóa](NORMALIZATION.md), rồi mở báo cáo đã duyệt [DOCX](../report/MarketLabVN30_Report.docx)/[PDF](../report/MarketLabVN30_Report.pdf). PDF hiện có 9 trang, 16 mục chính. Đề cương 22 mục dưới đây giúp triển khai báo cáo theo mẫu lớp; không phải yêu cầu viết lại bản đã duyệt thành 22 chương hoặc tăng trang tùy ý. Có thể gộp các mục thành tiểu mục. Không thay số liệu hoặc kết quả đã kiểm chứng để phù hợp bố cục.

Tạo nhánh `report/<chu-de>` và bản làm việc `report/team/<ten-phien-ban>.md` hoặc DOCX riêng. Không ghi đè bản tham khảo đã duyệt khi chưa review. Nếu không có mẫu của giảng viên, dùng cách trình bày trắng–đen, tiêu đề thống nhất; đề xuất Times New Roman 12–13 pt, giãn dòng 1,15–1,3 và lề theo mẫu lớp. Đây là đề xuất biên tập, không phải quy định trường đã được xác minh.

## Bảng ánh xạ đề cương → nguồn → bằng chứng → giải thích

|Mục báo cáo|File nguồn chính|Bằng chứng cần có|Giải thích trọng tâm|
|---|---|---|---|
|1. Giới thiệu|[PROJECT_OVERVIEW](PROJECT_OVERVIEW.md), [báo cáo §1](../report/MarketLabVN30_Report.md)|Phát biểu phạm vi thống nhất|CSDL quản lý dự báo có sẵn, không huấn luyện AI|
|2. Bài toán, mục tiêu|[REQUIREMENTS](REQUIREMENTS.md)|Bảng chức năng M01–M07/A01–A06|Vì sao cần khóa, thời gian, nguồn và tính toàn vẹn|
|3. Phạm vi, yêu cầu|[README](../README.md), [DATA_INVENTORY](DATA_INVENTORY.md)|Bảng thật/mô phỏng và giới hạn|Phân biệt điều có trong repo với nghiên cứu riêng|
|4. Phân tích hệ thống|[DATABASE_DESIGN](DATABASE_DESIGN.md)|Sơ đồ luồng nhập–lưu–đánh giá tự vẽ có chú thích|Vai trò dữ liệu và quy tắc nghiệp vụ|
|5. Xác định thực thể|[DATA_DICTIONARY](DATA_DICTIONARY.md)|Bảng 13 thực thể và lý do tồn tại|Không thêm bảng ngoài schema cho đủ số lượng|
|6. ERD|[SVG](diagrams/marketlab_erd.svg), [PDF](diagrams/marketlab_erd.pdf)|Hình toàn cảnh và vùng phóng to|16 FK; Industry tùy chọn; IndexMembership giải N–N|
|7. Lược đồ quan hệ|[01_create_tables](../sql/01_create_tables.sql)|13 quan hệ, khóa gạch chân/ghi rõ|Đọc đúng tên cột và thứ tự khóa|
|8. PK/FK|[schema indexes](../tests/reference_evidence/schema_indexes.json), [FK](../tests/reference_evidence/schema_foreign_keys.json)|Ảnh SSMS PK/FK thực + bảng khóa|Khóa ghép và toàn vẹn tham chiếu|
|9. 1NF/2NF/3NF|[NORMALIZATION](NORMALIZATION.md)|Bảng phụ thuộc hàm + phân rã ForecastOrigin|Phụ thuộc bộ phận thật, JOIN không mất thông tin|
|10. Triển khai SQL Server|[INSTALLATION_GUIDE](INSTALLATION_GUIDE.md), [all_in_one](../sql/all_in_one.sql)|Ảnh server edition + preflight trên máy chạy|Phân biệt engine thực với mục tiêu tương thích|
|11. Kiểu và ràng buộc|[01](../sql/01_create_tables.sql), [02](../sql/02_constraints_indexes.sql)|Bảng kiểu/constraint, lỗi âm đúng tên|DECIMAL, BIGINT, DATE; CHECK và trigger khác vai trò|
|12. Dữ liệu mẫu|[sample](../data/sample/README.md), [manifest](../data/manifests/demo_manifest.json)|Count 13 bảng và dòng DEMO có nhãn|Không dán bản ghi nghiên cứu riêng|
|13. Truy vấn nghiệp vụ|[07](../sql/07_business_queries.sql), [BUSINESS_QUERIES](BUSINESS_QUERIES.md)|Q01–Q16 + mục đích/output thật|JOIN/HAVING/subquery/tập hợp; 0 hàng có thể hợp lệ|
|14. Stored procedures|[06](../sql/06_stored_procedures.sql)|Bảng 4 SP, tham số và một lời gọi thật|Ghi có kiểm soát, savepoint, common support|
|15. Functions|[04](../sql/04_functions.sql)|Bảng 3 hàm + output 100→110, flat, eligible|Nhãn nhị phân khác kiểm tra ba dấu|
|16. Views|[05](../sql/05_views.sql)|Bảng 4 views và SELECT minh họa|Tên snapshot không phải thành phần hiện tại|
|17. Kiểm thử|[08](../sql/08_validation_tests.sql), [tests](../tests/README.md)|44 PASS, hash trước/sau, SQL/Python|44 ca × 4 DB =176 lượt lịch sử, không176 ca độc lập|
|18. Demo trực tiếp|[09](../sql/09_live_demo.sql), [10](../sql/10_preflight_live.sql), [DEMO_GUIDE](DEMO_GUIDE.md)|5 nhóm output, CHECK, ROLLBACK|Đóng transaction và chứng minh dữ liệu không đổi|
|19. Giới hạn|[HISTORICAL_FAILURE_AUDIT](HISTORICAL_FAILURE_AUDIT.md)|Danh sách BLOCKED/NOT VERIFIED nguyên trạng|Express, metadata, rights, Word/UI và phạm vi nghiên cứu|
|20. Kết luận|[PROJECT_OVERVIEW](PROJECT_OVERVIEW.md), bằng chứng §17|Đối chiếu mục tiêu với kết quả thực|Hoàn thành bài tập CSDL, không tuyên bố hiệu quả đầu tư|
|21. Tài liệu tham khảo|[REFERENCES](REFERENCES.md), báo cáo §16|Nguồn chính thức mở được, ngày truy cập|Không bịa DOI, số trang sách hay tài liệu giảng viên|
|22. Phụ lục|[SQL](../sql/all_in_one.sql), [fixtures](../tests/fixtures/legacy12/README.md)|Danh mục script, ảnh thật và log liên quan|Tách nội dung chính khỏi chi tiết có thể kiểm tra|

## Nội dung cần triển khai theo từng mục

### 1. Giới thiệu

Viết 1–2 đoạn về nhu cầu tổ chức dữ liệu theo mã/ngày và đối chiếu dự báo có sẵn. Dùng thuật ngữ nhất quán với README. Hình đề xuất: sơ đồ ba nhóm dữ liệu; bằng chứng là chức năng trong REQUIREMENTS. Tránh nói hệ thống tự sinh forecast, giao dịch tự động hoặc có website.

### 2. Bài toán và mục tiêu

Nêu đầu vào (danh mục, lịch, giá, dự báo/cấu hình) và đầu ra (truy vấn, tập đủ điều kiện, chỉ tiêu). Lập bảng yêu cầu → SQL object từ REQUIREMENTS và 04–06. Bằng chứng cần truy được đến tên object. Tránh viết mục tiêu như “độ chính xác cao” vì đây không phải tiêu chí nghiệm thu CSDL.

### 3. Phạm vi và yêu cầu

Tách hai hàng SYNTHETIC và REAL PRIVATE như DATA_INVENTORY. Repo có 8 mã/280 giá/258 dự báo mô phỏng; nghiên cứu riêng có 30/1.200/1.200, không có file records để bạn tái chạy. Hình/bảng nên ghi nhãn phạm vi ngay trong caption. Không lấy count nghiên cứu làm count database demo.

### 4. Phân tích hệ thống

Mô tả luồng: danh mục và lịch → nạp giá/dự báo → kiểm tra khóa/miền/thời gian → truy vấn → đánh giá. Đối chiếu USP và trigger trong 02/06; thêm bảng input/quy tắc/output. Bằng chứng là quy tắc thực trong SQL. Không thêm người dùng, phân quyền ứng dụng hoặc màn hình chưa xây.

### 5. Xác định 13 thực thể

Giải thích từng bảng theo từ điển, chia ba nhóm. Dataset giữ ngữ nghĩa nguồn; TradingDay tách lịch; TargetDefinition tách mục tiêu; ModelRun tách cấu hình; ForecastOrigin loại phụ thuộc bộ phận; IndexMembership biểu diễn N–N theo hiệu lực. Bảng 13 hàng phải khớp 01/schema_columns. Không gộp Stock với Industry hoặc nhét tên ngành vào Prediction để “đơn giản hóa”.

### 6. ERD

Chèn SVG/PDF vector hoặc PNG có sẵn; đánh số Hình 1, caption “13 thực thể, schema hiện hành”. Giải thích đầu 1/N, FK bắt buộc và IndustryId có thể NULL; phóng to nhóm forecast nếu chữ nhỏ. Nguồn là thư mục diagrams và catalog FK. Không chụp sơ đồ 12 bảng cũ làm ERD cuối; không bịa quan hệ lịch sử VN30.

### 7. Lược đồ quan hệ

Chép tên quan hệ/cột từ 01 và DATA_DICTIONARY, ghi PK, FK, UNIQUE, NULL. Bảng lược đồ nên phân biệt khóa chính với khóa tự nhiên. Bằng chứng là 73 cột catalog. Không suy từ CSV rồi bỏ LoadedAt/default hoặc tự đổi kiểu SQL.

### 8. PK, FK và toàn vẹn tham chiếu

DailyPrice có PK **(DatasetId,StockId,TradeDate)**: cùng cổ phiếu/ngày có thể thuộc nguồn hoặc phiên bản khác. Prediction có PK **(RunId,StockId,OriginDate)**, FK ghép **(RunId,OriginDate)** đến ForecastOrigin; DailyPrice có FK ghép đến TradingDay. Mô tả UNIQUE(MarketId,Ticker), quan hệ Industry tùy chọn và không cascade xóa. Bảng khóa + ảnh catalog SSMS S02 bên dưới là bằng chứng. Tránh nói ticker duy nhất toàn cầu hoặc ForecastOrigin có StockId.

### 9. Chuẩn hóa

1NF: giá trị nguyên tử đúng miền. 2NF: mọi thuộc tính không khóa phụ thuộc toàn khóa ứng viên. Dùng trường hợp thật `(RunId,OriginDate) → TargetDate` trong khóa Prediction lớn hơn để giải thích tách ForecastOrigin, từ 12 thành 13 bảng. 3NF: không lưu ModelName/IndustryName/PriceUnit trong Prediction; suy qua FK. Trình bày JOIN tái tạo TargetDate, FK tới PK bảo đảm tối đa một cha, không nhân forecast. Dùng bảng FD của NORMALIZATION và log migration 258 dòng/LoadedAt. Không dựng một bảng phi chuẩn “đã từng có” khi không có bằng chứng; 3NF phải nêu giả thiết miền của TargetDefinition.

### 10. Triển khai

Mô tả F5 all-in-one hoặc 00–06 đúng thứ tự; chỉ tạo demo khi cần. Chụp edition/version thật S01 và preflight S03, ghi máy/phiên bản/ngày chạy thực. File SQL có chú thích 2016 SP1+/Express là mục tiêu; bằng chứng runtime hiện tại chỉ Developer 2025. Không đánh dấu Express PASS từ compatibility130; không reset database để có ảnh đẹp.

### 11. Kiểu dữ liệu và ràng buộc

Giải thích DECIMAL(19,6) cho giá, DECIMAL(19,16) cho xác suất, BIGINT cho Volume, DATE/DATETIME2(0). FLOAT chỉ dùng phép tính chỉ tiêu. Bảng ràng buộc: PK/FK/UQ/NOT NULL/DEFAULT/CHECK, rồi trigger kiểm tra liên bảng/horizon/overlap/cấu hình đã dùng. Ảnh S06 phải đúng mã547/CK_DailyPrice_Volume. Không gọi CHECK là cơ chế tự kiểm lịch tương lai hoặc bảo đảm dữ liệu nguồn đúng sự thật.

### 12. Dữ liệu mẫu

Nêu 13 bảng count, hai mô hình giả định horizon5 và hai thiếu endpoint. Dùng một vài dòng DEMO khi cần minh họa; đọc sample/tables.json và log synthetic. Không đưa giá, ticker/probability nghiên cứu riêng hoặc private manifest vào phụ lục/ảnh. Không mô tả lịch demo là lịch nghỉ HOSE.

### 13. 16 truy vấn

Mỗi Q gồm yêu cầu, SQL, ý nghĩa output và caption có dataset. Có thể đưa đầy đủ16 ở phụ lục, chọn Q02/Q06/Q07 và một phép tập hợp ở chương chính. Nguồn 07/BUSINESS_QUERIES và query_01–16_synthetic.log. Chụp S04 trên máy chạy thật. Không sửa truy vấn để buộc trả hàng khi câu hỏi phát hiện thiếu dữ liệu đang có0 hàng.

### 14. Bốn thủ tục

Lập bảng tham số/tiền điều kiện/thành công/lỗi cho InsertDailyPrice, AddPrediction, GetModelPerformance, CompareModels. Giải thích AllowUpdate mặc định0; trùng giống bỏ qua, khác giá trị bị từ chối; TRY/CATCH/XACT_ABORT/savepoint. CompareModels đòi cùng dataset/target và giao khóa trưởng thành. Hình S05 là output thực. Không nói thủ tục đánh giá tự huấn luyện hoặc hai run có số count bằng nhau nghĩa là cùng observation.

### 15. Ba hàm

Nêu CalculateReturn tính phần trăm Close nguồn; CheckPredictionDirection so dấu âm/0/dương và NULL; EligiblePredictions nối run/target/origin/hai giá rồi kiểm trưởng thành. Chèn ví dụ100→110=10%, flat/flat=1, eligible256 từ file09. Đối chiếu hàm04. Không dùng hàm ba dấu thay nhãn nhị phân strict greater-than của metric.

### 16. Bốn view

Giải thích LatestStockPrice là cuối trong dataset, StudyUniverse là coverage, VN30SnapshotJune2026 chỉ snapshot, ModelPerformance tính theo run và đủ điều kiện. Bảng tên/nguồn/mục đích + SELECT mẫu từ05/Q15. Không gọi latest là giá hôm nay hoặc view snapshot là lịch sử membership.

### 17. Kiểm thử và xác minh

Nêu ca hợp lệ/âm, kỳ vọng đúng error/constraint, rollback của harness và so toàn bộ 13 bảng. Tách “44 ca khác nhau”, “176 lượt lịch sử trên 4 DB”, “64 lượt query” và lượt công bố mới. Nguồn log/summary lịch sử và PUBLICATION_AUDIT; chụp S08 nếu tự chạy. SQL/Python kiểm đủ hai run, không mất JSON hoặc chấp nhận rỗng giả. Không lấy tổng 176 làm 176 ca độc lập; không gán PASS cho máy chưa chạy hoặc coi lỗi dự kiến là lỗi chưa xử lý.

### 18. Demo và transaction

Dùng năm nhóm trong file 09 với thời lượng 4 phút. Đưa S06 (CHECK bị từ chối) và S07 (BEFORE V, DURING V+1, AFTER V, hash bằng nhau, @@TRANCOUNT=0). ROLLBACK hoàn tác thay đổi dữ liệu, nhưng biến cục bộ không được hoàn tác như dữ liệu bảng. Phần 4–5 phải chạy cùng file. Không chỉ chụp câu lệnh ROLLBACK mà không cho thấy trạng thái trước/sau.

### 19. Giới hạn

Giữ 9 blocker trong HISTORICAL_FAILURE_AUDIT: Word Save/native PDF/UI; Express; metadata; adjustment/đơn vị; lịch sử thành phần; CompletedAt; rights (nhóm Word/UI có ba mục). Nêu phạm vi retrospective và tập con đã chọn, không có kết luận ưu thế/đầu tư. Bảng trạng thái cần giữ BLOCKED hoặc NOT VERIFIED đúng phạm vi. Không xóa giới hạn vì GitHub push thành công.

### 20. Kết luận

Đối chiếu mục tiêu ở mục 2 với schema, SQL, test và demo. Gợi ý mở rộng: metadata có nguồn, lịch sử index có quyền, Express runtime, kiểm tải lớn. Các ý này là hướng tương lai, không gắn PASS hoặc số hiệu quả giả. Không hứa lợi nhuận hoặc nói logistic tốt hơn từ hai giá trị mô tả.

### 21. Tham khảo

Dùng [REFERENCES](REFERENCES.md) cùng các nguồn đã có trong báo cáo, chỉ trích nguồn thực sự đọc. Tài liệu Microsoft cho PK/FK/ROLLBACK và GitHub cho cộng tác là nguồn chính thức; truy cập lại khi viết bản mới. Ghi tác giả/tổ chức, tiêu đề, URL/ngày truy cập; không bịa sách/DOI/page. Mã dự án nên trích permalink commit từ PUBLICATION_AUDIT, tránh đường dẫn ổ K.

### 22. Phụ lục

Danh mục SQL 00–12, từ điển dữ liệu, Q01–16, test case, receipt công khai, ảnh SSMS thật và liên kết code. Ghi fixture legacy12 chỉ là đầu vào kiểm thử, không phải schema để triển khai. Chỉ đính nội dung trong public allowlist, không gói lại toàn bộ dự án hoặc backup riêng. Bằng chứng phải dẫn tới file cụ thể và ngày/engine đúng.

## Danh sách ảnh SSMS cần tự chụp

Không có ảnh giả lập SSMS trong hướng dẫn. Các log đã cung cấp là output sqlcmd; ảnh contact sheet là render báo cáo/slide. Dùng database demo và cửa sổ New Query riêng, chụp rõ câu lệnh + Results/Messages; che định danh cá nhân không cần thiết, ghi rõ nếu cắt ảnh.

|ID / caption đề xuất|Thao tác thực|Điều phải nhìn thấy|
|---|---|---|
|S01 — Môi trường chạy|SELECT SERVERPROPERTY('Edition'), SERVERPROPERTY('ProductVersion'), DB_NAME();|Engine/version thật; không suy từ têninstance|
|S02 — Khóa và liên kết|Phần DEMO 1 của file 09|13 bảng, PK DailyPrice/Prediction, FK ForecastOrigin|
|S03 — Preflight|Toàn bộ10|Actual=Expected; PREFLIGHT_PASS|
|S04 — Truy vấn nghiệp vụ|Q02/Q06/Q07 trong07 hoặc DEMO2|SQL + kết quả DEMO; JOIN/HAVING/subquery|
|S05 — Procedure/functions|DEMO 3 của file 09|CompareModels 128/run, ReturnPct 10, eligible 256|
|S06 — Constraint|DEMO4, chạy cùngphần5|547, CK_DailyPrice_Volume; script tiếp tục|
|S07 — Transaction|DEMO5|V/V+1/V, hash trước=sau, transaction0|
|S08 — Validation|Toàn bộ file 08|44 PASS, không FAIL; ghi đúng DB|

**[CAPTURE SSMS SCREENSHOT HERE]** — lặp placeholder này ở vị trí S01–S08 trong bản làm việc cho đến khi có ảnh thật. Ghi caption, dataset=SYNTHETIC, ngày chạy và fileSQL. Nếu không thể chạy SSMS, giữ placeholder/NOT VERIFIED; có thể dẫn logsqlcmd và ghi đúng loại bằng chứng, không đổi nhãn thành screenshot.

## Kiểm tra trước khi gửi PR

- Đủ các nội dung đề cương hoặc đã chỉ rõ mục gộp; mọi kết luận có nguồn.
- 13 bảng/khóa/FK khớp file 01 và ERD; không lưu lặp TargetDate trong Prediction.
- Số demo/thật, 44 ca/176 lượt, retrospective/không kết luận ưu thế được phân biệt rõ.
- Bảng/hình đánh số liên tục, caption trắng–đen; SQL dùng font monospace, không bị cắt.
- Không lỗi font tiếng Việt; xuất PDF từ bản làm việc và kiểm tất cả trang, gồm ERD/tham khảo.
- DOCX/PDF có thể khác số trang vì renderer; không tuyên bố Word/PDF giống từng trang khi chưa kiểm.
- Không có private data/manifest/screenshot, secret hoặc citation bịa.
- PR nêu file đổi, lý do, cách kiểm, nguồn và ảnh cần bổ sung; technical owner review trước merge.

## Bản quyền và quyền sử dụng dữ liệu

Dữ liệu thị trường thực tế của dự án được thu thập và truy xuất qua **VNstock**. VNstock là công cụ truy xuất; dữ liệu gốc tiếp tục chịu quyền và điều kiện của các nhà cung cấp hoặc chủ thể quyền bên thứ ba. Việc truy xuất không chuyển quyền sở hữu hoặc quyền phân phối lại dữ liệu nguồn cho dự án.

Kết quả dự báo, phân tích và tài sản nghiên cứu được ghi nhận trong hoạt động nghiên cứu của **Lương Minh Quân** và **DATCOM Lab**, theo đóng góp và quyền hợp pháp của các bên. Ghi nhận này không khẳng định DATCOM Lab là pháp nhân đồng sở hữu độc quyền mọi tài sản.

Dữ liệu **mô phỏng** trong bộ demo được tạo để phục vụ bài tập lớn, không phải bản ghi thị trường thu thập từ VNstock hoặc kết quả nghiên cứu thực tế. Nhóm được phân công và giảng viên chỉ sử dụng tài liệu được chia sẻ hợp pháp trong phạm vi bài tập/đánh giá; nghiên cứu khác hoặc việc khai thác tài sản hạn chế ngoài phạm vi được ủy quyền cần được cho phép trước bằng email hoặc văn bản từ chủ thể có thẩm quyền. Gửi yêu cầu mà chưa được chấp thuận không tạo sự cho phép.

Xem [LICENSE.md](../LICENSE.md) — **MarketLab VN30 — Restricted Research and Academic Use License (2026)**. Đây là giấy phép riêng hạn chế, không phải giấy phép nguồn mở được OSI công nhận. Quyền theo pháp luật, giấy phép có trước, điều kiện bên thứ ba và các quyền áp dụng theo GitHub vẫn được giữ nguyên.

Khi viết báo cáo, giữ ghi nhận nguồn VNstock, đóng góp nghiên cứu và nhãn mô phỏng. Chỉ dùng tài liệu/tổng hợp được phép chia sẻ; không tự đưa bản ghi nghiên cứu nội bộ hoặc dữ liệu tạo đặc trưng vào phụ lục.
