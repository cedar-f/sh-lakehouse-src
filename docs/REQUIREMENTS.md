# Phạm vi chức năng và giới hạn

| Nhu cầu | Cơ chế | Giới hạn vận hành |
|---|---|---|
| Ubuntu host / Windows dev | Docker Linux containers | Chọn profile RAM, đường dẫn và script theo OS |
| Một giao diện phân tích | JupyterLab + native Lakehouse panels | Không tương đương toàn bộ Databricks |
| Delta hot trên R2 | Spark/Delta + R2 Standard | Benchmark theo query, request và workload |
| Catalog/schema/table/file | UC + PostgreSQL, SQL DDL và Files | UI không cung cấp đủ CRUD mọi object |
| Tên catalog mới/mặc định | Bootstrap, Compute default, connector refresh | Tạo namespace trước khi ghi; tên ba phần |
| Notebook tự có Spark/SQL | Startup helper, %%sql và HTML grid | Mỗi kernel có Spark JVM riêng |
| Compute config/status | Save & Restart SQL/kernel đã chọn | Container cap ở env; driver memory chung |
| GitHub và Git native | Onboarding/SSH agent/auto ignore → Jupyter Git | Cùng repo/user; key encrypted cần unlock sau restart |
| File lớn/nhiều file | Multipart 32 MiB, queue/progress/resume | Tuần tự, cần state local và R2 để resume |
| Workflow/schedule | Visual graph + Kestra/runner | Logic advanced chạy trong runner, loop tuần tự |
| Variables/If/For each/output | Typed expressions và durable trace | Giới hạn node/loop/output; không exactly-once |
| dbt | dbt Core + Spark Thrift + report/Docs | Phải đo và kiểm build/tests trên deployment thật |
| Nhiều user | JupyterHub/PAM tùy chọn | Chung trust boundary; không UC per-user RBAC |
| Power BI/ADF | ODBC + Windows gateway/SHIR | Driver/network/license riêng |
| Chuyển host giữ catalog | Portable registry R2 replay empty namespace/comments/properties/root/external volume/table; DB restore cho UC đầy đủ | Sync trước reset, managed inventory chưa tự replay; chỉ một writer |

Các giới hạn chưa triển khai gồm UC authorization theo user, row/column policies, isolated multi-tenant compute/storage, Spark shared cluster/autoscaling, RAM driver theo service và runner cancellation xuyên suốt từ Kestra. Xem [DECISIONS](DECISIONS.md), [SECURITY](SECURITY.md), [ARCHITECTURE](ARCHITECTURE.md).

Nghiệm thu mỗi deployment theo [VALIDATION](VALIDATION.md) và [ACCEPTANCE](ACCEPTANCE.md); tài liệu chức năng không là cam kết hiệu năng hoặc kết quả test của host.
