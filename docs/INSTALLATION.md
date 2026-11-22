# Cài đặt trên Windows 11 và Ubuntu 22.04

Ubuntu sạch từ Git, SCP env, SSH/UFW và public HTTP/HTTPS: dùng [UBUNTU_DEPLOYMENT.md](UBUNTU_DEPLOYMENT.md). Trang này tập trung setup Windows và tóm tắt nền tảng hai OS. RAM 16 GB xem [RESOURCE_PLANNING.md](RESOURCE_PLANNING.md).

Ứng dụng dùng Linux containers trên cả hai hệ điều hành. Windows 11 dùng Docker Desktop/WSL 2; Ubuntu dùng Docker Engine và Compose plugin. Mã Spark, UC, dbt, Kestra và cấu trúc volume giống nhau; shell khởi động và nơi Docker giữ dữ liệu khác nhau.

## 1. Chuẩn bị chung

- Máy 64-bit, bật virtualization khi dùng Windows/VM; có Internet để tải image và Maven package lần đầu.
- Khuyến nghị cho project: RAM 24–32 GiB nếu chạy nhiều dịch vụ và notebook đồng thời; giữ tối thiểu khoảng 15 GiB trống cho lần build đầu, cộng dung lượng runtime/cache/backup về sau. Đây là ngân sách gợi ý của project, không phải cấu hình tối thiểu của Docker.
- R2 bucket và S3 Access Key ID/Secret Access Key có quyền đọc/ghi bucket. Xem [ENVIRONMENT.md](ENVIRONMENT.md) để điền đúng.
- Clone repository source theo [GIT_SOURCE.md](GIT_SOURCE.md), hoặc chép source vào thư mục mới. Cài mới không mang theo notebook/dbt/workflow cá nhân.
- Dùng thư mục project chứa compose.yaml. Không chép `.env` đang dùng vào Git; giữ ổn định Compose project name và volumes khi nâng cấp.

## 2. Windows 11 — PowerShell

### 2.1. Docker

Cài Docker Desktop theo [hướng dẫn chính thức cho Windows](https://docs.docker.com/desktop/setup/install/windows-install/), dùng WSL 2 và Linux containers. Mở Docker Desktop, chờ engine sẵn sàng. Kiểm tra trong PowerShell:

```powershell
docker info --format '{{.OSType}}'
docker compose version
```

Dòng đầu phải là `linux`. Theo [Docker](https://docs.docker.com/desktop/setup/install/windows-install/), Docker Desktop không được hỗ trợ chính thức trên Windows Server 2022. Với Windows Server, dùng Ubuntu VM làm host cho bộ Linux containers này; máy dev Windows 11 truy cập qua trình duyệt/SSH.

### 2.2. Init và điền cấu hình

Ví dụ chép project vào D:\lakehouse. Chạy:

```powershell
cd D:\lakehouse
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\init.ps1
notepad .env
```

ExecutionPolicy ở lệnh này chỉ áp dụng cho tiến trình PowerShell được mở; không thay policy toàn máy. Script tương thích Windows PowerShell 5.1, dùng nội dung ASCII và sinh `.env` UTF-8 không BOM. Nếu `.env` đã có thì giữ nguyên.

Có thể đặt WORKSPACE_DIR ra ngoài source, ví dụ `../lakehouse-data/workspace`; sau khi lưu `.env`, chạy init lần nữa để tạo đúng thư mục.

Điền 4 biến R2, kiểm tra TZ và chọn RAM phù hợp theo [ENVIRONMENT.md](ENVIRONMENT.md). Mặc định init.ps1 dùng Asia/Ho_Chi_Minh; để chọn timezone khác lúc cài mới:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\init.ps1 -TimeZone Etc/UTC
```

### 2.3. Khởi động

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
docker compose ps
```

Script kiểm tra Linux engine, cấu hình R2, build image và đợi dịch vụ healthy. Khi đã có image đúng phiên bản, có thể dùng `-SkipBuild` để khởi động lại. Chờ bootstrap/runtime-init hoàn tất; catalog/postgres/notebook/sql/runner có healthcheck. Kestra không có healthcheck trong Compose hiện tại, kiểm tra thêm trang web hoặc log của nó.

Mở http://localhost:8888/lab, nhập JUPYTER_TOKEN trong `.env`. Kestra ở http://localhost:8082, đăng nhập bằng KESTRA_USER/KESTRA_PASSWORD. Chỉ copy giá trị token/password, không copy tên biến hoặc dấu bằng.

Docker Desktop quản lý dữ liệu image/volume trong virtual disk. Nếu ổ hệ thống thiếu chỗ, dùng phần cấu hình nơi lưu dữ liệu của Docker Desktop; việc đặt project ở ổ D không tự chuyển các Docker volume sang D.

## 3. Ubuntu 22.04 — Bash

### 3.1. Docker và công cụ

Cài Docker Engine cùng Compose plugin theo mục apt repository trong [tài liệu Docker cho Ubuntu](https://docs.docker.com/engine/install/ubuntu/). Hoàn tất cấu hình quyền chạy Docker cho tài khoản quản trị của bạn theo hướng dẫn đó. Kiểm tra:

```bash
docker info --format '{{.OSType}}'
docker compose version
python3 --version
```

Cần Python 3 để chạy init/start helper. Nếu chưa có, cài gói python3 từ apt. Không cần Docker Desktop trên host Ubuntu.

### 3.2. Init và chạy project

```bash
cd ~/lakehouse
bash scripts/init.sh
nano .env
```

Điền R2, RAM/CPU, timezone và WORKSPACE_DIR theo [ENVIRONMENT.md](ENVIRONMENT.md). Nếu đổi thư mục workspace, lưu `.env` rồi chạy `bash scripts/init.sh` lần nữa. Sau đó:

```bash
bash scripts/start.sh
docker compose ps
```

Khi cài mới, init.sh thử lấy timezone IANA từ timedatectl; xem lại TZ trong `.env` để xác nhận đúng mong muốn. Script không thay timezone của hệ điều hành. Giữ quyền truy cập `.env` hạn chế (`chmod 600 .env`). Các shell script được lưu LF để chạy trên Ubuntu.

### 3.3. Truy cập từ Windows 11

Mặc định chỉ publish vào loopback Ubuntu. Trong PowerShell Windows mở SSH tunnel và giữ terminal chạy:

```powershell
ssh -L 8888:127.0.0.1:8888 -L 8082:127.0.0.1:8082 -L 10000:127.0.0.1:10000 ubuntu_user@IP_UBUNTU
```

Sau đó dùng http://localhost:8888/lab và http://localhost:8082 trên Windows. Nếu đã đổi port trong `.env`, đổi cả port tương ứng của tunnel. SQL 10000 chỉ cần tunnel khi dùng client bên ngoài.

## 4. Kiểm tra sau cài

1. Catalog hiển thị DEFAULT_CATALOG và DEFAULT_SCHEMA; Files mở được cây R2.
2. Trong SQL chạy `SELECT current_catalog(), current_schema(), current_timezone();`.
3. Trong Workflows tạo flow mới, đặt Flow ID `first_check`, thêm một task SQL với nội dung `SELECT 1 AS ok`, Save & publish to Kestra → Execute saved flow; xem SUCCESS trong Workflow Run History. Nếu muốn thử Variables/If/For each, dựng theo [RUNS_WORKFLOWS.md](RUNS_WORKFLOWS.md).
4. Chạy dbt_sample_pipeline theo [REBUILD_DBT.md](REBUILD_DBT.md) để thử seed/build/test/docs. Tạo notebook và project dbt của bạn theo [USER_GUIDE.md](USER_GUIDE.md). Workspace mới từ Git chưa có model hay workflow cá nhân.

Các thông số 8888/8082/10000 chỉ là mặc định. Hướng dẫn lỗi port, login, Spark và Docker nằm trong [TROUBLESHOOTING.md](TROUBLESHOOTING.md). Nếu nâng cấp hoặc di chuyển máy có dữ liệu, đọc [OPERATIONS.md](OPERATIONS.md) và [MIGRATION.md](MIGRATION.md) trước khi thay volume/database.
