# SQL Views trong Unity Catalog

View là câu truy vấn có tên bền vững `catalog.schema.view`, được UC lưu dưới collection tables với `table_type=VIEW`. View giữ SQL definition, schema cột, comment và dependency; không ghi một bản sao dữ liệu kết quả ra R2. PostgreSQL phục vụ metadata đang chạy, registry R2 giữ definition portable để dựng lại host. Xem [CATALOG_REGISTRY](CATALOG_REGISTRY.md).

## Tạo và sử dụng

Trong **Catalog**, chọn catalog/schema → **+ View**, nhập tên, comment tùy chọn và một câu SELECT/WITH. Nguồn phải tồn tại và query phải phân tích được. Nút này không thay thế object cùng tên. Có thể dùng SQL editor, workflow SQL hoặc notebook tự nạp Spark; notebook thêm `%%sql` ở đầu cell:

```sql
CREATE VIEW lakehouse.default.v_events
COMMENT 'Các sự kiện được sử dụng trong báo cáo'
AS SELECT id, created_at FROM lakehouse.default.customer_events;

SELECT * FROM lakehouse.default.v_events;
```

Thay namespace/bảng/cột theo dữ liệu thực tế. Khi dùng namespace vừa tạo, SQL cell tự refresh catalog; Python có thể gọi `refresh_catalogs()` trước `spark.sql(...)`. Dùng tên ba phần cho nguồn để định nghĩa rõ dependency; không tham chiếu temporary view hoặc temporary function.

**Asset type → Views** liệt kê riêng views. Chọn một view để xem ID/audit metadata UC, columns, SQL definition, dependency và Preview. Có nút copy full name, ID, SQL và mở SQL notebook. Refresh giữ filter và view đang xem nếu object vẫn tồn tại. Ngày giờ hiển thị theo TZ workspace.

Chọn checkbox → **Delete selected views**, kiểm đúng full names và nhập `DELETE`. Mỗi batch tối đa 100 views, dừng khi lỗi và báo trạng thái từng object. Backend kiểm lại `table_type=VIEW` rồi chạy `DROP VIEW`; không dùng nút này để DROP TABLE. Nguồn dữ liệu còn nguyên nhưng downstream view/query có thể lỗi sau khi view bị xóa.

## Engine và giới hạn

Native UC ViewCatalog cần Spark 4.2. Runtime sử dụng Spark 4.2.0, Delta 4.4.1 và UC Spark connector 0.7.0 cho Spark 4.2; xem [VERSIONS](VERSIONS.md). View dùng được trong session Spark/Thrift được cấu hình cùng catalog, không chỉ tồn tại trong một notebook. Client Power BI/ODBC vẫn cần cấu hình kết nối theo [EXTERNAL_CLIENTS](EXTERNAL_CLIENTS.md).

Connector UC hiện không hỗ trợ replace/alter/rename view. Không dùng `CREATE OR REPLACE VIEW` để cập nhật view đã có. Cách có kiểm soát: tạo view tên mới, kiểm kết quả, đổi downstream query rồi xóa view cũ khi phù hợp. `DROP VIEW` rồi `CREATE VIEW` cùng tên có khoảng gián đoạn và có thể mất definition nếu CREATE thất bại; không có atomic replacement.

dbt-spark mặc định phát SQL `CREATE OR REPLACE VIEW`; không cam kết materialization `view` chạy lặp lại trên UC này. Dùng Delta `table`/`incremental` cho model dbt, hoặc tạo view một lần bằng SQL sau khi dbt build nguồn. Không tự sửa macro project hay âm thầm DROP view khi dbt chạy. Xem [DBT_PROJECTS](DBT_PROJECTS.md). SQL scalar function của lớp Lakehouse được biên dịch thành temporary function nội bộ, nên chưa dùng được trong persistent view; xem [FUNCTIONS](FUNCTIONS.md). Metric/materialized view không thuộc phạm vi tính năng này.

## Lưu và phục hồi trên R2

Registry giữ `view_definition`, `view_dependencies`, columns, comment và properties trong manifest v3 tại key registry hiện có. Sau khi phục hồi namespace, external tables và functions, registry đăng ký views theo thứ tự dependency. Source thiếu, managed source chưa phục hồi, dependency vòng hoặc view cũ thiếu definition được giữ inventory và báo `unrestored`; không tự tạo source giả hoặc suy ra SQL từ dữ liệu Delta. ID/owner/grants/audit timestamp được UC mới cấp lại, không replay nguyên trạng.

Sau upgrade dùng **Compute → Sync registry now**, kiểm counts và `unrestored`. View SQL/property có thể chứa thông tin nghiệp vụ nhạy cảm; registry phải private. Không sửa version manifest bằng tay để rollback.

Nguồn: [UC SQL Views](https://unitycatalog.io/docs/how-to/sql-views/), [UC connector Spark 0.7.0](https://raw.githubusercontent.com/unitycatalog/unitycatalog/v0.7.0/connectors/spark/src/main/scala/io/unitycatalog/spark/UCSingleCatalog.scala), [UC API](https://raw.githubusercontent.com/unitycatalog/unitycatalog/v0.7.0/api/all.yaml).
