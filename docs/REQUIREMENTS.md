# Tiêu chí V3 và trạng thái

| Yêu cầu | Cách đáp ứng | Trạng thái |
|---|---|---|
| Ubuntu 22.04 host, Windows 11 dev | Docker Engine/Compose; Windows 11 có Docker Desktop Linux | Có hướng dẫn cả hai OS; script Windows đã chạy trên máy dev, Ubuntu đích cần kiểm tra khi triển khai |
| Giao diện chung gần Databricks | Extension gốc JupyterLab, panel cạnh notebook | Đã mở được trong browser; chưa tương đương toàn bộ Databricks |
| Delta hot trên R2 | R2 Standard, Spark/Delta | Đã kiểm tra tạo và đọc table |
| Catalog/schema/table và file | UC API + native Catalog/Files panels | CRUD catalog/schema và xem table; multipart API đã qua kiểm tra |
| Tạo catalog mới, tên mặc định cấu hình được | Bootstrap/config; refresh connector theo danh sách UC | Có triển khai; hướng dẫn SQL trong USER_GUIDE.md |
| SQL mặc định đăng ký catalog thật | defaultCatalog + UC managed Delta | Đã kiểm chứng, không dùng temp view |
| Notebook tự có Spark và SQL cell | IPython startup, %%sql, HTML dataframe | Notebook đã lưu chạy thành công qua runner, có tham số và SQL |
| Cluster status và Spark config | Compute panel; CPU, memory, shuffle, extra JSON | Có triển khai; Save & Restart cho SQL hoặc kernel đã chọn |
| GitHub | JupyterLab Git, SSH volume | Extension enabled; GitHub private cần tài khoản của bạn |
| Kéo thả file lớn/nhiều file/progress | Multipart 32 MiB, queue, resume, cancel | API upload/resume/readback đã qua; chưa thử 300 GB |
| Workflow kéo thả, dependency, schedule | Graph → Kestra DAG hoặc runner điều phối logic | Hai task dependency đã chạy SUCCESS; cron lưu disabled mặc định |
| Variables, If và For each | Biến có kiểu dữ liệu, điều kiện và loop tuần tự trong runner | variable_if_foreach_demo đã chạy Then/Else, danh sách rỗng và input tùy chỉnh |
| Trigger notebook đã lưu | Kestra HTTP task → runner → NBClient | Runner thực thi notebook thành công; output riêng, không ghi đè nguồn |
| dbt trong bản đầu | dbt Core + dbt-spark + Spark Thrift | debug/seed/build và 2 data tests đã qua |
| Nhiều user | JupyterHub/PAM tùy chọn | Đăng nhập, server riêng, SQL grid và đăng nhập lại sau recreate đã qua kiểm tra |
| Quyền dữ liệu theo từng user | Cần UC auth + identity + cô lập đường truy cập storage | **Chưa triển khai; hiện là workspace tin cậy chung quyền** |
| Power BI/ADF tùy chọn | ODBC, Windows gateway/SHIR | Có hướng dẫn; cần driver và kiểm tra thực tế |
| Sang host khác kế thừa catalog | PostgreSQL dump → R2 → restore | Đã khôi phục vào PostgreSQL/UC mới và SELECT từ Spark riêng thành công |

Chi tiết bằng chứng và giới hạn ở [VALIDATION.md](VALIDATION.md) và [FEATURES.md](FEATURES.md). Bản này là V3 thử nghiệm cho miền người dùng tin cậy; không nên mô tả là đã đạt đầy đủ phân quyền Unity Catalog của Databricks.
