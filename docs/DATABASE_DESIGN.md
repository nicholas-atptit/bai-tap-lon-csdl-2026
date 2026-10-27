# Thiết kế cơ sở dữ liệu

Mô hình quan hệ gồm 13 bảng. Mỗi database chứa một tập nguồn chính; khóa DatasetId vẫn cho phép quản lý nhiều phiên bản tách biệt. Giá và dự báo thật/mô phỏng được tách database và kiểm tra chéo loại mã.

## DailyPrice

OHLCV của một mã tại một phiên trong một dataset.

PK_DailyPrice: (DatasetId, StockId, TradeDate).

## Dataset

Phạm vi nguồn, đơn vị giá, loại dữ liệu và ngày đã quan sát; tách các phiên bản dữ liệu.

PK_Dataset: (DatasetId); UQ_Dataset_Code: (DatasetCode).

## ForecastModel

Định danh phương pháp dự báo, không lưu xác suất ở mức mô hình.

PK_ForecastModel: (ModelId); UQ_ForecastModel_Code: (ModelCode).

## ForecastOrigin

Ánh xạ một lần chạy và ngày gốc sang ngày mục tiêu; loại phụ thuộc bộ phận khỏi Prediction.

PK_ForecastOrigin: (RunId, OriginDate).

## IndexMembership

Quan hệ N–N chỉ số–cổ phiếu có khoảng hiệu lực đóng [ValidFrom, ValidTo].

PK_IndexMembership: (IndexId, StockId, ValidFrom).

## Industry

Danh mục ngành có nguồn hoặc được ghi rõ mô phỏng; không tự gán ngành cho dữ liệu thật.

PK_Industry: (IndustryId); UQ_Industry_Code: (IndustryCode).

## Market

Danh mục thị trường và đồng tiền tham chiếu.

PK_Market: (MarketId); UQ_Market_Code: (MarketCode).

## ModelRun

Cấu hình một lần chạy: dataset, mục tiêu, development/validation, threshold và nguồn.

PK_ModelRun: (RunId); UQ_ModelRun_Code: (RunCode).

## Prediction

Xác suất tăng giá của một mã tại một ngày gốc trong một lần chạy.

PK_Prediction: (RunId, StockId, OriginDate).

## Stock

Định danh mã chứng khoán trong thị trường; tên công ty và ngành có thể chưa biết.

PK_Stock: (StockId); UQ_Stock_MarketTicker: (MarketId, Ticker).

## StockIndex

Danh mục chỉ số trong thị trường.

PK_StockIndex: (IndexId); UQ_StockIndex_Code: (MarketId, IndexCode).

## TargetDefinition

Định nghĩa biến mục tiêu, đơn vị đầu ra và số phiên dự báo.

PK_TargetDefinition: (TargetId); UQ_Target_Definition: (HorizonSessions, OutputType, LabelRule); UQ_TargetDefinition_Code: (TargetCode).

## TradingDay

Lịch phiên riêng cho từng dataset, không giao cắt lịch của các thị trường.

PK_TradingDay: (DatasetId, TradeDate).

## Quy tắc triển khai

Không cascade xóa giá hoặc dự báo. Không nhập chung nhiều price basis vào một dataset. Hai CHECK về OHLC kiểm tra giá dương và thứ tự High/Low; Volume là BIGINT không âm. Một giá duy nhất theo (DatasetId, StockId, TradeDate). ForecastOrigin duy nhất theo (RunId, OriginDate); Prediction duy nhất theo (RunId, StockId, OriginDate).

Trigger kiểm tra phạm vi thị trường, nhãn mô phỏng/thật, ngày đã quan sát, khoảng hiệu lực không chồng lấn và horizon theo lịch phiên dataset. Khi đã có dự báo, cấu hình run/mục tiêu và ngữ nghĩa dataset không được đổi; thay đổi lịch không được làm sai các horizon đã lưu. Đây là kiểm tra liên bảng bổ sung cho PK/FK/CHECK, không thay thế chúng.

## Chỉ mục

PK DailyPrice đã phục vụ giá theo mã/ngày trong dataset. IX_DailyPrice_Date phục vụ đối chiếu toàn bộ mã tại một phiên, INCLUDE ClosePrice và Volume. IX_IndexMembership_Stock phục vụ lịch sử một mã. IX_ModelRun_Model lọc các lần chạy theo phương pháp/dataset/mục tiêu. IX_Prediction_Date phục vụ phân tích theo ngày gốc. Các chỉ mục này đổi thứ tự cột so với PK, không tạo bản sao của PK.

## ERD và khoảng hiệu lực

Nguồn Mermaid: docs/diagrams/marketlab_erd.mmd. Bản SVG/PNG/PDF được sinh từ cùng metadata sys.* và cùng danh sách FK. Đầu 1 nghĩa là quan hệ bắt buộc với đúng một bản ghi cha; 0..1 chỉ áp dụng Industry của Stock; đầu N cho phép 0..N bản ghi con. N–N giữa StockIndex và Stock được giải bằng IndexMembership. Snapshot VN30 chỉ có hiệu lực 01–30/06/2026 theo phạm vi tháng được cung cấp; không suy diễn lịch sử hoặc danh sách hiện tại.
