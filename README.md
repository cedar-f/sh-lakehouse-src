# R2 Lakehouse V3.1.3

Workspace phân tích tự host bằng Docker: JupyterLab/Lakehouse extension, Spark/Delta Lake, Unity Catalog OSS/PostgreSQL, Cloudflare R2, dbt và Kestra. Source dùng chung cho Ubuntu 22.04 host và Windows 11 dev.

**Người mới bắt đầu tại [docs/HANDOVER.md](docs/HANDOVER.md).** Mục lục theo vai trò: [docs/README.md](docs/README.md).

| Nhu cầu | Tài liệu |
|---|---|
| Ubuntu từ Git, copy env, SSH/public | [UBUNTU_DEPLOYMENT](docs/UBUNTU_DEPLOYMENT.md) |
| Windows, R2, RAM/CPU | [INSTALLATION](docs/INSTALLATION.md), [ENVIRONMENT](docs/ENVIRONMENT.md), [RESOURCE_PLANNING](docs/RESOURCE_PLANNING.md) |
| dbt sample/report, Delete, rebuild | [REBUILD_DBT](docs/REBUILD_DBT.md) |
| Notebook/SQL/workflow | [USER_GUIDE](docs/USER_GUIDE.md), [RUNS_WORKFLOWS](docs/RUNS_WORKFLOWS.md) |
| Bảo trì code/API | [DEVELOPMENT](docs/DEVELOPMENT.md), [API](docs/API.md), [ARCHITECTURE](docs/ARCHITECTURE.md) |
| Vận hành/backup/chuyển host | [OPERATIONS](docs/OPERATIONS.md), [DISASTER_RECOVERY](docs/DISASTER_RECOVERY.md) |
| Trạng thái/nghiệm thu | [VALIDATION](docs/VALIDATION.md), [ACCEPTANCE](docs/ACCEPTANCE.md), [CHANGELOG](CHANGELOG.md) |

## Phạm vi quan trọng

- Spark local với JVM riêng cho SQL, từng kernel và notebook nền; chưa shared cluster/autoscaling.
- UC metadata ở PostgreSQL. R2 chứa Delta, incoming và snapshot; cùng bucket không tự kế thừa catalog.
- UC authorization tắt, SQL NOSASL; miền người dùng tin cậy. Public access theo [SECURITY](docs/SECURITY.md).
- Snapshot script không nhân bản toàn bộ Delta data; cần data backup độc lập.
- Phần chưa nghiệm thu/triển khai được ghi tại [REQUIREMENTS](docs/REQUIREMENTS.md).

Repo gồm source/template, không có notebook/dbt cá nhân, `.env`, database volume hay backup. Bootstrap tạo dbt_sample/dbt_sample_pipeline khi thiếu, không ghi đè hoặc tự chạy; tắt bằng SEED_SAMPLE_DBT=false.

Init mới: Ubuntu `bash scripts/init.sh`; Windows `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/init.ps1`. Điền env/chọn RAM trước start; hướng dẫn và điều kiện nghiệm thu trong docs, không cần lịch sử chat.
