# Dữ liệu mô phỏng độc lập

Tất cả giá, khối lượng, công ty, ngành và xác suất trong thư mục này đều được tạo để minh họa, không phải bản ghi nghiên cứu. 8 mã DEMO01–DEMO08, 42 ngày lịch giả định, 280 giá, 258 dự báo, 34 ForecastOrigin; 256 dự báo đủ điều kiện, 2 thiếu endpoint. Lịch này chỉ bỏ cuối tuần, không phải lịch HOSE.

CSV và tables.json là cùng bộ dữ liệu; [all_in_one.sql](../../sql/all_in_one.sql) đã nhúng dữ liệu nên không cần Python hoặc CSV khi demo. [import_data.py](../../scripts/import_data.py) chỉ tạo SQL dẫn xuất để so byte với bản đã duyệt.
