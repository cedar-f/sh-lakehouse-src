# R2 Lakehouse V3.1.3

Workspace phân tích tự host bằng Docker: JupyterLab/Lakehouse extension, Spark/Delta Lake, Unity Catalog OSS/PostgreSQL, Cloudflare R2, dbt và Kestra. Source dùng chung cho Ubuntu 22.04 host và Windows 11 dev.

**Người mới bắt đầu tại [docs/HANDOVER.md](docs/HANDOVER.md).** Mục lục theo vai trò: [docs/README.md](docs/README.md).

| Nhu cầu | Tài liệu |
|---|---|
| Ubuntu từ Git, copy env, SSH/public | [UBUNTU_DEPLOYMENT](docs/UBUNTU_DEPLOYMENT.md) |
| Windows, R2, RAM/CPU | [INSTALLATION](docs/INSTALLATION.md), [ENVIRONMENT](docs/ENVIRONMENT.md), [RESOURCE_PLANNING](docs/RESOURCE_PLANNING.md) |
| dbt sample/report, Delete, rebuild | [REBUILD_DBT](docs/REBUILD_DBT.md) |
| Notebook/SQL/workflow | [USER_GUIDE](docs/USER_GUIDE.md), [RUNS_WORKFLOWS](docs/RUNS_WORKFLOWS.md), [GitHub workspace](docs/GITHUB_WORKSPACE.md) |
| Bảo trì code/API | [DEVELOPMENT](docs/DEVELOPMENT.md), [API](docs/API.md), [ARCHITECTURE](docs/ARCHITECTURE.md) |
| Vận hành/backup/chuyển host | [OPERATIONS](docs/OPERATIONS.md), [DISASTER_RECOVERY](docs/DISASTER_RECOVERY.md) |
| Trạng thái/nghiệm thu | [VALIDATION](docs/VALIDATION.md), [ACCEPTANCE](docs/ACCEPTANCE.md) |

## Phạm vi quan trọng

- Spark local với JVM riêng cho SQL, từng kernel và notebook nền; chưa shared cluster/autoscaling.
- dbt project có thể tự khai báo catalog và schema theo model/nhóm, chạy nhiều schema qua source/ref; xem [DBT_PROJECTS](docs/DBT_PROJECTS.md).
- UC chạy trên PostgreSQL; registry JSON trên R2 tự phục hồi catalog/schema rỗng, comment/properties/root, external assets và function definitions vào UC mới. Managed assets được giữ inventory và báo chưa phục hồi. Xem [CATALOG_REGISTRY](docs/CATALOG_REGISTRY.md).
- SQL scalar functions tạo và gọi bằng tên ba phần trong notebook, SQL editor và workflow SQL; định nghĩa tự lưu UC/R2 và nạp lại sau Spark restart. Xem cú pháp/phạm vi tại [FUNCTIONS](docs/FUNCTIONS.md).
- SQL views native UC có definition/dependency, preview/copy/delete và portable registry R2. Runtime dùng Spark 4.2/Delta 4.4; xem giới hạn replace/dbt và nâng cấp tại [VIEWS](docs/VIEWS.md), [VERSIONS](docs/VERSIONS.md). Files có copy file/folder path và metadata chi tiết theo [FILES](docs/FILES.md).
- UC authorization tắt, SQL NOSASL; miền người dùng tin cậy. Public access theo [SECURITY](docs/SECURITY.md).
- Snapshot script không nhân bản toàn bộ Delta data; cần data backup độc lập.
- Phần chưa nghiệm thu/triển khai được ghi tại [REQUIREMENTS](docs/REQUIREMENTS.md).

Repo gồm source/template, không có notebook/dbt cá nhân, `.env`, database volume hay backup. Bootstrap tạo dbt_sample/dbt_sample_pipeline khi thiếu, không ghi đè hoặc tự chạy; tắt bằng SEED_SAMPLE_DBT=false.

Init mới: Ubuntu `bash scripts/init.sh`; Windows `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/init.ps1`. Điền env/chọn RAM trước start; hướng dẫn theo vai trò và điều kiện nghiệm thu nằm trong docs.
