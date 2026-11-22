# Vận hành, volume và backup

## Lệnh dùng hàng ngày

Chạy tại thư mục có compose.yaml; các lệnh Docker sau dùng được trong PowerShell lẫn Bash:

```text
docker compose ps
docker compose logs --tail=100 notebook sql runner kestra
docker stats --no-stream
docker compose stop
docker compose up -d --wait --wait-timeout 900
```

`stop` giữ container/volume. `up` bật lại; nếu source đổi, build trước hoặc dùng scripts/start.ps1, scripts/start.sh. Khi thay frontend, refresh trình duyệt để nhận bundle mới. Lưu notebook trước khi thay container. `down -v` xóa named volumes, bao gồm database metadata; không dùng làm lệnh restart thường ngày.

Kiểm tra đường dẫn notebook riêng bằng Bash helper, nếu muốn chạy notebook thật:

```bash
bash scripts/check-notebook.sh notebooks/ten_notebook_cua_ban.ipynb
```

`scripts/check.sh` là smoke test có tạo một bảng Delta thử trên R2. Chỉ chạy khi bạn muốn kiểm tra thao tác ghi thật và có kế hoạch quản lý bảng thử đó.

## Dữ liệu nằm ở đâu?

| Vị trí | Nội dung |
|---|---|
| WORKSPACE_DIR trên host → /workspace | Notebook/code, dbt và workflow JSON/YAML; ngoài repo hệ thống |
| WORKSPACE_DIR/.lakehouse/spark.json | Spark config đã lưu từ Compute; Git ignore |
| lakehouse_data:/var/lib/lakehouse/runs | Code snapshot, log, executed notebook, dbt target/log, SQL output |
| lakehouse_data:/var/lib/lakehouse/runtime | history.sqlite, workflow traces, upload session, Spark temp/warehouse/metastore phụ |
| postgres_data | Metadata đang hoạt động của UC và Kestra |
| kestra_storage, kestra_tmp | File nội bộ và working directory của Kestra |
| spark_ivy, spark_ivy_sql | Dependency Maven |
| git_ssh | SSH keys của tài khoản analyst |
| R2 warehouse/ | Delta table files và _delta_log |
| R2 incoming/ | File upload |
| R2 BACKUP_PREFIX | Snapshot phục hồi metadata/workspace/runtime |

Docker Desktop quản lý volume trong virtual disk; trên Ubuntu volume thuộc Docker data root. Xem volume của project bằng `docker volume ls` và `docker volume inspect <volume_name>`, không sửa trực tiếp file database trong volume.

## Cleanup và retention

Trong Compute → Artifact retention & cleanup, dùng **Preview cleanup** trước khi bấm **Clean eligible artifacts now**. Runner tự dọn mỗi giờ: artifact terminal quá tuổi, rồi artifact cũ nhất khi vượt quota. Metadata history được giữ lâu hơn artifact, nên run có thể còn hàng lịch sử nhưng hiện thông báo artifact hết hạn.

Các biến RUN_RETENTION_DAYS, RUN_STORAGE_MAX_GB, HISTORY_RETENTION_DAYS, RUN_LOG_MAX_MB, RUN_ARTIFACT_MAX_MB và KESTRA_RETENTION_DAYS nằm trong [ENVIRONMENT.md](ENVIRONMENT.md). Mặc định artifact 30 ngày/10 GiB; history 365 ngày. Quota này không giới hạn toàn bộ volume. Job có artifact vượt ngưỡng riêng sẽ bị dừng để hạn chế tăng dung lượng.

Temp chỉ được dọn khi run/PID tương ứng không còn chạy và thư mục đã đủ cũ. Kiểm tra PID nằm trong đúng container sở hữu. Notebook/SQL dọn orphan khi tạo Spark session; runner dọn temp của mình theo lịch. Warehouse/metastore không thuộc diện tự xóa vì có thể chứa dữ liệu cần giữ. Cache Maven cũng được giữ để các Spark session tái sử dụng.

Kestra có flow quản trị **lakehouse.maintenance.runtime_retention** chạy 03:20 mỗi ngày để purge execution terminal cũ trong lakehouse.v3 và file nội bộ liên quan. Đây là flow hệ thống, không phải ví dụ trong workspace. Container stdout log xoay vòng 10 MiB × 3; PostgreSQL dùng autovacuum mặc định và có thể giữ vùng đã giải phóng để tái sử dụng.

Khi runner khởi động lại, các job/trace còn QUEUED/RUNNING được đánh dấu INTERRUPTED, giữ partial output và không tự chạy lại. Kiểm tra dữ liệu đã ghi trước khi chủ động retry.

File `.pid` lưu mã tiến trình. PID cũ khi service đã dừng có thể dọn; không dùng xóa PID như cách dừng service. JupyterHub tùy chọn nay ghi proxy PID trong hub_state thay vì workspace. Nội dung notebook/table được lưu ở các vị trí riêng trong bảng trên.

## Backup

Trên Ubuntu/Bash:

```bash
bash scripts/backup.sh
```

Script tạm dừng writer, tạo dump UC/Kestra, tar workspace, runtime volume và Kestra storage, ghi checksum và upload R2, rồi bật lại service. Thư mục `backups/` chỉ tạo khi cần, được Git bỏ qua; cần đủ chỗ cho bản cục bộ. Sau khi kiểm tra upload/checksum trên R2, có thể xóa snapshot cục bộ đã trùng để tiết kiệm ổ; không xóa bản R2 cùng lúc. Backup gồm thông tin nhạy cảm của workspace/database; bảo vệ quyền truy cập bucket và bản lưu cục bộ.

Windows dùng Bash helper này trong Ubuntu WSL có Docker Desktop integration và truy cập được cùng project, hoặc SSH vào Ubuntu host để thực hiện. Ví dụ từ WSL:

```bash
cd /mnt/d/lakehouse
bash scripts/backup.sh
```

Thay đường dẫn bằng project thực tế. Chạy `docker compose ps` trong chính terminal đó trước để xác nhận đúng bộ container. Không dùng chuyển hướng `>` của Windows PowerShell 5.1 để lưu pg_dump binary; helper Bash xử lý binary theo luồng phù hợp.

Giữ `.env` và SSH key riêng, mã hóa và kiểm soát truy cập. Nếu bật Hub, cần backup thêm hub_home và hub_state. Backup snapshot trên R2 chưa có retention tự động của project; quản lý lifecycle ở prefix backup riêng, không áp nhầm lên warehouse/. Xem phục hồi tại [MIGRATION.md](MIGRATION.md).

## Nâng cấp

1. Lưu code/notebook và tạo backup khi cần giữ khả năng quay lại.
2. Dừng notebook, runner, SQL và Kestra; chép mã mới nhưng giữ `.env`, workspace cá nhân và named volumes.
3. Build image mới, `docker compose up -d --wait --wait-timeout 900`, kiểm tra status và SQL, rồi refresh browser.
4. Service runtime-init di chuyển run cũ từ workspace sang lakehouse_data có kiểm tra hash. Local Hive metastore/warehouse chỉ được lưu chuyển khi đã xác nhận không có bảng local. Không tự xóa các thư mục dữ liệu còn chưa rõ nguồn gốc.

Với Compose Hub, dùng nhất quán cả compose.yaml và compose.hub.yaml khi start/stop/recreate. Chi tiết migration và thứ tự backup/restore nằm trong [MIGRATION.md](MIGRATION.md).
