# Từ điển dữ liệu

Được sinh từ sys.columns, sys.types, sys.default_constraints, sys.indexes và sys.foreign_keys của schema đã chạy thực tế. LoadedAt là thời gian nạp UTC, không thay thế thời gian tạo dự báo nguồn.

## DailyPrice

OHLCV của một mã tại một phiên trong một dataset.

|Cột|Kiểu SQL Server|Khóa|NULL|DEFAULT|Ý nghĩa|
|---|---|---|---|---|---|
|DatasetId|int|FK,PK|Không|—|Định danh phạm vi dữ liệu|
|StockId|int|FK,PK|Không|—|Định danh cổ phiếu|
|TradeDate|date|FK,PK|Không|—|Ngày phiên trong dataset|
|OpenPrice|decimal(19,6)|—|Không|—|Giá mở cửa nguồn|
|HighPrice|decimal(19,6)|—|Không|—|Giá cao nhất nguồn|
|LowPrice|decimal(19,6)|—|Không|—|Giá thấp nhất nguồn|
|ClosePrice|decimal(19,6)|—|Không|—|Giá đóng cửa nguồn|
|Volume|bigint|—|Không|—|Khối lượng nguồn, không âm|
|LoadedAt|datetime2(0)|—|Không|(sysutcdatetime())|Thời gian nạp UTC do DB ghi; không phải thời gian phát hành dự báo|

## Dataset

Phạm vi nguồn, đơn vị giá, loại dữ liệu và ngày đã quan sát; tách các phiên bản dữ liệu.

|Cột|Kiểu SQL Server|Khóa|NULL|DEFAULT|Ý nghĩa|
|---|---|---|---|---|---|
|DatasetId|int|PK|Không|—|Định danh phạm vi dữ liệu|
|DatasetCode|varchar(80)|UK|Không|—|Mã dataset duy nhất|
|MarketId|int|FK|Không|—|Định danh thị trường|
|DataKind|varchar(20)|—|Không|—|SYNTHETIC hoặc REAL_PRIVATE|
|PriceBasis|varchar(40)|—|Không|—|SOURCE_CLOSE; không khẳng định điều chỉnh cổ tức/chia tách|
|PriceUnit|nvarchar(100)|—|Không|—|Đơn vị báo giá và giới hạn xác minh|
|ObservedThrough|date|—|Không|—|Ngày cuối được coi là đã quan sát trong dataset|
|ManifestPath|nvarchar(400)|—|Không|—|Đường dẫn manifest tái lập|
|ProvenanceNote|nvarchar(1000)|—|Không|—|Nguồn gốc và giới hạn sử dụng|

## ForecastModel

Định danh phương pháp dự báo, không lưu xác suất ở mức mô hình.

|Cột|Kiểu SQL Server|Khóa|NULL|DEFAULT|Ý nghĩa|
|---|---|---|---|---|---|
|ModelId|int|PK|Không|—|Định danh phương pháp|
|ModelCode|varchar(70)|UK|Không|—|Mã phương pháp duy nhất|
|ModelName|nvarchar(160)|—|Không|—|Tên phương pháp|
|MethodNote|nvarchar(500)|—|Không|—|Mô tả phương pháp/nguồn|

## ForecastOrigin

Ánh xạ một lần chạy và ngày gốc sang ngày mục tiêu; loại phụ thuộc bộ phận khỏi Prediction.

|Cột|Kiểu SQL Server|Khóa|NULL|DEFAULT|Ý nghĩa|
|---|---|---|---|---|---|
|RunId|int|FK,PK|Không|—|Định danh lần chạy|
|OriginDate|date|PK|Không|—|Ngày gốc dự báo; nguồn chỉ có ngày, không suy diễn timestamp phát hành|
|TargetDate|date|—|Không|—|Ngày mục tiêu đã kiểm tra đúng số phiên|

## IndexMembership

Quan hệ N–N chỉ số–cổ phiếu có khoảng hiệu lực đóng [ValidFrom, ValidTo].

|Cột|Kiểu SQL Server|Khóa|NULL|DEFAULT|Ý nghĩa|
|---|---|---|---|---|---|
|IndexId|int|FK,PK|Không|—|Định danh chỉ số|
|StockId|int|FK,PK|Không|—|Định danh cổ phiếu|
|ValidFrom|date|PK|Không|—|Ngày bắt đầu hiệu lực (bao gồm)|
|ValidTo|date|—|Không|—|Ngày kết thúc hiệu lực (bao gồm)|
|EvidenceNote|nvarchar(500)|—|Không|—|Bằng chứng hoặc nhãn dữ liệu mô phỏng|

## Industry

Danh mục ngành có nguồn hoặc được ghi rõ mô phỏng; không tự gán ngành cho dữ liệu thật.

|Cột|Kiểu SQL Server|Khóa|NULL|DEFAULT|Ý nghĩa|
|---|---|---|---|---|---|
|IndustryId|int|PK|Không|—|Định danh ngành; NULL ở Stock nếu chưa có bằng chứng|
|IndustryCode|varchar(30)|UK|Không|—|Mã ngành duy nhất|
|IndustryName|nvarchar(120)|—|Không|—|Tên ngành|
|EvidenceNote|nvarchar(400)|—|Không|—|Bằng chứng hoặc nhãn dữ liệu mô phỏng|

## Market

Danh mục thị trường và đồng tiền tham chiếu.

|Cột|Kiểu SQL Server|Khóa|NULL|DEFAULT|Ý nghĩa|
|---|---|---|---|---|---|
|MarketId|int|PK|Không|—|Định danh thị trường|
|MarketCode|varchar(12)|UK|Không|—|Mã thị trường duy nhất|
|MarketName|nvarchar(120)|—|Không|—|Tên thị trường|
|CurrencyCode|char(3)|—|Không|—|Mã tiền tệ; không phải bằng chứng đơn vị giá|

## ModelRun

Cấu hình một lần chạy: dataset, mục tiêu, development/validation, threshold và nguồn.

|Cột|Kiểu SQL Server|Khóa|NULL|DEFAULT|Ý nghĩa|
|---|---|---|---|---|---|
|RunId|int|PK|Không|—|Định danh lần chạy|
|RunCode|varchar(100)|UK|Không|—|Mã lần chạy duy nhất|
|ModelId|int|FK|Không|—|Định danh phương pháp|
|DatasetId|int|FK|Không|—|Định danh phạm vi dữ liệu|
|TargetId|int|FK|Không|—|Định danh định nghĩa mục tiêu|
|TrainStart|date|—|Không|—|Bắt đầu khoảng development|
|TrainEnd|date|—|Không|—|Kết thúc development theo protocol|
|ValidationEnd|date|—|Không|—|Kết thúc validation; ngày gốc phải lớn hơn ngày này|
|SelectedC|decimal(12,6)|—|Có|—|Nghịch đảo mức phạt L2; NULL nếu không áp dụng|
|Threshold|decimal(9,8)|—|Không|((0.5))|Ngưỡng phân lớp; xác suất bằng ngưỡng thuộc lớp 1|
|EvaluationClass|varchar(40)|—|Không|—|SYNTHETIC_TEST hoặc RETROSPECTIVE_OOS|
|SourceRun|nvarchar(200)|—|Không|—|Định danh lần chạy nguồn|
|CompletedAt|datetime2(0)|—|Có|—|Thời gian hoàn tất nguồn; NULL nếu chưa xác minh|

## Prediction

Xác suất tăng giá của một mã tại một ngày gốc trong một lần chạy.

|Cột|Kiểu SQL Server|Khóa|NULL|DEFAULT|Ý nghĩa|
|---|---|---|---|---|---|
|RunId|int|FK,PK|Không|—|Định danh lần chạy|
|StockId|int|FK,PK|Không|—|Định danh cổ phiếu|
|OriginDate|date|FK,PK|Không|—|Ngày gốc dự báo; nguồn chỉ có ngày, không suy diễn timestamp phát hành|
|ProbabilityPositive|decimal(19,16)|—|Không|—|Xác suất lớp 1, thuộc [0,1]|
|LoadedAt|datetime2(0)|—|Không|(sysutcdatetime())|Thời gian nạp UTC do DB ghi; không phải thời gian phát hành dự báo|

## Stock

Định danh mã chứng khoán trong thị trường; tên công ty và ngành có thể chưa biết.

|Cột|Kiểu SQL Server|Khóa|NULL|DEFAULT|Ý nghĩa|
|---|---|---|---|---|---|
|StockId|int|PK|Không|—|Định danh cổ phiếu|
|MarketId|int|FK,UK|Không|—|Định danh thị trường|
|Ticker|varchar(20)|UK|Không|—|Mã cổ phiếu; duy nhất trong thị trường|
|CompanyName|nvarchar(200)|—|Có|—|Tên pháp nhân; NULL khi nguồn không cung cấp|
|IndustryId|int|FK|Có|—|Định danh ngành; NULL ở Stock nếu chưa có bằng chứng|
|IsSynthetic|bit|—|Không|((0))|1 nếu mã mô phỏng, 0 nếu mã thật|

## StockIndex

Danh mục chỉ số trong thị trường.

|Cột|Kiểu SQL Server|Khóa|NULL|DEFAULT|Ý nghĩa|
|---|---|---|---|---|---|
|IndexId|int|PK|Không|—|Định danh chỉ số|
|MarketId|int|FK,UK|Không|—|Định danh thị trường|
|IndexCode|varchar(20)|UK|Không|—|Mã chỉ số trong thị trường|
|IndexName|nvarchar(150)|—|Không|—|Tên chỉ số|

## TargetDefinition

Định nghĩa biến mục tiêu, đơn vị đầu ra và số phiên dự báo.

|Cột|Kiểu SQL Server|Khóa|NULL|DEFAULT|Ý nghĩa|
|---|---|---|---|---|---|
|TargetId|int|PK|Không|—|Định danh định nghĩa mục tiêu|
|TargetCode|varchar(50)|UK|Không|—|Mã mục tiêu duy nhất|
|HorizonSessions|int|UK|Không|—|Số phiên kế tiếp trong lịch dataset|
|OutputType|varchar(40)|UK|Không|—|Xác suất Close mục tiêu lớn hơn Close ngày gốc|
|LabelRule|varchar(80)|UK|Không|—|Nhãn 1 nếu tăng nghiêm ngặt; giảm hoặc bằng là 0|

## TradingDay

Lịch phiên riêng cho từng dataset, không giao cắt lịch của các thị trường.

|Cột|Kiểu SQL Server|Khóa|NULL|DEFAULT|Ý nghĩa|
|---|---|---|---|---|---|
|DatasetId|int|FK,PK|Không|—|Định danh phạm vi dữ liệu|
|TradeDate|date|PK|Không|—|Ngày phiên trong dataset|

## Ràng buộc CHECK

|Bảng|Tên|Biểu thức|
|---|---|---|
|DailyPrice|CK_DailyPrice_OHLC|([HighPrice]>=[OpenPrice] AND [HighPrice]>=[ClosePrice] AND [HighPrice]>=[LowPrice] AND [LowPrice]<=[OpenPrice] AND [LowPrice]<=[ClosePrice])|
|DailyPrice|CK_DailyPrice_Positive|([OpenPrice]>(0) AND [HighPrice]>(0) AND [LowPrice]>(0) AND [ClosePrice]>(0))|
|DailyPrice|CK_DailyPrice_Volume|([Volume]>=(0))|
|Dataset|CK_Dataset_Basis|([PriceBasis]='SOURCE_CLOSE')|
|Dataset|CK_Dataset_Kind|([DataKind]='REAL_PRIVATE' OR [DataKind]='SYNTHETIC')|
|ForecastOrigin|CK_ForecastOrigin_Dates|([TargetDate]>[OriginDate])|
|IndexMembership|CK_IndexMembership_Dates|([ValidTo]>=[ValidFrom])|
|ModelRun|CK_ModelRun_C|([SelectedC] IS NULL OR [SelectedC]>(0))|
|ModelRun|CK_ModelRun_Class|([EvaluationClass]='RETROSPECTIVE_OOS' OR [EvaluationClass]='SYNTHETIC_TEST')|
|ModelRun|CK_ModelRun_Dates|([TrainStart]<=[TrainEnd] AND [TrainEnd]<[ValidationEnd])|
|ModelRun|CK_ModelRun_Threshold|([Threshold]>(0) AND [Threshold]<(1))|
|Prediction|CK_Prediction_Probability|([ProbabilityPositive]>=(0) AND [ProbabilityPositive]<=(1))|
|TargetDefinition|CK_Target_Horizon|([HorizonSessions]>(0))|
|TargetDefinition|CK_Target_Output|([OutputType]='PROBABILITY_CLOSE_UP')|
|TargetDefinition|CK_Target_Rule|([LabelRule]='CLOSE_TARGET_GT_CLOSE_ORIGIN_ELSE_ZERO')|

## Khóa ngoại

|Tên|Bảng con/cột|Bảng cha/cột|
|---|---|---|
|FK_DailyPrice_Stock|DailyPrice(StockId)|Stock(StockId)|
|FK_DailyPrice_TradingDay|DailyPrice(DatasetId,TradeDate)|TradingDay(DatasetId,TradeDate)|
|FK_Dataset_Market|Dataset(MarketId)|Market(MarketId)|
|FK_ForecastOrigin_Run|ForecastOrigin(RunId)|ModelRun(RunId)|
|FK_IndexMembership_Index|IndexMembership(IndexId)|StockIndex(IndexId)|
|FK_IndexMembership_Stock|IndexMembership(StockId)|Stock(StockId)|
|FK_ModelRun_Dataset|ModelRun(DatasetId)|Dataset(DatasetId)|
|FK_ModelRun_Model|ModelRun(ModelId)|ForecastModel(ModelId)|
|FK_ModelRun_Target|ModelRun(TargetId)|TargetDefinition(TargetId)|
|FK_Prediction_ForecastOrigin|Prediction(RunId,OriginDate)|ForecastOrigin(RunId,OriginDate)|
|FK_Prediction_Run|Prediction(RunId)|ModelRun(RunId)|
|FK_Prediction_Stock|Prediction(StockId)|Stock(StockId)|
|FK_Stock_Industry|Stock(IndustryId)|Industry(IndustryId)|
|FK_Stock_Market|Stock(MarketId)|Market(MarketId)|
|FK_StockIndex_Market|StockIndex(MarketId)|Market(MarketId)|
|FK_TradingDay_Dataset|TradingDay(DatasetId)|Dataset(DatasetId)|
