# Files, bootstrap R2, rebuild và dbt sample

## Cập nhật từ Git trên Ubuntu

Đẩy commit source mới từ máy dev lên cùng repository mà Ubuntu đã clone. Trên Ubuntu:

```bash
cd ~/data/sh-lakehouse-src
git status --short
git pull --ff-only
bash scripts/rebuild.sh
```

Lưu notebook và chờ job kết thúc trước khi rebuild. Nếu Git báo có thay đổi local, lưu/commit phần đó trước khi pull; không dùng reset hard để bỏ qua. `.env` riêng và workspace không bị Git thay thế. Build lại image là bắt buộc để nhận backend và frontend mới; restart container bằng image cũ chưa có tính năng mới. Sau khi xong, refresh trình duyệt bằng Ctrl+F5.

## R2 được khởi tạo thế nào?

Script start chạy lại bootstrap trước khi bật toàn bộ dịch vụ. Các prefix mặc định:

```text
<R2_BUCKET>/
  warehouse/             Dữ liệu bảng Delta
  incoming/              File upload
  platform-backups/
    v3/                  Vị trí backup theo BACKUP_PREFIX
```

R2 là object storage; folder là prefix của object key. Khi prefix chưa có object, bootstrap tạo marker 0 byte với key kết thúc bằng `/`. Nếu đã có nội dung, dùng lại prefix đó; không ghi đè object/marker, không di chuyển hoặc xóa dữ liệu. Prefix backup đổi theo BACKUP_PREFIX trong `.env`. Bucket phải được tạo sẵn và credential R2 cần quyền đọc/ghi object.

Catalog/schema nằm trong PostgreSQL/UC. Không tạo folder giả tương ứng từng table; UC/Spark tạo location và `_delta_log` khi thực sự ghi Delta table. Vì vậy `warehouse/` có thể trống trước lần ghi đầu tiên.

## Làm lại metadata khi đã xóa sạch R2

Xóa object R2 không tự xóa metadata table trong PostgreSQL. Chỉ khi bạn chủ động muốn bỏ toàn bộ metadata/lịch sử cũ trên host này, chạy:

```bash
cd ~/data/sh-lakehouse-src
bash scripts/rebuild.sh --reset-metadata
```

Script build image và kiểm tra kết nối/khởi tạo prefix R2 trước. Nếu credential bị từ chối, dừng trước khi xóa metadata. Khi kiểm tra đạt, flag này dừng stack và xóa **4 named volumes của đúng Compose project**: postgres_data (UC + database Kestra), lakehouse_data (history/log/artifact và trạng thái upload), kestra_storage, kestra_tmp. Catalog, workflow execution history và run history cũ trên host bị xóa. Script từ chối external volume hoặc volume không mang label sở hữu đúng project; không ép xóa volume còn đang được sử dụng.

`.env`, file workspace, SSH key volume và cache Maven được giữ nguyên. Script không xóa bất kỳ object R2 nào, kể cả khi bucket đã có dữ liệu trở lại. Không dùng reset metadata cho một kho dữ liệu cần kế thừa: dùng [MIGRATION.md](MIGRATION.md). Reset không phục hồi object R2 đã xóa.

## File và folder Delete

Trong **Files**, mỗi file/thư mục con dưới `incoming/` có nút **Delete**. File có hộp xác nhận; folder yêu cầu nhập nguyên đường dẫn, ví dụ `incoming/orders/`, rồi xác nhận xóa cả nội dung.

UI hiển thị số object đã xóa, trạng thái đang chạy, lỗi theo từng object và nút **Stop after current batch**. Mỗi request xử lý tối đa 1000 object; dừng không hoàn tác các object đã xóa. Nếu R2 từ chối một phần, giao diện báo lỗi và giữ các object chưa xóa. Folder rỗng và marker cũng được xử lý.

Thư mục gốc `incoming/` được giữ làm landing folder. `warehouse/` và backup chỉ đọc trong Files; xóa table bằng SQL qua catalog. Xóa object là vĩnh viễn, không có thùng rác. Cần hoàn tất/cancel upload đang có ở đường dẫn đó trước khi xóa; không upload đồng thời vào folder đang xóa từ phiên khác.

## dbt project và workflow có sẵn

Bootstrap mặc định tạo khi chưa tồn tại:

```text
/workspace/
  dbt_sample/
    dbt_project.yml
    seeds/sample_orders.csv
    models/customer_totals.sql
    models/schema.yml
  workflows/
    dbt_sample_pipeline.json
    dbt_sample_pipeline.yml
```

Đây là template đi cùng source hệ thống, không phải bản sao project dbt cá nhân. Nếu thư mục `dbt_sample` hoặc flow đã có, giữ nguyên phiên bản đang dùng. Muốn tắt tạo sample mới, thêm `SEED_SAMPLE_DBT=false` vào `.env`. Không tự xóa sample đã tồn tại.

Trong **Workflows**, chọn `dbt_sample_pipeline` → **Load** → **Save & publish to Kestra** → **Execute saved flow**. Flow không có lịch tự chạy và không tự chạy khi bootstrap. Các bước là:

1. `seed`: nạp 5 order mẫu từ CSV.
2. `build`: dựng model và chạy 7 data tests.
3. `docs`: sinh tài liệu dbt.

Flow dùng catalog DEFAULT_CATALOG tại thời điểm tạo và schema riêng `dbt_sample`. Theo dõi **Workflow Run History**; có thể xem cùng flow trong Kestra namespace `lakehouse.v3` sau khi publish.

## Xem dbt report

Có hai nơi xem khác nhau:

**Kết quả thực thi và test:** mở **Runs**, filter Type = dbt, tìm lần chạy `dbt_sample · build`, chọn **View**. Xem Models/test status, Logs, Code và Artifacts. `run_results.json` chứa kết quả từng model/test của lần chạy đó; `manifest.json` mô tả project tại thời điểm chạy. Workflow Run History cho biết bước seed/build/docs nào thành công hoặc thất bại.

**Tài liệu, columns và lineage:** mở tab **dbt**, đặt Project directory = `dbt_sample`, Target catalog = catalog đã dùng trong flow, Target schema = `dbt_sample`. Sau khi bước docs thành công, bấm **Open Docs**. Trang mở ở tab trình duyệt mới qua chính cổng Jupyter đang dùng, không cần mở thêm port dbt. Cho phép popup nếu trình duyệt chặn. Docs là snapshot của lần generate gần nhất; sau khi sửa model, chạy lại docs để cập nhật.

Kiểm tra dữ liệu qua SQL, thay `lakehouse` nếu dùng catalog khác:

```sql
SELECT * FROM lakehouse.dbt_sample.customer_totals ORDER BY customer_id;
```

| customer_id | order_count | total_amount |
|---|---:|---:|
| 101 | 2 | 150 |
| 102 | 2 | 200 |
| 103 | 1 | 25 |

Nếu tạo SQL cell trong notebook, thêm `%%sql` trước câu SELECT.

## Lỗi R2 Unauthorized khi bootstrap

Kiểm tra lại R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET và S3_ENDPOINT trong `.env` trên chính Ubuntu. Nếu đã đổi key sau khi chép file từ Windows, cập nhật file Ubuntu. Cần bộ S3 Access Key/Secret của R2 còn hiệu lực và được cấp quyền cho đúng bucket; Cloudflare API Bearer token không thay thế hai giá trị đó. Không reset metadata để chữa lỗi credential.
