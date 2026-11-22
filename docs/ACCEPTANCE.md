# Checklist nghiệm thu và bàn giao độc lập

Checklist dùng trên môi trường đích/sandbox. Ghi **PASS / FAIL / NOT RUN / NOT APPLICABLE**, thời gian theo TZ, commit và bằng chứng trong hồ sơ nghiệm thu riêng. Một lệnh mẫu hoặc kết quả phiên bản khác không thay kiểm tra deployment hiện tại.

## Hồ sơ phiên kiểm tra

```text
Ngày/giờ/TZ:
Người thực hiện và người nhận bàn giao:
Host / OS / architecture / CPU / RAM / SSD:
Git remote / branch / commit / worktree clean:
Runtime/catalog/Kestra image IDs:
Compose project và COMPOSE_FILE:
WORKSPACE_DIR (không ghi secret):
R2 bucket / endpoint / backup prefix (không ghi key):
Chế độ truy cập: SSH tunnel / HTTP draft / HTTPS proxy:
Kết quả và các ngoại lệ chấp nhận:
```

Thông tin thực tế chưa có trong repo cần người vận hành điền; không tự dùng credential hay IP của máy dev làm hồ sơ server.

## A. Cài mới và đường quản trị

| Kiểm tra | Điều kiện đạt |
|---|---|
| SSH trước firewall | Rule đúng port/listener, login phiên thứ hai được trước khi đóng phiên cũ |
| OS/Docker | Linux engine/Compose hoạt động; RAM/disk đúng profile; hello-world chạy |
| Git source | Clone được đúng repo/commit bằng quyền server, không đưa secret vào remote URL |
| Git workspace | Luồng init/clone tự tạo ignore; encrypted key unlock; commit/push đầu rồi Git native commit/push tiếp; key được giữ qua recreate |
| Env | Root .env được ignore, mode 600, đúng credential/bucket/TZ, không chứa placeholder |
| Bind mount | Workspace nằm đúng host path và trong container là /workspace |
| Build/permission | Không có PermissionError của analyst; image regression riêng đã có bằng chứng |
| Init | bootstrap/runtime-init Exited (0); chạy lại giữ user files, config và object có sẵn |
| Service | postgres/catalog/notebook/sql/runner healthy; Kestra UI/login riêng hoạt động |

`docker compose config --quiet` kiểm cú pháp/config, không kiểm credential R2 hoặc chứng minh dữ liệu được đọc.

## B. SQL, UC và Files

Trong SQL editor chạy SQL thuần; notebook SQL cell thêm %%sql:

```sql
SELECT current_catalog(), current_schema(), current_timezone();
CREATE SCHEMA IF NOT EXISTS lakehouse.acceptance;
CREATE TABLE IF NOT EXISTS lakehouse.acceptance.handover_check USING DELTA AS
SELECT 1 AS id, 'handover' AS label;
SELECT * FROM lakehouse.acceptance.handover_check;
```

Thay lakehouse bằng catalog được phê duyệt; đây là ghi dữ liệu thật, chỉ dùng schema thử đã thống nhất. Xác nhận table xuất hiện trong Catalog, có location R2 và đọc được từ session/notebook khác sau khi restart kernel. Dùng thêm catalog mới được phê duyệt để kiểm tra tên ba phần/refresh catalogs nếu đó là phạm vi bàn giao. Sau kiểm thử, DROP TABLE qua SQL theo kế hoạch cleanup; không xóa trực tiếp folder Delta.

| Kiểm tra | Điều kiện đạt |
|---|---|
| Bootstrap R2 | warehouse/incoming/backup prefix xuất hiện hoặc nội dung cũ được dùng lại |
| Upload | File riêng trong incoming/acceptance/ đọc lại đúng nội dung |
| Nhiều file/resume | Progress theo part; cancel/resume chỉ với đúng file và session còn tồn tại |
| Delete file | Cancel giữ file; confirm xóa đúng file, sibling còn nguyên |
| Delete folder | Nhập sai path giữ nguyên; nhập đúng xóa cây con, có status và partial error khi storage từ chối |
| Protected storage | UI không có Delete cho warehouse/backup/root incoming; backend cũng từ chối target đó |
| Catalog | Tạo/list đúng catalog/schema/table; không dùng temp view để chứng minh persistence |

Chỉ dùng object thử do phiên nghiệm thu tạo. Xóa là vĩnh viễn; không cần thử xóa data thật để nghiệm thu boundary.

## C. Notebook, workflow và dbt report

1. Tạo notebook nhỏ trong workspace, xác nhận có spark/%%sql mà không cài Maven thủ công. Lưu, submit background với parameter, ghi một output JSON bằng set_output và xem Cells/Outputs/Logs của đúng Run ID.
2. Tạo workflow thử SQL hai bước dependency. Publish, Execute, xem task mapping trên Kestra và Workflow Run History.
3. Dựng Variables/If/For each theo [RUNS_WORKFLOWS.md](RUNS_WORKFLOWS.md); thử Then/Else, list rỗng, input override, failure handler và một retry có kiểm soát. Xem iteration/output và trạng thái task, không chỉ trạng thái tổng.
4. Load `dbt_sample_pipeline` → Save & publish → Execute. Không cần bật schedule. Xác nhận seed/build/docs đều SUCCESS và **7 data tests thực sự chạy** trong build; parse chỉ chứng minh project hợp lệ.
5. Trong Runs chọn dbt_sample build: xem model/test status, compiled SQL/code/log và tải run_results.json. Trong dbt panel đặt dbt_sample + đúng catalog/schema, Open Docs tải được model descriptions và lineage. Chạy lại docs sau thay model và xác nhận snapshot mới.

```sql
SELECT customer_id, order_count, total_amount
FROM lakehouse.dbt_sample.customer_totals ORDER BY customer_id;
```

Kết quả mong đợi: (101,2,150), (102,2,200), (103,1,25). Thay catalog nếu sample được tạo với tên khác.

## D. Tài nguyên, restart và giữ state

| Kiểm tra | Điều kiện đạt |
|---|---|
| RAM | Đo workload thật bằng docker stats/free; còn headroom OS/UC/PG; không chỉ cộng cap |
| Compute | Save & Restart scope SQL/kernel chọn đúng; READY; config lưu, kernel khác có thể còn cũ |
| UI tabs | Mở/đóng/mở lại Catalog/Files/Runs không cần F5; tab mới được active |
| Timezone | SQL session/UI filter/schedule dùng TZ mong muốn; ghi riêng timezone lịch |
| Container recreate | Notebook đã lưu, project dbt, Git key và table metadata còn; biến RAM trong kernel không được kỳ vọng còn |
| Interrupted jobs | Chỉ thử ở sandbox: runner restart giữ partial output, đánh dấu INTERRUPTED, không replay tự động |
| Retention | Preview nêu đúng terminal artifacts; cleanup chỉ trên run thử đủ điều kiện, giữ active run/table |

## E. Public access, restore và người tiếp nhận

HTTPS: certificate đúng hostname, login thành công, notebook WebSocket/terminal, upload multipart và Open Docs chạy trên cùng domain. Từ một máy ngoài mạng host, xác nhận private ports không truy cập được. TCP connect chỉ chứng minh reachability; không thay test TLS/login/query.

Restore drill: dùng snapshot đã xác minh, host/project/workspace đích sạch và không có writer cũ. Theo [DISASTER_RECOVERY.md](DISASTER_RECOVERY.md), xác nhận catalog/table/data checksum hoặc aggregate đã biết, notebook/workflow và artifact. Ghi RTO đo được, snapshot age và các data không được backup.

Người vận hành tự thực hiện clone → cấu hình → start → sample → report → backup/restore thử → chẩn đoán lỗi theo log. Ghi ngoại lệ và câu hỏi còn thiếu trong hồ sơ nghiệm thu, cập nhật hướng dẫn khi contract thay đổi. Chỉ ký nghiệm thu khi các mục bắt buộc có kết quả và người chịu trách nhiệm.
