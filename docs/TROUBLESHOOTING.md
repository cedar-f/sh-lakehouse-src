# Xử lý lỗi thường gặp

## Docker không kết nối được / npipe not found

Mở Docker Desktop trên Windows, chờ engine chạy. Kiểm tra `docker info --format '{{.OSType}}'` trả `linux`. PowerShell đang trỏ sai context có thể được kiểm tra bằng `docker context ls`. Trên Ubuntu kiểm tra dịch vụ Docker và quyền tài khoản. Đừng dùng xóa volume như cách sửa lỗi engine.

## Port 8888/8082/10000 already allocated

Xem container publish port bằng `docker ps --format '{{.Names}} {{.Ports}}'`. Dừng bản cũ giữ port nếu không còn dùng, hoặc chọn port khác trong `.env` và recreate service liên quan. Đổi port host không đổi port nội bộ container. Nếu dùng SSH tunnel, cập nhật tunnel cho cùng mapping.

## PowerShell báo Unexpected token / lỗi ký tự

Dùng scripts/init.ps1 và scripts/start.ps1 của bản hiện tại; chúng dùng ASCII, hỗ trợ Windows PowerShell 5.1. Chạy từ thư mục project theo [INSTALLATION.md](INSTALLATION.md). Script cũ copy qua Notepad có thể bị encoding khác. `.env` được init bằng UTF-8 không BOM; không cần sửa script để điền password.

## Login Jupyter không được

Mở `/lab` trên NOTEBOOK_PORT, lấy đúng **giá trị** JUPYTER_TOKEN từ `.env` đang cấp cho container. Sau khi đổi token phải recreate notebook. Nếu đang vào container/bản project khác, kiểm tra compose ps và port trước. Thử cửa sổ riêng tư khi cookie cũ gây vấn đề. Route `/lakehouse` của bản cũ không phải giao diện V3.

## Kestra quay về login / HTTP 401 / hộp thoại Basic Auth

KESTRA_USER phải là email; dùng đúng KESTRA_PASSWORD trong `.env`. Sau khi sửa:

```text
docker compose up -d --force-recreate kestra
docker compose logs --tail=100 kestra
```

Chỉ restart container có thể chưa áp dụng env mới. Browser có thể đang nhớ Basic Auth cũ; thử phiên riêng tư. Xem RAM thực tế bằng docker stats khi API chậm; KESTRA_MEMORY và KESTRA_JAVA_OPTS là hai ngân sách cần khớp nhau.

## Spark/SQL chưa ready / Connection refused

```text
docker compose logs --tail=100 catalog sql runner
docker compose ps
```

SQL chờ UC trong giai đoạn khởi động. Runner chờ SQL trước khi chạy dbt/SQL. Trong Compute kiểm tra status, cấu hình RAM và thử Save & Restart Spark sau khi sửa lỗi. Khi tăng heap, tăng cả giới hạn container tương ứng và còn RAM cho các dịch vụ khác.

## CREATE TABLE sai format hoặc không thấy bảng

Dùng `CREATE TABLE ... USING DELTA ...`, kiểm tra `SELECT current_catalog(), current_schema();`. Tên đầy đủ là catalog.schema.table. Tạo catalog/schema trước; refresh Catalog. Nếu đã lưu cấu hình trong Compute, `.lakehouse/spark.json` ghi đè mặc định Spark của `.env`. Để bỏ USING, đặt spark.sql.sources.default=delta trong Compute và restart Spark session cần áp dụng.

## R2 403 / AccessDenied / Signature mismatch

Kiểm tra 4 biến R2, bucket/endpoint và quyền S3 credential. Secret Access Key khác token Bearer. Kiểm tra đồng hồ host nếu chữ ký không hợp lệ. Khi chia sẻ log, che credential; không đăng `.env` công khai. UC metadata kết nối được chưa bảo đảm credential storage đúng.

## Registry pending / startup conflict

Xem `docker compose logs --tail=100 registry`, key/endpoint/bucket, registry prefix và Compute status. R2 AccessDenied không là object missing; startup không được ghi registry trống. UC local khác registry khi không có lineage khớp cần chọn nguồn đúng theo [CATALOG_REGISTRY](CATALOG_REGISTRY.md), không tự reset hoặc xóa JSON. Managed unrestored là giới hạn replay có chủ đích; giữ inventory/location và phục hồi riêng, không tạo lại cùng tên để bỏ qua cảnh báo.

## Git push cần passphrase / Permission denied

Mở GitHub → Refresh status, kiểm key loaded; dùng Unlock SSH key với passphrase hiện có. Jupyter và wizard cần cùng SSH agent do entrypoint tạo, không phải agent riêng trong một terminal. Repo phải có origin SSH, đúng key/quyền write và upstream. Sau cập nhật entrypoint cần rebuild/recreate notebook. Xem [GITHUB_WORKSPACE](GITHUB_WORKSPACE.md) cho luồng init/clone/auto ignore và các lỗi remote/branch protection.

## dbt checkpoint và model

Project cần .dbtignore; runner tự thêm quy tắc bỏ qua `.ipynb_checkpoints`. Kiểm tra model/seed selection, lỗi trong Models/Logs của run, trạng thái SQL và catalog/schema đích. Dùng Open Docs cho snapshot docs đã thành công; bấm docs để tạo mới sau khi sửa model.

## Workflow không thấy file / không thấy sample cũ

Source không chứa workspace cá nhân. Bootstrap cài mới tạo `dbt_sample_pipeline` nếu SEED_SAMPLE_DBT=true và file còn thiếu; ví dụ `variable_if_foreach_demo` là hướng dẫn dựng flow, không được bootstrap tự tạo. Dựng lại theo [RUNS_WORKFLOWS.md](RUNS_WORKFLOWS.md) nếu cần. Notebook job dùng path tương đối dưới workspace của bạn. Lưu notebook trước khi gọi; cập nhật Workspace path của node khi đổi tên/chuyển file. Refresh browser nếu dropdown workflow còn danh sách cache cũ. Lịch sử có thể vẫn có execution của định nghĩa đã xóa.

## If/For each báo biến không tồn tại

Đặt dependency để bước Variables hoàn tất trước khi If đọc vars. Task trong block dùng Parent block; Depends on chỉ nối các task cùng cấp. Ô Items của biểu thức cần dạng JSON string `"{{ vars.numbers }}"`. Biến gán trong loop riêng từng lượt; dùng outputs.for_each_number.items để lấy kết quả ngoài loop. Hướng dẫn đầy đủ ở [RUNS_WORKFLOWS.md](RUNS_WORKFLOWS.md).

## Artifact hết hạn / run INTERRUPTED / timezone khác mong muốn

Artifact hết hạn theo retention; metadata history có thể còn. INTERRUPTED cho biết runner đã khởi động lại trước khi job hoàn tất, cần xem partial output trước retry. Kiểm tra TZ trong `.env`, recreate service và refresh trình duyệt; bộ lọc from/to dùng TZ hiển thị trên màn hình. Timezone riêng của schedule cần chỉnh và publish ở workflow.

## Giao diện chưa cập nhật

Build image mới và recreate notebook, sau đó Ctrl+F5. Code frontend được đóng trong image, không hot reload trực tiếp từ thư mục runtime trên host. Nếu các tab lỗi, kiểm tra log notebook/runner và status của API; ghi lại thao tác, flow/run ID, thời điểm theo TZ và đoạn lỗi để tra cứu.

## PermissionError đọc /opt/lakehouse/platform_bootstrap.py

Docker image chạy bằng user analyst (UID 1000), dù host Ubuntu đang đăng nhập root. Khi source được checkout với umask 077, file mới có thể là 600 và directory là 700. Docker COPY giữ mode đó với ownership root, khiến analyst không đọc được module/template. Đây là lỗi đóng gói image, không chữa bằng cách chạy Bash bằng sudo trên host.

Dockerfile chuẩn hóa quyền đọc/traverse của code và frontend sau COPY; code vẫn root-owned và analyst không được sửa. Catalog startup script dùng mode 0755 rõ ràng.

Cập nhật source và rebuild trên Ubuntu:

```bash
cd ~/data/sh-lakehouse-src
umask 022
git pull --ff-only
bash scripts/rebuild.sh
```

Nếu đang chủ động dựng mới và muốn bỏ metadata cũ, dùng `bash scripts/rebuild.sh --reset-metadata` thay cho lệnh rebuild cuối; flag này có ý nghĩa xóa metadata/lịch sử như mô tả trong [REBUILD_DBT.md](REBUILD_DBT.md). Lỗi import ở preflight xảy ra trước bước reset volumes.

Giữ `.env` ở mode 600: `chmod 600 .env`. Chỉ dùng umask 077 trong phạm vi tạo secret hoặc script con, không để phiên Git checkout phụ thuộc vào nó.

Regression test: `python3 tests/image_permissions.py`. Test build từ context có Python/template/startup root-only, kiểm tra import/read/template generation bằng user runtime và quyền đọc/chạy UC startup; không dùng R2 hay data volume.
