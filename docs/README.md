# Tài liệu R2 Lakehouse V3.1.1

Đây là bộ lakehouse tự host bằng Docker: JupyterLab với extension Lakehouse, Spark/Delta Lake, Unity Catalog OSS, PostgreSQL, Cloudflare R2, dbt và Kestra. Tài liệu phản ánh bản project hiện tại; cập nhật ngày 22/11/2026.

## Bắt đầu từ đâu?

| Nhu cầu | Tài liệu |
|---|---|
| Đưa source lên GitHub, tách repo workspace | [GIT_SOURCE.md](GIT_SOURCE.md) |
| Hiểu tính năng, kiến trúc và giới hạn | [FEATURES.md](FEATURES.md) |
| Đối chiếu tiêu chí hệ thống | [REQUIREMENTS.md](REQUIREMENTS.md) |
| Cài trên Windows 11 hoặc Ubuntu 22.04 | [INSTALLATION.md](INSTALLATION.md) |
| Điền R2, token, RAM/CPU, port, timezone, retention | [ENVIRONMENT.md](ENVIRONMENT.md) |
| Dùng Catalog, Files, notebook/SQL, Git và dbt | [USER_GUIDE.md](USER_GUIDE.md) |
| Workflow, Variables/If/For each, lịch và log | [RUNS_WORKFLOWS.md](RUNS_WORKFLOWS.md) |
| Start/stop, Docker volume, cleanup, backup/restore | [OPERATIONS.md](OPERATIONS.md) |
| Chuyển host, kế thừa catalog, dữ liệu V2 | [MIGRATION.md](MIGRATION.md) |
| Xử lý lỗi thường gặp | [TROUBLESHOOTING.md](TROUBLESHOOTING.md) |
| Nhiều tài khoản trong workspace tin cậy | [MULTIUSER.md](MULTIUSER.md) |
| Power BI và ADF tùy chọn | [EXTERNAL_CLIENTS.md](EXTERNAL_CLIENTS.md) |
| Phạm vi đã kiểm chứng và đợt cleanup | [VALIDATION.md](VALIDATION.md) |

## Cấu trúc project

```text
compose.yaml                Dịch vụ mặc định
compose.hub.yaml            Chế độ JupyterHub tùy chọn
.env.example                Mẫu cấu hình; scripts/init tạo .env riêng
scripts/                    Init/start Windows và Ubuntu; công cụ vận hành
runtime/                    Spark, runner, extension UI và kiểm thử
catalog/                    Unity Catalog + tích hợp credential R2
postgres/                   Khởi tạo database
workspace/                  Dữ liệu mặc định khi chạy; không nằm trong Git
                            Có thể đổi bằng WORKSPACE_DIR để đặt ngoài source
docs/                       Bộ tài liệu này
  assets/                   Ảnh minh họa
  history/                  Bằng chứng kiểm thử các bản trước
backups/                    Chỉ tạo khi backup/restore; được Git bỏ qua
```

Source trên Git không chứa notebook, project dbt hay workflow đang làm của bạn. Workspace hiện tại được giữ riêng tại `../r2-lakehouse-data/workspace`, bao gồm Git cũ, code cá nhân và **variable_if_foreach_demo**. Cài mới từ Git tạo workspace trống; hướng dẫn tạo ví dụ nằm trong tài liệu. Lịch sử execution/run có retention riêng.

Dùng một bộ source cho Windows và Ubuntu; không cần duy trì bản sao source riêng cho từng hệ điều hành. Các lệnh trong tài liệu chạy tại thư mục chứa `compose.yaml`. Git ở gốc quản lý hệ thống; Git panel trong Jupyter quản lý code trong workspace.
