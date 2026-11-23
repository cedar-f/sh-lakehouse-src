# Tài liệu R2 Lakehouse

Bộ tài liệu định nghĩa hệ thống, giải thích cơ chế và hướng dẫn cài đặt/vận hành. Bắt đầu tại [HANDOVER.md](HANDOVER.md). Kết quả kiểm thử và cấu hình từng host được giữ trong hồ sơ deployment riêng.

## Lộ trình đọc theo vai trò

| Vai trò | Đọc trước | Tra cứu |
|---|---|---|
| Người dùng | [USER_GUIDE](USER_GUIDE.md), [dbt sample/report](REBUILD_DBT.md) | [Workflow logic](RUNS_WORKFLOWS.md), [Troubleshooting](TROUBLESHOOTING.md) |
| Cài Ubuntu | [Ubuntu từ đầu](UBUNTU_DEPLOYMENT.md), [Env](ENVIRONMENT.md), [Tài nguyên](RESOURCE_PLANNING.md) | [Security](SECURITY.md), [Git](GIT_SOURCE.md), [Acceptance](ACCEPTANCE.md) |
| Cài Windows | [Installation](INSTALLATION.md), [Env](ENVIRONMENT.md) | [Operations](OPERATIONS.md), [Git](GIT_SOURCE.md) |
| Vận hành | [Architecture](ARCHITECTURE.md), [Operations](OPERATIONS.md) | [DR/rollback](DISASTER_RECOVERY.md), [Migration](MIGRATION.md), [Security](SECURITY.md) |
| Bảo trì code | [Development](DEVELOPMENT.md), [API](API.md), [Versions](VERSIONS.md) | [Decisions](DECISIONS.md), [Validation](VALIDATION.md) |
| Nghiệm thu | [Requirements](REQUIREMENTS.md), [Validation](VALIDATION.md) | [Acceptance checklist](ACCEPTANCE.md), [Features](FEATURES.md) |

## Danh mục đầy đủ

| Tài liệu | Nội dung |
|---|---|
| [HANDOVER.md](HANDOVER.md) | Mục tiêu, trust boundary, mẫu hồ sơ deployment, thuật ngữ |
| [FEATURES.md](FEATURES.md) | Chức năng và giới hạn |
| [REQUIREMENTS.md](REQUIREMENTS.md) | Phạm vi chức năng và giới hạn |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Services, sequence flows, persistence, UC/R2 signer |
| [DECISIONS.md](DECISIONS.md) | Lý do, đánh đổi, việc chưa thực hiện |
| [UBUNTU_DEPLOYMENT.md](UBUNTU_DEPLOYMENT.md) | Ubuntu sạch, SSH/UFW, Git, SCP env, Docker, tunnel/HTTP/HTTPS |
| [INSTALLATION.md](INSTALLATION.md) | Windows 11 và nền tảng hai OS |
| [CATALOG_REGISTRY.md](CATALOG_REGISTRY.md) | Đồng bộ metadata lên R2, startup replay, conflict/pending và phạm vi managed |
| [ENVIRONMENT.md](ENVIRONMENT.md) | Biến env, ưu tiên config, áp dụng thay đổi |
| [RESOURCE_PLANNING.md](RESOURCE_PLANNING.md) | Ngân sách 16/32 GB, nhiều JVM, đo tải |
| [SECURITY.md](SECURITY.md) | Auth, ports, secret và public exposure |
| [GITHUB_WORKSPACE.md](GITHUB_WORKSPACE.md) | Tạo repo trên GitHub, init/clone, auto ignore, SSH agent và native Git |
| [GIT_SOURCE.md](GIT_SOURCE.md) | Hai repo source/workspace, clone/commit/push/pull |
| [USER_GUIDE.md](USER_GUIDE.md) | Notebook/SQL/Catalog/Files/Compute/Git/dbt |
| [RUNS_WORKFLOWS.md](RUNS_WORKFLOWS.md) | History/logs, workflow logic, Variables/If/For each |
| [REBUILD_DBT.md](REBUILD_DBT.md) | Bootstrap, reset, Delete, starter/report |
| [FUNCTIONS.md](FUNCTIONS.md) | SQL function trong notebook/editor/workflow, Catalog UI, definition R2, phục hồi và giới hạn |
| [DBT_PROJECTS.md](DBT_PROJECTS.md) | Catalog/schema do project quản lý, source/ref, nhiều schema và migration legacy |
| [OPERATIONS.md](OPERATIONS.md) | Theo dõi/restart/update/cleanup và incident runbook |
| [DISASTER_RECOVERY.md](DISASTER_RECOVERY.md) | Backup scope, restore drill, rollback, mất R2 |
| [MIGRATION.md](MIGRATION.md) | Chuyển host/UC và import V2 |
| [DEVELOPMENT.md](DEVELOPMENT.md) | Source map, build/test và quy trình sửa |
| [API.md](API.md) | Gateway/runner contracts, payloads, auth, limits |
| [VERSIONS.md](VERSIONS.md) | Dependencies, provenance và nâng version |
| [MULTIUSER.md](MULTIUSER.md) | JupyterHub cho nhiều tài khoản tin cậy |
| [EXTERNAL_CLIENTS.md](EXTERNAL_CLIENTS.md) | Power BI/ADF tùy chọn |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Chẩn đoán port/login/Spark/R2/permissions/Git |
| [VALIDATION.md](VALIDATION.md) | Quy trình kiểm thử theo lớp và quản lý bằng chứng |
| [ACCEPTANCE.md](ACCEPTANCE.md) | Checklist người nhận tự nghiệm thu |

## Cấu trúc và quy tắc đọc

Source gồm compose files, runtime, catalog, postgres, scripts, tests và docs. runtime/templates/dbt_sample là template hệ thống. Workspace ở WORKSPACE_DIR; database/artifact ở named volumes; chúng không thuộc repo source. `.env`/secret và cấu hình deployment local không chia sẻ bằng Git.

`docs/examples/` là **cấu hình tham khảo**: [Caddyfile](examples/Caddyfile), [proxy Compose](examples/compose.proxy.yaml), [Jupyter proxy JSON](examples/jupyter-proxy.json). Chúng không tự active khi clone. `docs/assets/` là ảnh minh họa UI, không là dữ liệu mẫu phải tồn tại trong deployment.

Lệnh mặc định chạy tại thư mục compose.yaml. Placeholder hostname/path/timestamp phải thay. Không dùng reset để upgrade/chữa credential. IP/domain/owner/RPO/RTO chưa xác nhận được ghi trong hồ sơ riêng theo HANDOVER, không điền bằng suy đoán.
