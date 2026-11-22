# Quyết định thiết kế và các việc chưa thực hiện

Đây là lý do/đánh đổi phản ánh implementation hiện tại, không phải cam kết rằng mọi khả năng Databricks đã được tái tạo.

| Quyết định | Lý do và hệ quả |
|---|---|
| JupyterLab extension là UI chính | Giữ notebook/Git native, các panel mở cùng vùng tab; không nhúng notebook editor qua iframe. Cần rebuild bundle khi đổi UI |
| Spark local thay cluster phân tán | Đơn giản cho một host Docker; nhiều JVM, RAM không gộp, không autoscale. Chuyển Spark Connect/shared cluster là thay kiến trúc chưa làm |
| Delta trên R2 Standard | Dữ liệu hot, S3-compatible; không dùng Google Drive làm storage hoạt động. Files uploaded phải chuyển thành Delta nếu muốn table |
| UC OSS + PostgreSQL | Có metadata/catalog/schema và managed Delta integration; active DB dùng SSD. R2 chỉ chứa snapshot metadata để migrate |
| Custom UC R2 credential signer | Integration UC/R2 dùng scoped credentials; cần test riêng khi nâng version. Không suy ra per-user enforcement khi UC auth disabled |
| Kestra + runner | Kestra giữ schedule/execution, runner chạy subprocess và advanced logic; không mount Docker socket. Cancel trong Kestra chưa bảo đảm dừng runner tức thời |
| dbt Core qua Spark Thrift | Tận dụng SQL service; không cần dbt Cloud account. Docs snapshot tách khỏi report execution/test |
| Source repo tách workspace repo | Người khác dựng platform từ source mà không lấy notebook/dbt riêng hoặc secrets. Template dbt sample là phần source, sinh khi thiếu |
| Artifact vào named volume + retention | Giảm source/workspace phình; history metadata có thể sống lâu hơn artifact. Maven/DB/temp/data R2 có vòng đời khác |
| Bootstrap không ghi đè | Tạo prefix/sample thiếu, giữ nội dung có sẵn. Đổi template không tự cập nhật bản sample đã được người dùng sửa |
| Reset metadata có explicit flag và preflight | Tránh đồng nhất rebuild với xóa state; không xóa R2 data. Không thay backup/restore |

## Giới hạn và yêu cầu nghiệm thu

| Hạng mục | Trạng thái |
|---|---|
| UC RBAC theo user, row/column policies, storage isolation giữa workspace | Chưa triển khai |
| RAM Spark tách riêng theo từng service | Chưa triển khai; chỉ có shared settings và cap container riêng |
| Shared Spark cluster, autoscaling, multi-host compute | Chưa triển khai |
| Workflow permissions theo user, distributed/exactly-once execution | Chưa triển khai |
| API hủy runner process toàn chuỗi từ nút cancel Kestra | Chưa bảo đảm |
| Notebook revision pin đầy đủ mọi file phụ khi chạy | Chưa có; snapshot chỉ có phạm vi trong source capture |
| Tự động backup định kỳ, bản sao Delta ngoài bucket, DR SLA | Chưa cấu hình/cam kết |
| CI/CD và reproducible dependency lock toàn bộ | Chưa có |
| Benchmark 300 GB, upload quy mô lớn, throughput | Đo và chốt ngưỡng theo deployment/workload |
| Power BI/ADF, DirectQuery/sink Delta qua ODBC | Tùy chọn; nghiệm thu driver/network/query thực tế |
| Ubuntu public HTTPS | Cấu hình domain/firewall/proxy và nghiệm thu mỗi host |

Đề xuất trong tài liệu không tự bật tính năng. Khi triển khai một mục mới, sửa code/config/test rồi cập nhật bảng trạng thái và [VALIDATION.md](VALIDATION.md); không chỉ đổi mô tả requirement thành “đã hỗ trợ”.
