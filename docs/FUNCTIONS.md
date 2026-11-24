# Functions trong SQL, Catalog và registry R2

Function có tên `catalog.schema.function`. UC giữ định nghĩa trong PostgreSQL; registry giữ bản portable trên R2 để phục hồi sang UC mới. SQL scalar function có thể tạo và gọi bằng SQL trong notebook, SQL editor và task SQL của workflow. Catalog hiển thị cùng định nghĩa đó. MCP chưa được tích hợp.

## Tạo và gọi bằng SQL

Tạo catalog/schema trước bằng Catalog UI hoặc SQL của UC connector. Trong ví dụ dưới đây, thay `lakehouse.analytics` bằng namespace của bạn. Function luôn cần tên đầy đủ ba phần, kể cả khi notebook đã chọn default catalog/schema.

Trong notebook, chạy cell:

```sql
%%sql
CREATE FUNCTION lakehouse.analytics.net_amount(
  amount DECIMAL(18,2),
  discount DECIMAL(18,2)
)
RETURNS DECIMAL(18,2)
LANGUAGE SQL
DETERMINISTIC
COMMENT 'Amount after discount'
RETURN amount - coalesce(discount, 0);
```

Cell tiếp theo:

```sql
%%sql
SELECT lakehouse.analytics.net_amount(100.00, 15.00) AS net_amount;
```

Kết quả là `85.00`. Có thể dùng cột bảng làm đối số:

```sql
%%sql
SELECT order_id,
       lakehouse.analytics.net_amount(amount, discount) AS net_amount
FROM lakehouse.analytics.orders;
```

`spark.sql(...)` trên SparkSession tự nạp trong notebook cũng đi qua cùng lớp tích hợp. SQL editor và workflow task loại SQL dùng nguyên câu SQL trên, **bỏ dòng `%%sql`**. Notebook chạy trong workflow nạp startup giống notebook tương tác.

Spark kiểm tra kiểu và biểu thức trước khi đăng ký UC. Nếu biểu thức lỗi, function không được ghi vào UC/R2. Khi registry được bật, đăng ký thành công chỉ được trả về sau khi đồng bộ R2 thành công. Mở Catalog, chọn namespace, Refresh và Asset type = Functions để xem.

## Xem, sửa và xóa

```sql
SHOW FUNCTIONS IN lakehouse.analytics;
SHOW USER FUNCTIONS IN lakehouse.analytics LIKE 'net*';
DESCRIBE FUNCTION EXTENDED lakehouse.analytics.net_amount;
```

`SHOW` trong namespace hai phần trả các function UC của schema; pattern hỗ trợ `*` và `?`. `DESCRIBE` trả tên, kiểu trả về, body, comment và các tham số dưới dạng bảng.

Sửa body cùng tên bằng:

```sql
CREATE OR REPLACE FUNCTION lakehouse.analytics.net_amount(
  amount DECIMAL(18,2), discount DECIMAL(18,2)
)
RETURNS DECIMAL(18,2)
RETURN greatest(amount - coalesce(discount, 0), 0);
```

`OR REPLACE` yêu cầu giữ nguyên tên/kiểu/thứ tự tham số. Khi đổi chữ ký, tạo tên function mới để tránh làm hỏng caller. `CREATE FUNCTION IF NOT EXISTS ...` giữ nguyên định nghĩa nếu tên đã có; không dùng cùng `OR REPLACE`.

```sql
DROP FUNCTION IF EXISTS lakehouse.analytics.net_amount;
```

SQL DROP không mở hộp xác nhận. Trong Catalog UI, Delete function yêu cầu gõ full name. Cả hai đường đều xóa định nghĩa UC và đồng bộ R2; sau sync thành công, host mới không phục hồi function đã xóa. `current.json` không cung cấp thùng rác hoặc lịch sử phiên bản.

UC 0.7 chưa có PATCH function. `OR REPLACE` dùng endpoint nội bộ có khóa và kiểm hash định nghĩa cũ, rồi delete/create; hai lệnh UC **không atomic**, function có thể vắng mặt ngắn hạn và ID có thể đổi. Không bảo toàn grants/ownership qua cách thay thế này. Workspace hiện dùng UC authorization disabled, không có quyền EXECUTE riêng từng user được enforce.

Registry ghi replacement intent vào state local trước delete. Nếu tạo mới thất bại và tên đang trống, nó thử phục hồi định nghĩa cũ trước khi xuất registry, giữ bản R2 cuối cùng nếu phục hồi chưa thành công. Nếu thay đổi UC đã xong nhưng R2 lỗi, trạng thái chuyển pending. Đọc lại định nghĩa và kiểm Compute → Catalog registry on R2 trước khi retry; không xóa database/state để chữa lỗi.

## Workflow ví dụ

Trong Workflows, thêm hai task SQL:

1. Task `define_function`: câu `CREATE FUNCTION IF NOT EXISTS ...` ở trên.
2. Task `calculate`, Depends on = `define_function`:

```sql
SELECT lakehouse.analytics.net_amount(100.00, 15.00) AS net_amount;
```

Save & publish rồi Execute. Xem task và kết quả trong Workflow run history → execution → task → run detail. Không cần tạo lại function mỗi lần chạy nếu nó đã đăng ký. Các task SQL có session Thrift riêng nhưng dùng chung UC definition.

## Phạm vi SQL được hỗ trợ

| Nội dung | Hành vi |
|---|---|
| DDL | CREATE [OR REPLACE] FUNCTION [IF NOT EXISTS], RETURNS, LANGUAGE SQL, COMMENT, [NOT] DETERMINISTIC, RETURN; SHOW/DESCRIBE/DROP như trên |
| Tên | Bắt buộc `catalog.schema.function`; identifier chữ, số, underscore, bắt đầu bằng chữ/underscore; có thể bọc backtick |
| Tham số / return | INT/INTEGER, BIGINT/LONG, SMALLINT/SHORT, TINYINT/BYTE, STRING, BOOLEAN, FLOAT, DOUBLE, DATE, TIMESTAMP, BINARY, DECIMAL/NUMERIC(p,s), p tối đa 38 |
| Body | Một biểu thức scalar Spark SQL: phép tính, CASE, built-in scalar functions, gọi function UC khác bằng full name |
| Dependency | Nạp theo full name, từ chối chu trình; tối đa 16 mức và 100 function mỗi statement |
| Batch SQL | Tối đa 100 statement, chạy tuần tự và trả kết quả statement cuối; không có transaction chung/rollback batch |
| Chưa hỗ trợ | RETURNS tự suy luận, parameter DEFAULT/COMMENT trong DDL, complex types, table-valued function, subquery/table query, aggregate/window, Python body/external runtime |

`CREATE TEMPORARY FUNCTION` và `spark.udf.register(...)` vẫn là chức năng session của Spark, không tự lưu vào UC/R2. Code Python `def ...` cũng không tự được đăng ký.

Đây là lớp tích hợp tại đường gọi SQL của Lakehouse, không phải implementation FunctionCatalog trong Spark connector. Chỉ `%%sql`, `spark.sql` của session tự nạp, SQL editor và workflow SQL/notebook được tích hợp. Session tự tạo bằng `newSession()`, DataFrame `selectExpr`/`expr`, raw JDBC/ODBC/Thrift, Power BI hoặc dbt gọi trực tiếp Thrift không tự phân giải function UC bằng lớp này. Không dùng managed function trong persistent view: Spark không cho view bền vững tham chiếu temporary function nội bộ.

Mỗi statement gọi full name sẽ đọc lại UC và nạp SQL temporary function nội bộ vào session Spark. Session mới hoặc Spark restart vì vậy không cần chạy lại CREATE. Thay đổi/delete UC có hiệu lực với lần gọi full name tiếp theo; truy vấn/DataFrame đã phân tích có thể vẫn giữ biểu thức cũ. Không sử dụng tên `_lh_uc_...` nội bộ trong code của bạn.

## Quản lý định nghĩa bằng Catalog UI

Mở Catalog → chọn namespace → **+ Function**. Form nhận Language PYTHON hoặc SQL, Return type, Input parameters, Description và Function body. Ví dụ SQL: parameters `[{"name":"value","type":"INT"}]`, return type `INT`, body `value + 1`. Chọn function để xem/copy full name/xóa.

Form chỉ đăng ký metadata, không biên dịch body. SQL definition có kiểu/body thuộc phạm vi trên sẽ được kiểm tra bởi Spark khi gọi từ managed SQL. Form scalar hỗ trợ các kiểu đơn giản; dùng SQL DDL cho DECIMAL(p,s), hoặc UC API/native function_info cho definition phức tạp. Definition Python được lưu/xem/replay nhưng chưa có runtime thực thi.

Không ghi credential vào body/comment/default parameter. Registry chứa source function nên phải được bảo vệ như code riêng tư. Giữ source và dependency package trong Git.

## Nội dung trên R2 và phục hồi

Vị trí: `s3://<bucket>/<UC_REGISTRY_PREFIX>/current.json`. Collection `functions` lưu definition UC trả về: namespace, input/return parameters, type metadata, routine body/definition/language, comment, flags và các trường definition được allowlist. ID, owner, created/updated audit fields không replay. Dependency metadata không tự deploy thư viện/hệ thống bên ngoài.

UC 0.7 có các trường experimental backend có thể không persist/return, ví dụ function properties. Registry không suy diễn hoặc phục hồi trường UC chưa lưu. Các trường core được giữ: tên, tham số, kiểu trả về, body/language, comment và flags.

Khi UC mới trống: phục hồi catalogs → schemas → external volumes/tables → functions trước bootstrap. Startup replay chỉ tạo metadata, không chạy body. Lần truy vấn managed SQL sau đó nạp body vào Spark. Định nghĩa cùng tên khác nội dung gây conflict; không tự ghi đè. Managed table/volume có giới hạn replay riêng theo [CATALOG_REGISTRY](CATALOG_REGISTRY.md).

## Nâng cấp và API

Code đọc manifest v1/v2/v3. v1 chưa có functions được hiểu là danh sách rỗng; sync dùng ít nhất v2 và nâng v3 khi có SQL view definitions. Không đổi UC_REGISTRY_PREFIX, reset PostgreSQL hoặc sửa current.json bằng tay. Code cũ từ chối version chưa hỗ trợ; rollback theo [DISASTER_RECOVERY](DISASTER_RECOVERY.md), không ép version bằng tay. View portable theo [VIEWS](VIEWS.md).

Nâng cấp bằng Git và rebuild theo [OPERATIONS](OPERATIONS.md); restart notebook kernel để nạp wrapper `spark.sql` mới. Không cần reset data/metadata. Kiểm registry healthy và thử một CREATE/SELECT trong namespace sandbox trước khi áp dụng cho job thật.

Gateway function metadata và endpoint private compare-and-replace được mô tả tại [API](API.md). Gọi native UC qua UC_URL registry proxy để có acknowledgement R2. Không publish runner/registry hoặc bypass trực tiếp backend. Tham khảo [Spark SQL functions](https://spark.apache.org/docs/latest/sql-ref-syntax-ddl-create-sql-function.html) và [UC API v0.7.0](https://raw.githubusercontent.com/unitycatalog/unitycatalog/v0.7.0/api/all.yaml).
