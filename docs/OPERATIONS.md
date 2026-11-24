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

## Theo dõi portable UC registry

Compute → Catalog registry on R2 cho biết sync/pending/counts và managed inventory chưa replay. Có thể dùng `docker compose exec -T registry python3 /opt/lakehouse/registry_service.py status` hoặc sync. Trước reset local, đảm bảo registry đã lưu đúng metadata cần giữ; khi UC trống sẽ replay trước bootstrap. Không xóa current.json hoặc đổi prefix để chữa lỗi auth/conflict nếu chưa xác định nguồn đúng. Reconcile mặc định mỗi 60 giây, chỉ PUT khi metadata thay đổi; có GET ETag mỗi lần sync. Xem [CATALOG_REGISTRY](CATALOG_REGISTRY.md).

## Git sau recreate hoặc chuyển host

Key single-user được giữ ở git_ssh; encrypted key cần mở lại trong GitHub → Unlock SSH key sau khi agent/container restart. Kiểm tra status Key loaded trước push từ Jupyter Git. Key của host pull source và key analyst push workspace là hai phạm vi riêng. Backup/restore key theo [DISASTER_RECOVERY](DISASTER_RECOVERY.md); Hub dùng key trong home của user. Cập nhật onboarding xem [GITHUB_WORKSPACE](GITHUB_WORKSPACE.md).

## Artifact cleanup và retention

Trong Compute → Artifact retention & cleanup, dùng **Preview cleanup** trước khi bấm **Clean eligible artifacts now**. Runner tự dọn mỗi giờ: artifact terminal quá tuổi, rồi artifact cũ nhất khi vượt quota. Metadata history được giữ lâu hơn artifact, nên run có thể còn hàng lịch sử nhưng hiện thông báo artifact hết hạn.

Các biến RUN_RETENTION_DAYS, RUN_STORAGE_MAX_GB, HISTORY_RETENTION_DAYS, RUN_LOG_MAX_MB, RUN_ARTIFACT_MAX_MB và KESTRA_RETENTION_DAYS nằm trong [ENVIRONMENT.md](ENVIRONMENT.md). Mặc định artifact 30 ngày/10 GiB; history 365 ngày. Quota này không giới hạn toàn bộ volume. Job có artifact vượt ngưỡng riêng sẽ bị dừng để hạn chế tăng dung lượng.

Temp chỉ được dọn khi run/PID tương ứng không còn chạy và thư mục đã đủ cũ. Kiểm tra PID nằm trong đúng container sở hữu. Notebook/SQL dọn orphan khi tạo Spark session; runner dọn temp của mình theo lịch. Warehouse/metastore không thuộc diện tự xóa vì có thể chứa dữ liệu cần giữ. Cache Maven cũng được giữ để các Spark session tái sử dụng.

Kestra có flow quản trị **lakehouse.maintenance.runtime_retention** chạy 03:20 mỗi ngày để purge execution terminal cũ trong lakehouse.v3 và file nội bộ liên quan. Đây là flow hệ thống, không phải ví dụ trong workspace. Container stdout log xoay vòng 10 MiB × 3; PostgreSQL dùng autovacuum mặc định và có thể giữ vùng đã giải phóng để tái sử dụng.

Khi runner khởi động lại, các job/trace còn QUEUED/RUNNING được đánh dấu INTERRUPTED, giữ partial output và không tự chạy lại. Kiểm tra dữ liệu đã ghi trước khi chủ động retry.

File `.pid` lưu mã tiến trình. PID cũ khi service đã dừng có thể dọn; không dùng xóa PID như cách dừng service. JupyterHub tùy chọn ghi proxy PID trong hub_state thay vì workspace. Nội dung notebook/table được lưu ở các vị trí riêng trong bảng trên.

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

## Runbook sự cố theo dấu hiệu

| Dấu hiệu | Kiểm tra trước | Hướng xử lý |
|---|---|---|
| Không SSH được sau firewall | Console, listener thực tế, UFW và provider/router | Mở đúng SSH port trước; login phiên mới, không reset firewall toàn bộ |
| Local UI được nhưng public không | Bind 127/0.0, upstream rules/NAT/DNS | Theo [Ubuntu deployment](UBUNTU_DEPLOYMENT.md); UFW không đủ để kết luận Docker port đã private |
| UI không login / Kestra prompt | Đúng env/token/email; Basic auth/cookie; service logs | Không tắt auth để chữa login; nếu secret đổi, recreate process liên quan |
| Bootstrap fail | `docker compose logs --tail=100 bootstrap catalog` | PermissionError → hotfix image; Unauthorized → R2 fields/permission/clock; không reset để chữa auth |
| SQL STARTING/FAILED | Compute status, `docker compose logs --tail=100 sql catalog` | Catalog/Maven/R2/JVM readiness; Save & Restart đúng scope sau sửa config |
| Container restart / OOM | docker stats, free -h, State.OOMKilled, logs JVM/Python | Giảm kernel/job, kiểm driver heap vs cap và config đã lưu; không tăng đồng loạt vượt host |
| Disk đầy | df -h, docker system df, artifact cleanup preview, local backups | Dọn eligible artifacts hoặc snapshot local đã xác minh; không prune DB/key/warehouse tùy tiện |
| Table có trong catalog nhưng đọc lỗi Delta | Location, R2 keys, _delta_log, credential | Dữ liệu R2 bị xóa không sửa được bằng refresh; dùng kế hoạch data recovery |
| Workflow FAILED nhưng thiếu chi tiết ở Kestra | Workflow Run History và linked Run IDs | Advanced flow chạy trong runner; xem Models/Cells/Logs của run con |
| History còn nhưng artifact 404 | artifacts_expired và retention | Đây có thể là hết retention; metadata history không bảo đảm giữ file |

## Kiểm tra vận hành và owner

Hằng ngày hoặc theo lịch đã thống nhất: service status/SQL SELECT 1, RAM available, disk Docker/temp, backup gần nhất, workflow failures và log retention. Chưa có hệ thống metrics/alert tập trung trong repo; người vận hành phải ghi người theo dõi và phương thức báo lỗi trong HANDOVER.

```bash
docker compose ps -a
docker stats --no-stream
free -h
df -h
docker system df
docker compose logs --tail=100 sql runner kestra
```

Kiểm tra sau reboot: Docker service chạy, containers đạt readiness, one-shot đã kết thúc thành công và Kestra login/query thực sự được. unless-stopped không hứa bật lại container đã bị chủ động stop trước reboot. Job bị gián đoạn không tự replay; kiểm side effects trước retry.

Ngưỡng ban đầu như available RAM thấp hơn 1–2 GiB hoặc Docker filesystem gần đầy là tín hiệu điều tra, không SLA/cap đã enforce. Theo dõi workload đại diện và điều chỉnh threshold có ghi nhận.

## Upgrade và rollback có kiểm soát

Ghi commit/image IDs, giữ cấu hình private và snapshot phù hợp; worktree sạch trước git pull --ff-only. Lưu notebook/chờ job, rebuild theo script, nghiệm thu query/dbt/UI rồi mới coi deployment đạt. Proxy/Hub cần dùng cùng Compose layers; COMPOSE_FILE/proxy local là phần config bàn giao.

Rollback code và restore state là hai thao tác khác nhau. Hướng dẫn điều kiện/command, backup scope, diễn tập restore và giới hạn khi mất Delta nằm trong [DISASTER_RECOVERY.md](DISASTER_RECOVERY.md). Snapshot hiện tại không nhân bản toàn warehouse; backup và cron chưa tự bật. Không dùng reset-metadata như bước upgrade.

Các thao tác table cleanup/VACUUM cần chính sách Delta và reader retention riêng. DROP TABLE/location external có semantics khác managed; kiểm metadata và storage sau thao tác, không suy ra free disk/object chỉ từ việc table biến mất trong Catalog.

## Nâng cấp Catalog functions, views và registry

Upgrade bằng git pull và rebuild thông thường, không reset metadata. Đợi registry healthy, kiểm Compute counts/functions và Sync trước khi dựng lại host. Manifest v1 tự nâng ít nhất v2, lên v3 khi có SQL views, tại cùng key bằng conditional PUT; code cũ không đọc version mới. Function/view definition được replay, không thực thi code/query khi startup. Nếu cần rollback, dừng writers/registry và dùng quy trình restore/registry disabled trong [DISASTER_RECOVERY](DISASTER_RECOVERY.md), không sửa version manifest bằng tay. Xem [FUNCTIONS](FUNCTIONS.md), [VIEWS](VIEWS.md).

Sau nâng cấp managed SQL functions, restart notebook kernel để nạp wrapper `spark.sql`; SQL/runner cần image mới. Chạy thử CREATE/SELECT trong namespace sandbox và gọi lại sau restart Spark. UC/R2 data/metadata hiện có được giữ. Nếu OR REPLACE lỗi, đọc lại function và kiểm registry status/logs trước retry: state có thể giữ `function_replacement` intent để phục hồi an toàn. Sửa lỗi kết nối rồi Sync lại; không xóa marker/database hay tự sửa current.json. Raw Thrift/dbt không tự sử dụng adapter notebook/runner.

Native views nâng runtime lên Spark 4.2/Delta 4.4: lưu notebooks, chờ job kết thúc, kiểm disk trống tối thiểu theo rebuild preflight, `git pull --ff-only` rồi `bash scripts/rebuild.sh`. Cần build image, không chỉ restart/no-build. Không dùng --reset-metadata. Kiểm Extra Spark config không override Maven coordinates cũ; xem [VERSIONS](VERSIONS.md). Cache Maven tách phiên bản và giữ cache cũ; lần khởi động đầu tải package trước final JVM nên chờ logs tiến triển thay vì reset volume. Sau healthy, restart kernel và Ctrl+F5 trình duyệt, kiểm table/view query, dbt build/docs và registry sync. Ngân sách RAM container không tự tăng khi nâng Spark.
