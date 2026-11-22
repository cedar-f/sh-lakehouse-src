# Tổng quan hệ thống và thông tin triển khai

R2 Lakehouse là workspace phân tích dữ liệu tự host bằng Docker, tích hợp notebook Python/Spark, SQL, catalog, file browser, Git, dbt và workflow/schedule trong cùng giao diện. Ubuntu 22.04 là nền tảng host; Windows 11 có thể dùng để phát triển hoặc chạy Linux containers bằng Docker Desktop.

Hệ thống tích hợp các service độc lập, không phải Databricks Runtime. Delta Lake lưu dữ liệu hot trên Cloudflare R2. Quy mô thiết kế tham khảo là 300 GB dữ liệu và 50 GB truyền tải/tháng; hiệu năng và ngân sách cần được đo theo workload tại mỗi deployment.

## Đọc theo vai trò

| Vai trò | Tài liệu |
|---|---|
| Người dùng | [USER_GUIDE](USER_GUIDE.md), [Git workspace](GITHUB_WORKSPACE.md), [dbt sample/report](REBUILD_DBT.md), [workflow](RUNS_WORKFLOWS.md) |
| Cài đặt | [Ubuntu](UBUNTU_DEPLOYMENT.md), [Windows](INSTALLATION.md), [env](ENVIRONMENT.md), [RAM/CPU](RESOURCE_PLANNING.md) |
| Vận hành | [Architecture](ARCHITECTURE.md), [Operations](OPERATIONS.md), [Security](SECURITY.md), [DR](DISASTER_RECOVERY.md) |
| Bảo trì code | [Development](DEVELOPMENT.md), [API](API.md), [Versions](VERSIONS.md) |
| Kiểm tra deployment | [Validation](VALIDATION.md), [Acceptance](ACCEPTANCE.md) |

## Các nguyên tắc hoạt động

1. UC metadata hoạt động trên PostgreSQL SSD. R2 giữ Delta, incoming và snapshot backup. Clone source hoặc dùng cùng bucket không tự kế thừa catalog; chuyển host cần restore metadata.
2. Spark chạy local, mỗi kernel/notebook nền có JVM riêng; SQL/dbt dùng SQL service. Chưa có shared Spark cluster/autoscaling.
3. Người dùng thuộc cùng miền tin cậy. UC authorization tắt, SQL dùng NOSASL, UI Permissions không enforce RBAC.
4. Repo source hệ thống khác repo workspace. Source chứa application/scripts/docs/templates; workspace chứa notebook/model/workflow. Secret, database volumes và backup không thuộc Git source.
5. Rebuild giữ state; reset metadata là thao tác xóa có flag riêng. Không dùng reset để upgrade hoặc chữa credential.
6. Snapshot hiện tại không nhân bản toàn bộ Delta data. Cần kế hoạch backup data độc lập nếu phải chịu được mất bucket.
7. Tab GitHub thiết lập repo/key/commit đầu; Git panel Jupyter dùng cùng `.git` và SSH agent cho công việc hằng ngày. Xem [GITHUB_WORKSPACE](GITHUB_WORKSPACE.md).

## Hồ sơ vận hành riêng cho mỗi deployment

Người quản trị lưu các trường dưới đây ở nơi được bảo vệ; không điền secret trực tiếp vào tài liệu Git. Đây là mẫu thông tin cần quản lý, không phải cấu hình của một máy cụ thể.

| Hạng mục | Cách xác định |
|---|---|
| Source URL / branch / commit | git remote, git branch, git rev-parse |
| Host / OS / CPU / RAM / disk | Inventory của host và Docker engine |
| Source directory / WORKSPACE_DIR / Compose project | Đường dẫn và env thực tế |
| IP/domain / SSH user và port / public mode | Firewall, DNS, proxy và listener thực tế |
| R2 bucket / endpoint / backup prefix | Env deployment; key lưu trong secret store |
| Owner / người nhận cảnh báo | Phân công vận hành |
| Lịch backup / bản sao Delta độc lập | Chính sách backup và retention |
| RPO/RTO / giới hạn tải | Cam kết sau benchmark và restore drill |

## Thuật ngữ

| Tên | Định nghĩa |
|---|---|
| Workspace | Thư mục code và các panel UI của hệ thống |
| Compute | Cấu hình/process Spark local |
| Catalog / schema | Namespace metadata UC; bảng có tên catalog.schema.table |
| UC volume | Metadata external file location; khác Docker named volume |
| Run ID | ID 32 hex của một job runner |
| Execution ID | ID Kestra; có thể liên kết nhiều Run ID |
| dbt report / Docs | Kết quả thực thi/test và tài liệu/lineage snapshot riêng |
| Folder R2 | Prefix object key, có thể có marker 0 byte |
