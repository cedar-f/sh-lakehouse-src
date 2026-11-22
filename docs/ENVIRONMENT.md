# Cấu hình .env và tài nguyên

`scripts/init.ps1` hoặc `scripts/init.sh` tạo `.env` từ `.env.example` và sinh mật khẩu/token nội bộ. Script giữ nguyên `.env` đã tồn tại. Các giá trị GENERATE/CHANGE_ME là placeholder, chưa phải credential sử dụng được. File `.env` được Git bỏ qua; chia sẻ bản cấu hình bằng `.env.example`.

## Thư mục workspace trên host

`WORKSPACE_DIR` là đường dẫn **trên máy chạy Docker**, được gắn vào `/workspace` trong container. Mặc định `./workspace`; đường dẫn tương đối tính từ thư mục chứa compose.yaml, không tính từ terminal notebook. Dùng đường dẫn literal, không dùng biến shell hay dấu `~`.

```dotenv
WORKSPACE_DIR=../lakehouse-data/workspace
```

Trên Ubuntu có thể dùng đường dẫn tuyệt đối như `/srv/lakehouse-data/workspace`; Windows dùng dấu `/`, ví dụ `D:/lakehouse-data/workspace`. Sửa `.env` xong chạy init lần nữa để tạo thư mục, rồi start. Đổi đường dẫn **không tự chuyển dữ liệu**: nếu workspace cũ có dữ liệu, dừng writer và chuyển nguyên thư mục trước khi recreate. Trên máy dev đã thực hiện chuyển an toàn và đặt `../r2-lakehouse-data/workspace`.

Thư mục này chứa notebook, dbt, workflow và `.lakehouse/spark.json`. Toàn bộ workspace không được track trong repo source hệ thống. Xem [GIT_SOURCE.md](GIT_SOURCE.md).

## Kết nối R2

| Biến | Điền gì? |
|---|---|
| R2_ACCOUNT_ID | Account ID trên tài khoản Cloudflare sở hữu bucket |
| R2_ACCESS_KEY_ID | S3 Access Key ID được cấp khi tạo credential R2 |
| R2_SECRET_ACCESS_KEY | S3 Secret Access Key đi cùng Access Key ID |
| R2_BUCKET | Tên bucket chính xác, không thêm s3:// hoặc đường dẫn |
| S3_ENDPOINT | Để trống để suy ra endpoint chuẩn từ Account ID; điền endpoint riêng nếu môi trường yêu cầu |
| BACKUP_PREFIX | Prefix cho snapshot backup; mặc định platform-backups/v3 |

Credential cần đọc/ghi object trong bucket. S3 Secret Access Key khác Cloudflare Global API Key và token Bearer. Giữ bí mật credential; xem cách quản lý S3 credential trong [tài liệu Cloudflare](https://developers.cloudflare.com/r2/api/tokens/).

Ví dụ cấu hình hình dạng, thay các placeholder bằng giá trị của bạn:

```dotenv
R2_ACCOUNT_ID=account_id_cua_ban
R2_ACCESS_KEY_ID=access_key_id_cua_ban
R2_SECRET_ACCESS_KEY=secret_access_key_cua_ban
R2_BUCKET=ten_bucket_cua_ban
S3_ENDPOINT=
```

Trong bucket, `warehouse/` chứa dữ liệu bảng; `incoming/` chứa file upload; BACKUP_PREFIX chứa snapshot phục hồi. File upload chưa tự trở thành bảng Delta.

## Đăng nhập và secret nội bộ

| Biến | Vai trò |
|---|---|
| JUPYTER_TOKEN | Giá trị nhập vào ô Password or token ở JupyterLab |
| RUNNER_TOKEN | Xác thực giữa UI/Kestra và runner; các service phải dùng cùng giá trị |
| POSTGRES_PASSWORD | Mật khẩu database cho UC và Kestra |
| KESTRA_USER | Tên đăng nhập Kestra dạng email, ví dụ admin@example.com |
| KESTRA_PASSWORD | Mật khẩu Kestra |
| HUB_ADMIN | Tên tài khoản quản trị khi bật chế độ Hub tùy chọn |

Không đổi POSTGRES_PASSWORD của `.env` như cách reset database đã tồn tại: PostgreSQL giữ mật khẩu đã thiết lập trong volume. Cần đổi mật khẩu trong database theo quy trình quản trị rồi cập nhật cấu hình tương ứng. Không thay toàn bộ `.env` bằng mẫu khi nâng cấp.

## Catalog, CPU, RAM và Spark

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| DEFAULT_CATALOG | lakehouse | Catalog bootstrap và mặc định ban đầu |
| DEFAULT_SCHEMA | default | Schema mặc định ban đầu |
| SEED_SAMPLE_DBT | true | Tạo dbt_sample và workflow mẫu khi thiếu; không ghi đè hoặc tự chạy |
| SPARK_THREADS | auto | local[*] hoặc số CPU threads mỗi Spark driver |
| SPARK_DRIVER_MEMORY | 4g | Heap mỗi Spark JVM |
| SPARK_SHUFFLE_PARTITIONS | 8 | Số partition shuffle mặc định |
| NOTEBOOK_MEMORY | 6g | Giới hạn container Jupyter/notebook |
| SQL_MEMORY | 6g | Giới hạn container SQL |
| RUNNER_MEMORY | 6g | Giới hạn container runner/job nền |
| KESTRA_MEMORY | 4g | Giới hạn container Kestra |
| KESTRA_JAVA_OPTS | Xms256m, Xmx2g, ActiveProcessorCount=2 | Heap/thread CPU cho JVM Kestra; xem giá trị đầy đủ trong .env.example |

Tên catalog/schema dùng chữ, số, dấu gạch dưới và bắt đầu bằng chữ/gạch dưới. Có thể tạo thêm catalog/schema qua UI.

Giới hạn container cần cao hơn heap để còn bộ nhớ Python, native và JVM overhead. Mỗi notebook kernel có Spark driver riêng; đừng nhân số notebook bận mà chỉ dự trù RAM cho một driver. `auto` sử dụng CPU Docker nhìn thấy, vẫn chịu giới hạn CPU/WSL/VM của host. Trên Windows, ngân sách WSL/Docker nằm ngoài `.env` của project.

Ví dụ khởi đầu gọn hơn trên máy RAM hạn chế, rồi tăng dựa trên docker stats:

```dotenv
SPARK_THREADS=2
SPARK_DRIVER_MEMORY=1g
NOTEBOOK_MEMORY=2g
SQL_MEMORY=2g
RUNNER_MEMORY=2g
```

Đây là cấu hình đã dùng cho một số kiểm thử nhỏ, không phải cam kết xử lý 300 GB trên máy RAM nhỏ.

Compute → Save & Restart Spark lưu cấu hình vào `WORKSPACE_DIR/.lakehouse/spark.json` trên host, tương ứng `/workspace/.lakehouse/spark.json` trong container. File này ghi đè các giá trị Spark mặc định từ `.env`. Đổi `.env` không tự xóa cấu hình đã lưu ở Compute. Dùng ô Extra Spark config để thêm `{"spark.sql.sources.default":"delta"}` nếu muốn CREATE TABLE bỏ qua USING vẫn mặc định dùng Delta; hoặc ghi rõ `USING DELTA` trong SQL.

## Port và timezone

| Biến | Mặc định |
|---|---|
| BIND_IP | 127.0.0.1 |
| NOTEBOOK_PORT | 8888 |
| KESTRA_PORT | 8082 |
| SQL_BIND_IP | 127.0.0.1 |
| SQL_PORT | 10000 |
| TZ | Asia/Ho_Chi_Minh |

TZ là IANA zone, ví dụ Asia/Ho_Chi_Minh hoặc Etc/UTC. UI chuyển timestamp chuẩn sang TZ để hiển thị và diễn giải bộ lọc datetime-local. Spark SQL session, JVM, PostgreSQL và Kestra được cấp cùng TZ. Workflow đã có timezone riêng vẫn giữ timezone đó; sửa Schedule timezone và Publish nếu muốn thay lịch.

## Retention

| Biến | Mặc định | Phạm vi |
|---|---|---|
| RUN_RETENTION_DAYS | 30 | Tuổi artifact của run terminal |
| RUN_STORAGE_MAX_GB | 10 | Quota GiB cho artifact run đã kết thúc; xóa cũ nhất khi vượt |
| HISTORY_RETENTION_DAYS | 365 | Tuổi metadata lịch sử |
| RUN_LOG_MAX_MB | 25 | MiB cho execution log và từng nguồn structured event |
| RUN_ARTIFACT_MAX_MB | 1024 | MiB artifact một job; kiểm tra mỗi 5 giây và dừng job khi vượt |
| KESTRA_RETENTION_DAYS | 30 | Retention execution terminal/file nội bộ trong namespace lakehouse.v3 |

Đây là retention vận hành, không phải quota toàn bộ Docker disk. R2 table, PostgreSQL, warehouse và cache Maven có vòng đời riêng. Xem [OPERATIONS.md](OPERATIONS.md).

## Áp dụng thay đổi

Sửa `.env` rồi recreate các service liên quan, ví dụ sau khi đổi TZ:

```text
docker compose up -d --force-recreate
```

Lưu notebook trước thao tác recreate. Đổi mã ứng dụng/Dockerfile cần build image lại; đổi token trên browser cần đăng nhập lại. Với Spark config trong Compute, dùng Save & Restart Spark để chỉ thay các Spark process đã chọn. Xem thứ tự áp dụng và lỗi thường gặp trong [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## Ưu tiên cấu hình và các biến nội bộ

Đọc [RESOURCE_PLANNING.md](RESOURCE_PLANNING.md) trước khi dùng default 4g/6g trên host 16 GB. Tài liệu phân biệt profile cân bằng đang hỗ trợ với proposal memory riêng theo service chưa triển khai.

Thứ tự: giá trị mặc định trong code → env process từ Compose → `.lakehouse/spark.json` ghi đè các Spark setting đã lưu. Kernel đang sống giữ SparkContext/config của nó; Save & Restart scope không chọn kernel đó sẽ không làm nó nhận cấu hình mới. User code còn có thể thay các SQL setting cho session của mình.

Không thêm các biến như SQL_SPARK_MEMORY/NOTEBOOK_SPARK_MEMORY rồi kỳ vọng app tự nhận; hiện không có mapping đó trong code. Container cap và driver_memory là hai lớp khác nhau.

Các biến sau do Compose/entrypoint đặt, thường không cần thêm vào env riêng:

| Biến | Default Compose / vai trò |
|---|---|
| WORKSPACE_ROOT | Code fallback /workspace; bind mount hiện cố định /workspace |
| RUNS_ROOT | /var/lib/lakehouse/runs |
| RUNTIME_ROOT | /var/lib/lakehouse/runtime |
| UC_URL | http://catalog:8080 |
| SQL_HOST | sql |
| RUNNER_URL | http://runner:8765 |
| KESTRA_URL | http://kestra:8080 |
| LAKEHOUSE_SERVICE | notebook/sql/runner cho temp/warehouse riêng |
| PYTHONPATH | /opt/lakehouse |
| PYSPARK_PYTHON | /usr/bin/python3 |
| SPARK_LOCAL_IP | 127.0.0.1; Spark chạy local |

Đổi các đường dẫn nội bộ cần đồng bộ mounts/permission/artifact serving; không đổi chỉ một env để di chuyển runtime database. Script notebook background còn dùng LAKEHOUSE_PARAMETERS/LAKEHOUSE_RUN_DIR theo run, không phải global config.

**Biến của Docker Compose**, khác app variables: COMPOSE_FILE cho phép dùng override, ví dụ `compose.yaml:docs/examples/compose.proxy.yaml` trên Ubuntu. Chuẩn bị file local theo [UBUNTU_DEPLOYMENT.md](UBUNTU_DEPLOYMENT.md) trước khi bật. Đổi project name bằng CLI/env thay namespace named volumes; kiểm kết quả `docker compose config`/ps và không coi volume mới trống là dữ liệu cũ đã mất.

Không source .env thành shell script. Tránh in toàn bộ `docker compose config` hoặc Docker inspect environment vào log bàn giao vì có secret đã được interpolate; dùng config --quiet và inspect field cụ thể.
