# Phát triển và bảo trì source

Đọc [ARCHITECTURE.md](ARCHITECTURE.md), [API.md](API.md) và [VERSIONS.md](VERSIONS.md) trước khi thay đổi integration. Repo chứa source hệ thống; dữ liệu làm việc thuộc repo/workspace riêng theo [GIT_SOURCE.md](GIT_SOURCE.md).

## Bản đồ source

| Nhóm file | Trách nhiệm |
|---|---|
| compose.yaml / compose.hub.yaml / compose.restore.yaml | Service graph, bind/named volumes, env, health, chế độ Hub/restore |
| runtime/Dockerfile, requirements.txt | Java/Python/Spark/dbt/Jupyter/Node và build extension; code root-owned đọc được bởi analyst |
| catalog/Dockerfile, start.sh, R2CredentialGenerator.java | UC image, PostgreSQL properties và R2 credential vending |
| postgres/init.sql | Tạo database kestra khi volume PostgreSQL mới |
| scripts/init.*, start.* | Init env/directories và build/start Windows/Bash |
| scripts/rebuild.sh, reset_metadata.py | Rebuild Ubuntu và reset metadata có flag/ownership checks |
| scripts/backup.sh, restore.sh | Pause writers, dump/restore PostgreSQL và gọi archive tool |
| scripts/hub-user.sh | Tạo user PAM/startup cho Hub, giữ state theo volume |
| runtime/config.py | Đường dẫn, timezone, Spark/UC config, identifiers và safe paths |
| spark_session.py, startup.py, start.sh | Spark notebook và SQL magic tự nạp |
| sql_server.py, sql_supervisor.py, service_readiness.py, health.py | SQL Thrift, readiness/restart và health probes |
| sql_job.py | SQL CLI subprocess của background/workflow job, lưu result.json |
| hub_config.py, start_hub.py, start_singleuser.py | PAM/Spawner, account restore và đường dẫn state/PID của Hub |
| import_v2.py, smoke_test.py | Đăng ký registry bảng V2 và smoke test có ghi dữ liệu thật |
| bootstrap.py, platform_bootstrap.py, templates/dbt_sample | R2 layout, UC namespace và sample idempotent |
| lakehouse_server.py | Jupyter auth gateway, Files/upload/Delete, artifact/Docs serving, Compute API |
| cluster_restarts.py | Save/restart coordinator cho SQL và các kernel được chọn, status polling |
| runner.py | FastAPI jobs/SQL/config/flows, subprocess và kết nối Kestra |
| execute_notebook.py, runtime_outputs.py | NBClient, cell capture, parameters và set_output |
| dbt_project.py | Bỏ qua Jupyter checkpoints khi dbt discovery |
| workflows.py / workflow_runtime.py / workflow_history.py | Compile DAG, expression/logic engine và execution history |
| run_support.py / run_store.py | Code snapshots, process capture/limits, SQLite index, logs/cells/models/artifacts |
| retention.py / migrate_runtime.py / backup_storage.py | Retention, migration có hash và snapshot archive |
| git_integration.py / git_askpass.py / labextension/github.js | Git onboarding/clone/ignore, bounded preview/commit/push và SSH agent/askpass dùng chung với native Git |
| file_deletion.py | Validate target/confirmation, active upload preflight, batch delete và partial errors |
| labextension/index.js | Đăng ký sidebar/tab, API helper và các panel chính |
| labextension/filetree.js / compute.js / workflow.js / history.js / style.css | Tree, restart UI, graph editor, history/detail và CSS |
| runtime/tests / tests | Unit/regression; UI và Docker permission checks riêng |

## Thiết lập môi trường dev

Docker Linux containers và Git đủ để build/test trong container. Không bắt buộc cài Spark/Java/dbt trên host. Thay source ở Git branch riêng, dùng workspace/bucket thử riêng nếu test ghi dữ liệu.

```bash
git switch -c feature/ten-thay-doi
docker build -t r2-lakehouse-v3-runtime:local runtime
```

Build trực tiếp runtime không cần `.env` và không gọi R2; cần Internet cho image/package. Để chạy cả stack, cấu hình `.env` và dùng start/rebuild theo tài liệu cài đặt. Không mount Docker socket vào notebook/runner để làm shortcut điều khiển cluster.

## Kiểm thử và tác động

### Unit và contract tests — không cần R2

Sau khi có runtime image, chạy tại root repo (Bash hoặc PowerShell):

```bash
docker run --rm --user root -v "${PWD}:/project:ro" -w /project -e PYTHONPATH=/project/runtime r2-lakehouse-v3-runtime:local python3 -m pytest -p no:cacheprovider runtime/tests tests/test_reset_metadata.py -q
```

Suite gồm unit/fake storage/API contract tests và Git/SSH local integration; không thay thế integration trên deployment R2/Ubuntu/GitHub thật. Nhóm chính: workflow validation/semantics, notebook capture, log/history/retention, temp ownership, restart/readiness, backup archive, bounded deletion, idempotent bootstrap và reset volume ownership. Các test reset không xóa Docker volume thật.

### Regression quyền file Linux

```bash
python3 tests/image_permissions.py
```

Windows dùng `python` nếu Python 3 đã cài. Test build hai image tag `r2-lakehouse-permissions-runtime:test` và `r2-lakehouse-permissions-catalog:test` từ source mode 600/700, kiểm tra bằng user non-root, không gọi R2 hoặc dùng data volume. Cần Docker và mạng build; không tự chạy trong pytest suite ở trên.

### UI và integration có tác động thật

Trong virtualenv riêng, cài `tests/requirements-ui.txt`, cài Chromium bằng `python -m playwright install chromium`, rồi chạy UI script khi stack thử đã sẵn sàng. Script đọc `.env` ở root repo; LAKEHOUSE_TEST_URL và LAKEHOUSE_TEST_BROWSER là tùy chọn của UI tests, không phải biến app.

| Lệnh | Điều cần biết trước khi chạy |
|---|---|
| `python tests/ui_tabs_files.py` | Ghi object thử dưới incoming prefix ngẫu nhiên, kiểm tra tree/upload và cleanup các key thử |
| `python tests/ui_compute_restart.py` | Restart/configure Spark và thao tác notebook; dùng môi trường riêng, đọc fixture/cleanup trong script |
| `python tests/ui_git_setup.py` | Tạo/xóa container Docker riêng với repo bare local; kiểm GitHub wizard, key encrypted, native Git và restart. Không đọc .env hoặc gọi GitHub/R2. LAKEHOUSE_GIT_TEST_IMAGE chọn runtime image |
| `bash scripts/check.sh` | Smoke test có ghi Delta table thật; cần kế hoạch dọn table thử |
| `bash scripts/check-notebook.sh notebooks/my_job.ipynb` | Thực thi notebook thật và mọi side effect trong notebook |

Chưa có pipeline CI/CD trong repo. Không mô tả UI test hoặc R2 integration như tự chạy trên mỗi commit. Mẫu dbt và checklist integration nằm tại [ACCEPTANCE.md](ACCEPTANCE.md).

## Quy trình sửa một chức năng

1. Tạo nhánh và ghi trigger/behavior mong muốn; chọn test kiểm tra lỗi thực tế.
2. Xác định module UI/API/runner/storage liên quan từ bảng trên. Thay API phải sửa cả contract docs và caller.
3. Chạy unit liên quan rồi suite khi thay shared config/history/runner. Chỉ dùng sandbox R2 cho thao tác ghi/xóa.
4. Build image; backend/frontend được COPY vào image, không hot reload từ source host. Java adapter đổi thì build catalog nữa.
5. Lưu notebook, chờ job kết thúc và rebuild stack thử; xác nhận health/UI. Cập nhật quy trình [VALIDATION.md](VALIDATION.md) nếu contract đổi; kết quả/log thực tế giữ trong hồ sơ kiểm thử riêng.
6. Commit source đã rà soát, không commit `.env`, key, workspace, named volume hay artifact. Cập nhật tài liệu định nghĩa/hướng dẫn liên quan khi thay hành vi.

### Khi thêm task workflow

Cập nhật graph editor trường nhập, `workflows.compile_flow()` cho native/advanced detection, `workflow_runtime.validate/render/execute_workflow`, runner payload allowlist/dispatch và history type. Test dependencies/branch, retry, output size, error handler và terminal status. Node chạy SQL/dbt/notebook có thể ghi dữ liệu trước khi lỗi; retry không tự rollback side effects.

### Khi sửa Files/Delete

Giữ boundary incoming, confirmation, batch <=1000 và xử lý partial errors. Không dùng continuation token cũ để vừa xóa vừa duyệt phần còn lại. Không biến Delete thành xóa warehouse trực tiếp; DDL phải đồng bộ UC/Delta. Preflight multipart không phải transaction lock với browser/session khác.

### Khi sửa Spark/UC/R2

Kiểm tra exact Maven coordinates và classpath SQL Thrift. Xác minh CREATE TABLE/SELECT bằng tên ba phần, schema mới sau session đã mở, SQL/dbt fresh session và R2 scoped credential read/write. Cấu hình RAM riêng theo service chưa được thực hiện: sửa `.env` hoặc gắn thêm biến tùy ý không tự tạo tính năng đó.

## Quy ước bảo trì

- Shell script LF và PowerShell 5.1-compatible; dùng `bash script.sh` trên Ubuntu, không phụ thuộc executable bit của Git checkout.
- Giữ code image root-owned, runtime user đọc/traverse được; private data/secret áp quyền riêng.
- UI dùng DOM text cho dữ liệu người dùng. Notebook HTML output được sandbox, không nới CSP/artifact path validation để chữa lỗi hiển thị.
- Timestamp lưu epoch/ISO theo nguồn; UI diễn giải filter theo TZ. Không đổi timezone bằng cách cộng thủ công 7 giờ.
- Config ưu tiên `.lakehouse/spark.json` hơn env; không ghi đè file này khi upgrade.
- Package versions, Java image và mutable Node/Maven inputs cần kiểm tra khi upgrade; frontend chưa có lockfile commit.
- Frontend package ghi license MIT nhưng repo chưa có LICENSE ở gốc. Chủ sở hữu quyết định license toàn repo; không tự gán theo một package hoặc dependency.
