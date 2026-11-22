# JupyterHub cho nhiều tài khoản tin cậy

Chế độ mặc định dùng Jupyter token một user. Chế độ Hub dùng PAM/Linux account, notebook server riêng theo user và cùng thư mục workspace. **Tất cả user thuộc cùng miền tin cậy và dùng chung quyền dữ liệu**; UC per-user authorization chưa bật.

Trước khi bật, lưu notebook và dừng service notebook:

```bash
docker compose stop notebook
docker compose -f compose.yaml -f compose.hub.yaml up -d notebook
docker compose -f compose.yaml -f compose.hub.yaml exec --user root notebook bash -c 'mkdir -p /var/lib/lakehouse/runtime/notebook/spark-tmp /var/lib/lakehouse/runtime/notebook/warehouse /var/lib/lakehouse/runs; chgrp -R 1000 /var/lib/lakehouse; chmod -R g+rwX /var/lib/lakehouse; find /var/lib/lakehouse -type d -exec chmod g+s {} +'
bash scripts/hub-user.sh admin
bash scripts/hub-user.sh analyst2
```

Script yêu cầu nhập password trực tiếp trong terminal, tạo home và startup Spark. Account/password hash được lưu ở volume hub_state và khôi phục khi thay container; home ở hub_home. Sau đó mở `http://localhost:8888`, đăng nhập bằng username/password vừa tạo. HUB_ADMIN trong .env mặc định `admin`.

Khi vận hành Hub, luôn dùng `docker compose -f compose.yaml -f compose.hub.yaml ...` để các lần recreate giữ đúng chế độ. Backup hai volume hub_state và hub_home riêng với quyền truy cập chặt chẽ. Chế độ này chưa được xem là cơ chế phân quyền table, volume hay workflow theo từng người.

Lệnh quyền truy cập volume phía trên dành cho workspace tin cậy dùng chung group 1000. Sau khi tạo user, kiểm tra tạo notebook, Spark startup, chạy SQL và tải artifact bằng user đó; nghiệm thu Hub riêng với từng user và giới hạn quyền đã xác định. Mỗi user có SSH agent riêng được khởi động qua start_singleuser.py, key lưu trong home của user trên hub_home. Mở khóa key của đúng user trong tab GitHub. Proxy PID của Hub ở `/srv/jupyterhub/jupyterhub-proxy.pid` trong hub_state; workspace không dùng để lưu PID.

Để quay lại single-user, dừng service notebook bằng cả hai compose file rồi chạy `docker compose up -d notebook` với compose mặc định. Bảo toàn hub_home/hub_state nếu muốn bật Hub trở lại sau này.
