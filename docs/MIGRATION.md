# Backup catalog và chuyển host

R2 chứa dữ liệu Delta đang hoạt động. Metadata catalog đang hoạt động nằm trên PostgreSQL SSD; snapshot của nó được upload lên R2. Đáp ứng di chuyển giữa các host theo cách khôi phục snapshot, không phải gắn R2 thành ổ database.

## Bảng cũ của V2

Chép notebooks/repository bạn muốn giữ từ `V2/workspace` sang thư mục WORKSPACE_DIR của V3, tránh ghi đè code hiện có. V3 không tự đọc database H2 của V2. Có helper đọc registry tên bảng cũ trên R2, mặc định chỉ liệt kê kế hoạch:

```bash
docker compose exec -T runner python3 /opt/lakehouse/import_v2.py
docker compose exec -T runner python3 /opt/lakehouse/import_v2.py --apply
```

Lệnh thứ hai đăng ký **external tables thật trong UC V3**, giữ nguyên file Delta. Không chuyển bảng external thành managed; các bảng tạo mới bằng SQL không có LOCATION vẫn dùng managed. Helper này cần được thử với bảng cũ cụ thể trước khi bỏ V2. Nếu V2 không có registry, dùng `CREATE TABLE catalog.schema.name USING DELTA LOCATION 's3://bucket/path'` trong một phiên Spark có quyền đọc location đó.

## Backup

Đóng hoặc lưu notebook trước. Lệnh sau tạm dừng các writer và catalog, dump cả UC và Kestra, đóng gói workspace, runtime volume và Kestra storage, ghi SHA-256 rồi upload R2; cuối cùng tự bật dịch vụ trở lại:

```bash
bash scripts/backup.sh
```

Backup nằm trong `platform-backups/v3/<UTC_TIMESTAMP>/` theo BACKUP_PREFIX. Bản mới có unitycatalog.dump, kestra.dump, workspace.tar.gz, runtime.tar.gz, kestra-storage.tar.gz và manifest checksum; runtime bao gồm run artifact và history. Giữ `.env` và SSH key riêng trong bản lưu được mã hóa. Chưa có tự xóa backup; hãy đặt retention phù hợp, không áp lifecycle xóa/cold vào `warehouse/`. Cách chạy Bash helper từ Windows/WSL nằm trong [OPERATIONS.md](OPERATIONS.md).

## Khôi phục trên Ubuntu mới

1. Clone repo source V3 sang Ubuntu mới, chạy init, chọn WORKSPACE_DIR cho dữ liệu riêng và chạy init lần nữa nếu đổi đường dẫn. Điền cùng R2 bucket và các mật khẩu cũ hoặc mật khẩu PostgreSQL mới tương ứng host mới. Không khởi chạy hai host ghi đồng thời.
2. Build image: `docker compose build`. Chép `.env` an toàn; đây không phải file commit Git.
3. Chạy `bash scripts/restore.sh 20261122T000000Z --replace-metadata`, thay timestamp minh họa bằng backup cần dùng. Flag cho biết bạn chủ động thay metadata đang có trên host đích.
4. Mở notebook và SELECT một table cũ qua tên đầy đủ. Giữ host cũ dừng cho đến khi xác nhận xong.

Restore kiểm checksum trước, phục hồi database, workspace, runtime và Kestra storage. Backup V3 cũ không có runtime.tar.gz vẫn được đọc; các run còn trong workspace được runtime-init chuyển vào volume khi khởi động. File Delta vẫn ở cùng R2 location nên không tải toàn bộ 300 GB về máy mới. Không dùng `docker compose down -v`: thao tác đó xóa metadata local.

Snapshot tạo trước đợt cleanup có thể khôi phục lại ví dụ cũ cùng code tại thời điểm snapshot. Chọn đúng snapshot và rà soát workspace sau khi restore. Thay code ứng dụng không tự thay nội dung một backup đã có.

Đây là script cho single-user Compose mặc định. Nếu bật JupyterHub, cần lưu thêm hai volume `hub_state`, `hub_home` và chạy các lệnh bằng cả hai file compose. Chúng chứa tài khoản/password hash và dữ liệu home, phải lưu như secret.
