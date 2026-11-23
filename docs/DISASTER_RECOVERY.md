# Backup, restore, rollback và mất dữ liệu

Đối tượng: người vận hành, single-user Compose mặc định. Đọc [ARCHITECTURE.md](ARCHITECTURE.md), [SECURITY.md](SECURITY.md) và xác nhận đúng Compose project/host trước thao tác. Hub cần giữ thêm hub_home/hub_state; script backup mặc định không đóng gói hai volume đó.

## Portable metadata và database backup

Registry R2 tự phục hồi một phần định nghĩa UC vào UC trống theo [CATALOG_REGISTRY](CATALOG_REGISTRY.md); không phục hồi full database, managed identity, Kestra, workspace hoặc lịch sử. Với restore database snapshot bên dưới, đặt UC_REGISTRY_ENABLED=false trước restore; sau nghiệm thu DB chọn registry prefix mới rồi bật lại để không để snapshot cũ ghi đè registry mới hơn.

## Phạm vi backup hiện có

`scripts/backup.sh` dừng notebook/runner/sql/kestra/registry/catalog, giữ PostgreSQL chạy để pg_dump, rồi đóng gói workspace, runtime và Kestra storage. Script có EXIT trap bật lại service kể cả khi backup lỗi. Lưu notebook và chờ job hoàn tất trước khi chạy để tránh ngắt công việc đang ghi.

| File trong snapshot | Nội dung |
|---|---|
| unitycatalog.dump | UC metadata PostgreSQL |
| kestra.dump | Kestra metadata/executions PostgreSQL |
| workspace.tar.gz | Toàn bộ workspace, gồm code/Git và config đã lưu |
| runtime.tar.gz | lakehouse_data: artifact/history/workflow traces/upload sessions/local runtime |
| kestra-storage.tar.gz | File storage Kestra |
| manifest.json | Version 3, bucket, timestamp UTC và SHA-256 từng archive/dump |

Root `.env`, git_ssh, hub_home/hub_state và Delta data trên R2 không được sao thành các archive trong bảng. Secret nào người dùng đặt **bên trong workspace** vẫn có thể nằm trong tar; bảo vệ snapshot như dữ liệu nhạy cảm. Script không sao lại toàn bộ R2 warehouse/incoming sang nơi độc lập.

**Nếu xóa cả bucket, metadata backup trong cùng bucket cũng có thể mất.** Nếu chỉ xóa Delta object, restore PostgreSQL không tạo lại dữ liệu. Cần một kế hoạch sao chép Delta/incoming và snapshot sang storage/account độc lập theo yêu cầu của chủ sở hữu; repo chưa cung cấp replication đó.

## Tạo snapshot và giữ secret riêng

Chạy trong Bash trên Ubuntu hoặc WSL đã kết nối đúng Docker engine:

```bash
cd ~/data/sh-lakehouse-src
docker compose ps
bash scripts/backup.sh
```

Ghi timestamp script in ra. Snapshot nằm ở `BACKUP_PREFIX/<UTC_TIMESTAMP>/` trên R2 và `backups/<UTC_TIMESTAMP>/` local. Manifest upload sau các file. Kiểm tra exit code, service được bật lại, đủ file trên R2 và kiểm checksum/readback khi diễn tập; có file local chưa chứng minh upload đã hoàn tất.

Để xuất root env và Git SSH volume vào thư mục private trên host (thực hiện có chủ đích, chưa mã hóa):

```bash
install -d -m 700 ~/lakehouse-private
install -m 600 .env ~/lakehouse-private/platform.env
(umask 077; docker compose run -T --rm --no-deps --user root notebook tar -czf - -C /home/analyst/.ssh . > ~/lakehouse-private/git-ssh.tar.gz)
```

Mã hóa/chuyển bản private tới nơi quản lý secret được chỉ định; thư mục trên cùng host không bảo vệ khi mất host. Với GitHub deploy key trên host, giữ riêng `~/.ssh/lakehouse_git` và config/known_hosts cần thiết, hoặc sẵn sàng tạo/ủy quyền key mới. Không commit các file này. Snapshot local có thể dọn sau khi bản remote được xác minh; prefix backup trên R2 chưa có retention tự động trong project.

## Phục hồi sang host mới

1. Đóng writer host cũ; giữ nó dừng trong thời gian chuyển. Chuẩn bị Ubuntu/Git/Docker theo [UBUNTU_DEPLOYMENT.md](UBUNTU_DEPLOYMENT.md).
2. Checkout version phù hợp với snapshot. Chuẩn bị `.env` cùng bucket/BACKUP_PREFIX, endpoint, credential hợp lệ và password khớp với volume DB của host đích. Host mới hoàn toàn có thể dùng password DB mới cho PostgreSQL mới; restore dùng cùng role lakehouse.
3. Chọn workspace/volumes đích sạch và kiểm đúng project name. Restore archive **ghi đè file cùng tên nhưng không xóa mọi file thừa**; không merge vào workspace/state quan trọng không liên quan. Chuẩn bị backup riêng của host đích nếu đang có dữ liệu.
4. Build image và restore bằng timestamp thật của snapshot:

```bash
cd ~/data/sh-lakehouse-src
bash scripts/init.sh
docker compose config --quiet
docker compose build
bash scripts/restore.sh 20261122T000000Z --replace-metadata
```

Timestamp trên chỉ minh họa, phải thay bằng snapshot đã xác minh. Flag replace-metadata chủ động thay UC/Kestra metadata trên host đích; đây không phải lệnh restart. Khi dùng proxy override, cấu hình local/COMPOSE_FILE cần tồn tại ở host mới trước khi dùng Compose.

Restore tải manifest, kiểm version/bucket/danh sách file và SHA-256 rồi extract archive có kiểm path; sau đó pg_restore cả hai database, chuẩn hóa quyền và start. Snapshot cũ không có runtime.tar.gz vẫn được chấp nhận. Backup chứa symlink/hardlink không được phục hồi qua tar extraction này.

5. Khôi phục private root env/SSH/Hub state bằng cơ chế quản trị riêng nếu cần. Git key mới cần add lại quyền GitHub; đừng ghi đè key còn dùng mà chưa kiểm tra.
6. Nghiệm thu trước khi cho ghi thật:

```text
[ ] PostgreSQL/catalog/notebook/sql/runner đạt health; Kestra login được.
[ ] List đúng catalog/schema/table cũ và location vẫn trỏ cùng R2.
[ ] SELECT một table có dữ liệu đã biết: số dòng, cột, tổng kiểm tra đúng.
[ ] Mở notebook/dbt/workflow đã lưu; không tự bật lại schedule ghi dữ liệu trước kiểm tra.
[ ] Runs/artifacts còn trong snapshot đọc được; timezone đúng.
[ ] Kiểm tra Git access, Files và cấu hình Spark của workspace.
[ ] Host cũ không đang ghi; ghi commit/image IDs và thời gian restore thực tế.
```

R2 Delta log có thể đã tiến xa hơn snapshot metadata. Restore metadata cũ không tự đưa Delta data về version tại timestamp snapshot; cần kiểm tra schema/location và chọn chiến lược phục hồi data riêng nếu có lệch.

## Rollback một lần nâng code

Trước nâng cấp, ghi `git rev-parse HEAD`, image IDs, config private và tạo snapshot cần thiết. Giữ image/backup tốt cho tới khi nghiệm thu. Không prune volume hoặc cache image ngay khi đang thử rollback.

Nếu xác nhận code cũ tương thích metadata/config hiện tại, có thể rollback **code** ở cùng thư mục:

```bash
git status --short
docker compose stop notebook runner sql kestra registry catalog
git switch --detach GOOD_COMMIT
bash scripts/start.sh
```

Thay GOOD_COMMIT bằng commit đã chạy tốt. Chỉ làm khi worktree sạch/đã lưu thay đổi. Không dùng git reset hard để bỏ công việc đang có. Kiểm tra lại `.env`/COMPOSE_FILE và local proxy file có phù hợp commit cũ; named volumes, workspace và R2 không tự quay về trạng thái cũ.

Nếu đã nâng schema UC/Kestra/PostgreSQL không tương thích ngược, checkout code cũ không đủ. Dừng writers và diễn tập restore snapshot tương ứng trên môi trường tách biệt trước; không downgrade DB version trên volume hiện tại theo suy đoán. Xem [VERSIONS.md](VERSIONS.md).

## Xóa R2 khác reset local metadata

`bash scripts/rebuild.sh --reset-metadata` xóa đúng bốn local metadata/runtime volumes sau preflight R2, giữ workspace/key/cache và mọi object R2. Khi registry R2 còn hợp lệ, nó replay các object được hỗ trợ trước bootstrap; không quét Delta files để suy ra mọi metadata hoặc khôi phục managed identity. Trường hợp có dữ liệu cần kế thừa phải restore metadata hoặc đăng ký external location có kiểm tra, không reset như thao tác sửa lỗi auth.

## Lịch backup và mục tiêu phục hồi

Repo chưa cài cron backup mặc định, chưa có remote backup retention hay cam kết RPO/RTO. Chủ sở hữu cần chốt tần suất, khoảng dừng writer cho phép, nơi sao Delta độc lập và người nhận lỗi.

Ví dụ **tùy chọn** cron của đúng tài khoản vận hành, sau khi tạo thư mục log private và xác minh `command -v flock`:

```cron
0 2 * * * /usr/bin/flock -n /tmp/lakehouse-backup.lock /bin/bash /ABS/PATH/sh-lakehouse-src/scripts/backup.sh >> /ABS/PRIVATE/lakehouse-backup.log 2>&1
```

Thay cả hai đường dẫn tuyệt đối; kiểm timezone host bằng timedatectl. Lịch này có downtime writer, không bật chỉ bằng việc có file docs. Theo dõi exit/log và kiểm snapshot ngày mới; không có alert tự động trong project. RPO metadata phụ thuộc snapshot thành công gần nhất; RPO data còn phụ thuộc bản sao Delta riêng. Đo RTO qua restore drill, không suy ra từ dung lượng 300 GB hoặc một unit test archive.

Registry v2 có function definitions và giữ nguyên key/prefix của v1. Trước rollback code cũ, dừng writer và xử lý registry như hướng dẫn [FUNCTIONS](FUNCTIONS.md); không ép version manifest về 1. Backup PostgreSQL vẫn là phương án đầy đủ hơn portable replay.
