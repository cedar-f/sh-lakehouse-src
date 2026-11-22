# R2 Lakehouse V3.1.3

Lakehouse tự host bằng Docker, dùng Spark/Delta Lake, Unity Catalog OSS, R2, dbt và Kestra; giao diện chính là JupyterLab với extension Lakehouse.

**Tài liệu bắt đầu tại [docs/README.md](docs/README.md).**

V3.1.3: Delete file/folder trong incoming, bootstrap prefix R2 khi thiếu và project/workflow dbt sample. Hướng dẫn cập nhật từ Git, rebuild/reset và xem report: [docs/REBUILD_DBT.md](docs/REBUILD_DBT.md).

- [Đưa source hệ thống lên GitHub, tách workspace riêng](docs/GIT_SOURCE.md)
- [Tính năng và giới hạn](docs/FEATURES.md)
- [Cài đặt Windows 11 / Ubuntu 22.04](docs/INSTALLATION.md)
- [Cấu hình .env, R2, RAM/CPU và timezone](docs/ENVIRONMENT.md)
- [Sử dụng notebook, SQL, Catalog, Files, Git và dbt](docs/USER_GUIDE.md)
- [Workflow, run history và ví dụ Variables / If / For each](docs/RUNS_WORKFLOWS.md)
- [Vận hành, cleanup và backup](docs/OPERATIONS.md)
- [Xử lý lỗi](docs/TROUBLESHOOTING.md)

Repository này chỉ lưu source dựng hệ thống và template dbt mẫu. `workspace/`, `.env`, database và backup được Git bỏ qua. Trên máy dev, workspace hiện tại cùng Git cũ đã được giữ riêng tại `../r2-lakehouse-data/workspace`, cấu hình qua `WORKSPACE_DIR`. Cài mới sinh project `dbt_sample` và flow `dbt_sample_pipeline` khi chưa có; có thể tắt bằng SEED_SAMPLE_DBT=false. Không chứa code cá nhân của workspace đang dùng.

Khởi tạo Windows: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/init.ps1`; Ubuntu: `bash scripts/init.sh`. Điền `.env` theo tài liệu trước khi chạy script start tương ứng.
