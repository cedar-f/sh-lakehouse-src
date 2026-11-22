# Ubuntu mới: Git → env → Docker → truy cập

Luồng chính cho Ubuntu 22.04 và máy dev Windows 11. Dùng tài khoản có sudo; nếu host hiện dùng root, sudo vẫn có thể bỏ theo môi trường, nhưng không đổi user runtime của container để chữa lỗi quyền. Hướng dẫn single-user; Hub có quy trình riêng tại [MULTIUSER.md](MULTIUSER.md).

Thay USER_UBUNTU, IP_SERVER và OWNER/REPO bằng thông tin thật. IP_SERVER ở các lệnh truy cập Internet là public IP; hostname -I chỉ cho biết địa chỉ interface của máy. Source repo hiện tại là `cedar-f/sh-lakehouse-src`; kiểm tra quyền truy cập và branch trước khi clone. `.env` không nằm trong Git.

## 1. Chuẩn bị OS và SSH

Nếu chưa vào được SSH, dùng console máy/VM hoặc web console nhà cung cấp:

```bash
sudo apt update
sudo apt install -y ca-certificates curl git python3 nano openssh-server ufw tzdata gnupg
sudo systemctl enable --now ssh
sudo timedatectl set-timezone Asia/Ho_Chi_Minh
whoami
hostname -I
free -h
nproc
df -h /
uname -m
```

Mục tiêu đã dùng để thiết kế là host Intel/AMD 64-bit; kiến trúc khác cần kiểm tra image/dependency thực tế. Dành disk cho Docker/temp, không chỉ source; đọc [RESOURCE_PLANNING.md](RESOURCE_PLANNING.md) và dùng profile 16 GB nếu phù hợp. sudo không hiện ký tự khi nhập password là bình thường.

### Mở SSH trước khi bật firewall

Trong firewall/security group của VPS, cho phép TCP 22 trước và gắn rule vào đúng server. Nếu sau router, forward public TCP 22 tới Ubuntu LAN:22; VM NAT có thể cần thêm một lớp forwarding. Đường truyền không có public address nhận inbound cần giải pháp public IP/tunnel riêng.

```bash
sudo /usr/sbin/sshd -T | grep '^port '
sudo ss -lntp | grep ':22'
sudo ufw insert 1 allow 22/tcp
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw enable
sudo ufw status numbered
```

Nếu SSH listener thực tế không phải 22, mở thêm đúng listener port trước enable và đổi ssh -p/scp -P tương ứng. Giữ phiên console/SSH hiện tại. Trên **PowerShell Windows khác**, kiểm tra và đăng nhập phiên mới rồi mới đóng phiên cũ:

```powershell
Test-NetConnection IP_SERVER -Port 22
ssh USER_UBUNTU@IP_SERVER
```

Nếu bị khóa, vào web console và dùng `sudo ufw insert 1 allow 22/tcp`, kiểm tra listener và firewall nhà cung cấp. Không reset toàn bộ rule firewall để chữa một port. Tham chiếu [Ubuntu UFW](https://ubuntu.com/server/docs/how-to/security/firewalls/).

## 2. Docker Engine và Compose

Các lệnh cho host Ubuntu sạch, chưa có Docker package/repository khác. Nếu đã cài, kiểm tra version/hello-world trước; khi có package xung đột xem quy trình chính thức thay vì cài chồng. Cách dưới dùng [APT repository của Docker](https://docs.docker.com/engine/install/ubuntu/).

```bash
sudo install -d -m 0755 /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod 0644 /etc/apt/keyrings/docker.asc
. /etc/os-release
docker_arch=$(dpkg --print-architecture)
echo "deb [arch=$docker_arch signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $VERSION_CODENAME stable" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
newgrp docker
docker run --rm hello-world
docker compose version
docker info --format '{{.OSType}}'
```

Kết quả OSType phải linux. Nếu group chưa áp dụng, logout/login lại. Docker group có quyền quản trị host; chỉ cấp cho tài khoản tin cậy. Không cần Docker Desktop, Spark hoặc Java riêng trên Ubuntu.

## 3. Clone GitHub bằng deploy key

Repo phải có source đã push. Trên Ubuntu:

```bash
umask 022
mkdir -p ~/.ssh
chmod 700 ~/.ssh
ssh-keygen -t ed25519 -f ~/.ssh/lakehouse_git -C "ubuntu-lakehouse"
cat ~/.ssh/lakehouse_git.pub
```

Nếu key đã có, giữ key, không ghi đè. Thêm dòng **public key** vào GitHub repo → Settings → Deploy keys → Add deploy key; đặt title server và để write access không chọn. Đây là key Ubuntu đọc source GitHub, khác key Windows dùng login Ubuntu. Xem [GitHub deploy keys](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys).

```bash
mkdir -p ~/data
git -c core.sshCommand="ssh -i $HOME/.ssh/lakehouse_git -o IdentitiesOnly=yes" clone git@github.com:OWNER/REPO.git ~/data/sh-lakehouse-src
cd ~/data/sh-lakehouse-src
git config core.sshCommand "ssh -i $HOME/.ssh/lakehouse_git -o IdentitiesOnly=yes"
git remote -v
git log -1 --oneline
```

Xác nhận host key GitHub ở lần đầu và nhập passphrase nếu đặt. Nếu thư mục đích đã có source, kiểm tra Git tại đó; không clone đè/xóa workspace để thử lại.

## 4. Chuyển hoặc tạo .env

Chọn một cách. **Cài mới hoàn toàn**: chạy `bash scripts/init.sh`, mở `nano .env`, điền R2 và tài nguyên theo [ENVIRONMENT.md](ENVIRONMENT.md). Script sinh token/password nội bộ.

**Dùng cấu hình riêng đang có trên Windows**: trước khi init/start, tạo file private ở Ubuntu:

```bash
cd ~/data/sh-lakehouse-src
touch .env
chmod 600 .env
```

Hai lệnh trên không làm rỗng nội dung file đang có. Bước SCP kế tiếp sẽ thay nội dung .env; nếu host đã có cấu hình cần giữ, lưu bản private riêng hoặc dùng bản đó thay cho SCP. Nếu SCP lỗi, dừng và xử lý trước init/start. Trên Windows PowerShell:

```powershell
scp "D:\r2-lakehouse-v3\.env" USER_UBUNTU@IP_SERVER:data/sh-lakehouse-src/.env
```

Đổi local path nếu source của bạn ở nơi khác. Trên Ubuntu chuẩn hóa text và quyền, không in secret:

```bash
cd ~/data/sh-lakehouse-src
python3 - <<'PY'
from pathlib import Path
p = Path('.env')
text = p.read_text(encoding='utf-8-sig')
with p.open('w', encoding='utf-8', newline='\n') as stream:
    stream.write(text)
p.chmod(0o600)
PY
nano .env
```

Kiểm tra bốn trường R2, endpoint, KESTRA_USER dạng email, RAM và đường dẫn. Giữ password/token cũ nếu đang kế thừa metadata hiện có; không thay POSTGRES_PASSWORD tùy ý với volume DB đã khởi tạo.

```dotenv
WORKSPACE_DIR=../lakehouse-data/workspace
TZ=Asia/Ho_Chi_Minh
BIND_IP=127.0.0.1
NOTEBOOK_PORT=8888
KESTRA_PORT=8082
SQL_BIND_IP=127.0.0.1
SQL_PORT=10000
SEED_SAMPLE_DBT=true
```

Áp profile RAM ở [RESOURCE_PLANNING.md](RESOURCE_PLANNING.md), rồi:

```bash
bash scripts/init.sh
git check-ignore .env
docker compose config --quiet
```

Không source .env trong shell; không để umask 077 kéo dài trong phiên Git checkout. `.env` dùng chmod 600; code image có bước chuẩn hóa quyền đọc cho analyst.

## 5. Bật stack và kiểm tra qua tunnel trước

Đây là cài mới source/state. Nếu chuyển host để giữ catalog/table cũ, làm [MIGRATION.md](MIGRATION.md) thay vì coi cùng R2 bucket là đã migrate. Dừng writer host cũ trước khi chuyển quyền ghi.

```bash
cd ~/data/sh-lakehouse-src
bash scripts/start.sh
docker compose ps -a
docker compose logs --tail=100 bootstrap
```

bootstrap/runtime-init Exited (0) là bình thường; postgres/catalog/notebook/sql/runner cần healthy. Kestra cần kiểm tra UI/login riêng. Nếu R2 Unauthorized, cập nhật credential; không reset metadata để chữa auth. Script build cần thời gian và kết nối SSH giữ mở đến khi xong.

Trên Windows dùng tunnel (đóng bản Windows cũ hoặc chọn local port khác nếu port bị chiếm):

```powershell
ssh -N -o ExitOnForwardFailure=yes -L 8888:127.0.0.1:8888 -L 8082:127.0.0.1:8082 -L 10000:127.0.0.1:10000 USER_UBUNTU@IP_SERVER
```

Mở http://localhost:8888/lab và http://localhost:8082. Jupyter dùng JUPYTER_TOKEN, Kestra dùng KESTRA_USER/KESTRA_PASSWORD, có thể là browser Basic auth prompt. Lấy giá trị từ `nano .env`; giữ tunnel mở. Sau đó nghiệm thu SQL/Files/sample theo [ACCEPTANCE.md](ACCEPTANCE.md).

## 6. Chọn cách truy cập public

### A. HTTPS qua domain — ví dụ triển khai single-user

Ví dụ này cần hai hostname bạn sở hữu: lakehouse.example.com và kestra.example.com. Thay bằng domain thật và tạo A records tới public IPv4; chỉ để AAAA khi IPv6 hoạt động. Khi dùng DNS provider có proxy, có thể bắt đầu DNS-only để kiểm tra đường tới origin. Mở TCP **22, 80, 443** ở firewall nhà cung cấp/router; backend 8888/8082/10000 giữ loopback.

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
```

Tạo bản config local, không sửa template đang track trong Git:

```bash
mkdir -p deploy-local
printf '/deploy-local/\n' >> "$(git rev-parse --git-path info/exclude)"
cp docs/examples/jupyter-proxy.json deploy-local/jupyter-proxy.json
cp docs/examples/Caddyfile deploy-local/Caddyfile
nano deploy-local/jupyter-proxy.json
nano deploy-local/Caddyfile
chmod 644 deploy-local/jupyter-proxy.json
nano .env
```

Thay hostname trong cả JSON và Caddyfile. Giữ bind loopback như bước 4 và thêm vào `.env` trên Ubuntu:

```dotenv
COMPOSE_FILE=compose.yaml:docs/examples/compose.proxy.yaml
```

Đây là biến của Docker Compose, dùng dấu `:` trên Linux. Nhờ lưu ở `.env`, start/rebuild/backup/restore dùng cùng override. Proxy JSON cho Jupyter tin forwarded protocol và whitelist đúng hostname; backend chỉ tiếp nhận proxy qua loopback. Tham chiếu [Jupyter trust_xheaders/local_hostnames](https://jupyter-server.readthedocs.io/en/latest/other/full-config.html). Không bật allow_origin=* để chữa WebSocket.

```bash
docker compose config --quiet
docker compose up -d --force-recreate notebook kestra
```

Cài Caddy trên **host**, theo [hướng dẫn package chính thức](https://caddyserver.com/docs/install#debian-ubuntu-raspbian):

```bash
sudo apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl gnupg
curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/gpg.key | sudo gpg --dearmor --yes --output /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt | sudo tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
sudo chmod a+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg /etc/apt/sources.list.d/caddy-stable.list
sudo apt-get update
sudo apt-get install -y caddy
sudo install -m 644 deploy-local/Caddyfile /etc/caddy/Caddyfile
sudo caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
sudo systemctl enable --now caddy
sudo systemctl reload caddy
```

Caddy quản lý chứng chỉ/renew khi DNS, đường tới 80/443 và certificate storage phù hợp; [Automatic HTTPS](https://caddyserver.com/docs/automatic-https). Reverse proxy hỗ trợ WebSocket, cần cho notebook/terminal; [Caddy reverse_proxy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy).

Kiểm tra https://lakehouse.example.com/lab và https://kestra.example.com/ui, login, kernel WebSocket, upload >32 MiB, Open Docs và workflow. Khi lỗi xem `sudo journalctl -u caddy -n 100 --no-pager`. Nếu trước đó public raw ports, xác nhận Docker đã bind lại loopback rồi gỡ inbound rule 8888/8082 ở provider và UFW. Mẫu này chưa được nghiệm thu trên host thật; ghi kết quả theo [VALIDATION.md](VALIDATION.md).

### B. Public HTTP trực tiếp — chỉ dùng thử draft

HTTP không mã hóa token/password. Chỉ dùng tạm cho thử nghiệm có chủ đích. Trong `.env` đổi BIND_IP=0.0.0.0, giữ SQL_BIND_IP=127.0.0.1. Nếu đã bật proxy override ở mode A, bỏ COMPOSE_FILE đó trước khi dùng direct IP để tránh hostname whitelist của proxy mode.

```bash
sudo ufw allow 8888/tcp
sudo ufw allow 8082/tcp
docker compose up -d --force-recreate notebook kestra
docker compose port notebook 8888
docker compose port kestra 8080
docker compose port sql 10000
```

Mở thêm TCP 8888/8082 ở provider/router tới server. Kết quả tương ứng 0.0.0.0:8888, 0.0.0.0:8082, 127.0.0.1:10000. Windows kiểm tra `Test-NetConnection IP_SERVER -Port 8888` và port 8082; trình duyệt dùng http://IP_SERVER:8888/lab, http://IP_SERVER:8082.

Docker publish có thể bypass UFW, vì vậy không dựa riêng vào deny rule UFW để bảo vệ container port; [Docker/UFW](https://docs.docker.com/engine/network/packet-filtering-firewalls/#docker-and-ufw). Không public SQL NOSASL, UC, runner, PostgreSQL hay Docker daemon. Dùng tunnel/VPN cho SQL và [EXTERNAL_CLIENTS.md](EXTERNAL_CLIENTS.md).

## 7. Cập nhật sau này

```bash
cd ~/data/sh-lakehouse-src
git status --short
git pull --ff-only
bash scripts/rebuild.sh
```

Lưu công việc và tạo snapshot khi cần rollback; đọc [OPERATIONS.md](OPERATIONS.md) và [DISASTER_RECOVERY.md](DISASTER_RECOVERY.md). `.env`, deploy-local và workspace là state/config riêng, không bị git pull cập nhật. Khi đổi hostname/proxy config, sửa bản local và validate/reload Caddy riêng. Không thêm reset-metadata vào quy trình upgrade thường ngày.
