# Bàn giao R2 Lakehouse

Ngày đối chiếu: **22/11/2026**, timezone Asia/Ho_Chi_Minh. Mã ứng dụng: **V3.1.3 + hotfix quyền image**, baseline kỹ thuật `e842c7a`. Tài liệu mô tả code có trong repo; trạng thái server thực tế cần xác nhận bằng [ACCEPTANCE.md](ACCEPTANCE.md).

## Project giải quyết việc gì?

Một workspace phân tích dữ liệu tự host, có notebook Python/Spark, SQL, catalog, file browser, Git, dbt và workflow/schedule trong cùng giao diện. Windows 11 là máy dev; Ubuntu 22.04 là host dự kiến, hiện được người vận hành báo có 16 GB RAM. Dữ liệu hot lưu bằng Delta Lake trên Cloudflare R2; quy mô mục tiêu ban đầu khoảng 300 GB, truyền tải dự kiến tối đa khoảng 50 GB/tháng, có thể thấp hơn nhiều. Các con số này là yêu cầu dung lượng, **không phải benchmark đã đạt**.

Đây là ứng dụng tích hợp các service độc lập, không phải Databricks Runtime. Có thể quản lý catalog/schema/table bằng tên ba phần, tạo catalog mới, chạy notebook và dbt, xây workflow có biến/điều kiện/loop và xem lịch sử/log. Xem [FEATURES.md](FEATURES.md) và [REQUIREMENTS.md](REQUIREMENTS.md) để phân biệt phần đã có với phần chưa đáp ứng.

## Đọc theo vai trò

| Người nhận | Thứ tự đọc |
|---|---|
| Người dùng dữ liệu | Tài liệu này → [USER_GUIDE](USER_GUIDE.md) → [REBUILD_DBT](REBUILD_DBT.md) → [RUNS_WORKFLOWS](RUNS_WORKFLOWS.md) |
| Người vận hành | Tài liệu này → [ARCHITECTURE](ARCHITECTURE.md) → [UBUNTU_DEPLOYMENT](UBUNTU_DEPLOYMENT.md) → [ENVIRONMENT](ENVIRONMENT.md) → [OPERATIONS](OPERATIONS.md) → [DISASTER_RECOVERY](DISASTER_RECOVERY.md) |
| Người bảo trì code | Tài liệu này → [ARCHITECTURE](ARCHITECTURE.md) → [DEVELOPMENT](DEVELOPMENT.md) → [API](API.md) → [VERSIONS](VERSIONS.md) |
| Người nghiệm thu | [SECURITY](SECURITY.md) → [VALIDATION](VALIDATION.md) → [ACCEPTANCE](ACCEPTANCE.md) |

## Các sự thật phải giữ khi tiếp quản

1. **UC metadata đang hoạt động ở PostgreSQL SSD.** R2 chứa Delta files, incoming và snapshot backup; clone repo/copy `.env`/dùng cùng bucket không tự kế thừa catalog cũ.
2. **Spark local, nhiều JVM độc lập.** SQL/dbt dùng SQL service. Mỗi notebook kernel tương tác và notebook nền có Spark riêng. Chưa có shared Spark cluster, Spark Connect hoặc autoscaling.
3. **Một miền người dùng tin cậy.** UC authorization tắt; SQL dùng NOSASL; UI Permissions không thực thi RBAC. Chế độ nhiều user không tạo ranh giới dữ liệu riêng.
4. **Repo source khác repo dữ liệu làm việc.** Source gồm application, scripts, docs và template sample. Workspace chứa code notebook/dbt/workflow của người dùng; `.env`, named volumes và backup không thuộc Git source.
5. **Rebuild khác reset.** Rebuild dùng lại dữ liệu và cấu hình. `--reset-metadata` chủ động xóa UC/Kestra metadata và lịch sử/artifact local, sau preflight R2. Nó không xóa object R2 hay workspace.
6. **Backup hiện tại không nhân bản Delta data.** Xóa cả bucket có thể làm mất đồng thời dữ liệu bảng và snapshot lưu trong bucket đó. Xem [DISASTER_RECOVERY](DISASTER_RECOVERY.md).

## Thông tin triển khai và người chịu trách nhiệm

Thông tin đã được cung cấp/quan sát, không phải kết quả SSH kiểm tra host:

| Hạng mục | Giá trị / nơi lấy |
|---|---|
| Source repo | `https://github.com/cedar-f/sh-lakehouse-src.git`, nhánh main; kiểm tra lại `git remote -v` |
| Source máy dev | `D:\r2-lakehouse-v3`; đường dẫn này không bắt buộc trên máy khác |
| Source Ubuntu trong ảnh vận hành | `~/data/sh-lakehouse-src`; với root tương ứng `/root/data/sh-lakehouse-src` |
| Host đích | Ubuntu 22.04, RAM 16 GB theo người vận hành; CPU/disk/architecture cần ghi lại từ máy thật |
| Workspace thực tế | Giá trị WORKSPACE_DIR trong `.env`, không suy ra từ đường dẫn source |
| R2 bucket/endpoint | Lấy từ `.env` của host; không đưa Access Key/Secret vào bản bàn giao |
| IP/domain, SSH user/port | Người vận hành điền vào hồ sơ triển khai riêng; không dựa vào IP cũ trong ảnh chat |
| Owner hệ thống / người nhận cảnh báo | **Chưa chỉ định**; cần chốt trước vận hành lâu dài |
| Lịch backup, nơi giữ secret, bản sao Delta độc lập | **Chưa cấu hình mặc định**; cần ghi nhận quyết định |
| RPO/RTO và tải chấp nhận được | **Chưa cam kết**; đo và điền sau diễn tập restore/benchmark |

Giao quyền truy cập server, GitHub và R2 qua cơ chế quản lý quyền/secret của chủ sở hữu. Hồ sơ bàn giao ghi nơi lưu và người có quyền, không ghi mật khẩu/token trực tiếp.

## Ranh giới kiểm chứng

Đã có 87 kiểm thử Python, build frontend, regression quyền file Linux và kiểm tra UI bằng fixture. Những lần tạo/đọc Delta và restore trước đây có bằng chứng lịch sử. **Flow dbt sample mới chưa được xác nhận end-to-end trên R2 trong baseline này**, vì credential local trả Unauthorized. Tài liệu public HTTPS là cấu hình tham khảo theo nguồn chính thức, chưa được triển khai/nghiệm thu trên Ubuntu của người dùng.

Người nhận hoàn tất checklist nghiệm thu, ghi commit/hash image và kết quả mới. Một tài liệu không thay thế việc kiểm tra môi trường thật. Các bước còn trống không được coi là đã PASS.

## Thuật ngữ

| Tên | Ý nghĩa trong project |
|---|---|
| Workspace | Thư mục code dùng chung và các panel UI; không phải tài nguyên Databricks Cloud |
| Compute | Cấu hình/process Spark local; không phải cụm máy tự cấp phát |
| Catalog / schema | Namespace và metadata UC; tên bảng `catalog.schema.table` |
| Volume UC | Metadata external volume incoming trên R2; khác Docker named volume |
| Run ID | ID 32 ký tự hex của một job runner |
| Execution ID | ID execution Kestra, khác Run ID; một execution có thể liên kết nhiều run |
| dbt report | Kết quả thực thi/test trong Runs; dbt Docs là tài liệu/lineage snapshot riêng |
| Folder R2 | Prefix object key, có thể có marker 0 byte; không phải POSIX directory |
