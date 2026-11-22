# Ranh giới bảo mật hiện tại

Tài liệu này mô tả implementation, không chứng nhận hệ thống đã đạt an toàn production/multi-tenant. Phạm vi sử dụng hiện tại là một người dùng hoặc nhóm người dùng tin cậy, có quyền chạy code và truy cập cùng dữ liệu.

## Ai được tin cậy?

| Lớp | Đang có | Không bảo đảm |
|---|---|---|
| Host Ubuntu/Windows, Docker admin | Quyền quản trị máy và container | Docker group không phải user quyền thấp |
| Jupyter single-user | Token/cookie auth, gateway authenticated | Không phân quyền bảng/file/workflow giữa người dùng chung token |
| JupyterHub tùy chọn | PAM login, home/server riêng, workspace chung | Không tự bật UC auth/RBAC hoặc cô lập data/secret |
| Runner | X-Runner-Token cho application API, private network, allowlisted task types | Không sandbox notebook người dùng; người chạy code đọc environment được |
| Kestra | Basic auth theo config hiện tại | Chưa có role/workflow permission theo từng user trong project |
| SQL Thrift | NOSASL, bind localhost mặc định | Không có SQL user auth/TLS của project để public trực tiếp |
| UC | Metadata, managed tables, scoped credential integration | server.authorization=disable; UI Permissions không enforce grant |
| R2 | Parent S3 credential và custom scoped credential theo path | Không cô lập workspace khác nếu có cùng credential/khả năng gọi UC |

Người có notebook/terminal được xem như có quyền trên dữ liệu và secret của workspace. Hiding menu, tắt terminal, hay scoped credential vending không biến code execution thành tenant isolation. Tách user/workspace không tin cậy cần identity, UC authorization, credential cấp theo identity và cô lập compute/network/storage; chưa có triển khai đó.

## Port và đường truy cập

| Port | Vai trò | Public mặc định |
|---|---|---|
| 22/TCP trên host | SSH/SCP | Host/provider do người vận hành mở trước khi bật UFW |
| 8888/TCP | Jupyter/Lakehouse | Compose bind 127.0.0.1 |
| 8082/TCP → Kestra 8080 | Kestra UI/API | Compose bind 127.0.0.1 |
| 10000/TCP | Thrift NOSASL | Bind 127.0.0.1; dùng tunnel/VPN |
| 8080 catalog / 8765 runner / 5432 postgres | Service-to-service | Không publish trong default Compose |
| 80/443 host proxy | HTTP redirect/HTTPS tùy chọn | Cài/config riêng theo UBUNTU_DEPLOYMENT |

Mở SSH theo listener thực tế trước UFW, giữ phiên cũ và thử login phiên mới. Docker NAT published traffic có thể bypass UFW; dùng đúng bind address và firewall upstream. Trong HTTPS mode giữ backend loopback, chỉ trust proxy headers từ đường truy cập được kiểm soát. Mẫu copyable ở [UBUNTU_DEPLOYMENT.md](UBUNTU_DEPLOYMENT.md), không tự được bật khi clone repo.

HTTP draft 8888/8082 không mã hóa credential; chuyển HTTPS trước vận hành lâu dài. HTTPS bảo vệ transport, không bổ sung UC RBAC. Reverse proxy phải giữ WebSocket và hostname đúng; không mở CORS toàn bộ hay tắt token/XSRF để chữa proxy.

## Secret và config

- `.env` private chmod 600; root `.gitignore` bỏ qua. Không đưa secret vào URL Git, notebook, model, workflow JSON, screenshot hoặc issue/log chia sẻ.
- Không source `.env` như shell script. Giữ backup `.env` mã hóa và ghi nơi cất/owner trong hồ sơ bàn giao riêng.
- R2 dùng S3 Access Key/Secret được cấp cho đúng bucket, không thay bằng Cloudflare Bearer token. Server clock/TZ và endpoint cần đúng để ký request.
- JUPYTER_TOKEN bảo vệ UI; RUNNER_TOKEN bảo vệ runner; KESTRA_* cho Kestra; POSTGRES_PASSWORD cho DB. Chúng có phạm vi khác nhau, không dùng thay nhau.
- Đổi R2 key cần cập nhật env và recreate các service sử dụng key, kể cả catalog; secret đã nằm trong process cũ không tự đổi theo file.
- Đổi Jupyter token có thể yêu cầu xử lý session đang tồn tại; nếu nghi lộ, invalidate cookie/session theo Jupyter và ngắt phiên active thay vì chỉ sửa file. Đổi PostgreSQL password cần thao tác DB tương ứng trước/cùng cấu hình; env không reset password đã lưu trong volume.
- Deploy key GitHub trên host đọc source khác SSH key trong git_ssh của analyst; backup/thu hồi từng key theo phạm vi riêng. Chỉ grant read cho server chỉ cần pull.

## Data protection trong application

Files/Delete chặn warehouse/backup/root incoming, yêu cầu confirmation và báo partial errors. Đây là guardrail UI/API, không là quyền storage với người có thể chạy code. Multipart preflight không khóa upload từ phiên khác.

Artifact endpoint chặn traversal, profiles.yml và secret-named files, có CSP cho Docs; notebook HTML render trong sandbox. Redaction hỗ trợ một số key/value secret nhưng không đảm bảo mọi dữ liệu nhạy cảm do code người dùng print ra đều được che. Code snapshot, notebook output, dbt artifacts và backup có thể chứa dữ liệu nhạy cảm; bảo vệ như workspace data.

UC R2 signer dùng JWT scope và thời hạn 1 giờ; API UC hiện không gắn privilege với identity người dùng. Parent credential còn có trong environment; không quảng bá đây là enforcement giữa hai host dùng chung R2 keys.

## Khi nghi credential hoặc host bị lộ

Hạn chế inbound ở provider, giữ đường quản trị hợp lệ; dừng tác vụ ghi nếu cần. Thu hồi/rotate credential ở nơi cấp, cập nhật DB/service tương ứng, restart/invalidate sessions, rà soát executions, Git changes và object access bằng công cụ provider đang có. Project chưa có SIEM/audit trail đầy đủ hay incident automation. Ghi thời điểm, phạm vi và người xử lý; không xóa log gốc trước khi thu thập bằng chứng.

## Trước khi cho người khác dùng

Xác nhận người dùng thuộc cùng trust boundary; kiểm tra HTTPS/login, private backend bindings, secret storage, backup độc lập và checklist [ACCEPTANCE.md](ACCEPTANCE.md). Ghi rõ UC auth disabled/NOSASL trong biên bản, không chỉ gửi một đường link UI có token.
