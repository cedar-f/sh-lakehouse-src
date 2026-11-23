# dbt project: catalog, schema và chuỗi model

Project dbt là source của notebook/model/workflow trong repository workspace. Runner cấp kết nối Spark SQL Thrift; không đưa profiles.yml, credential R2 hoặc mật khẩu vào project.

## Chọn chế độ cấu hình

Khai báo `vars.lakehouse_catalog` ở cấp gốc của dbt_project.yml để bật **project mode**. Đây là quy ước của Lakehouse runner, không phải trường catalog native của dbt-spark. Giá trị phải là tên literal gồm chữ/số/underscore, bắt đầu bằng chữ/underscore; không hỗ trợ Jinja/env_var cho trường này. Mỗi project dùng một catalog, có thể có nhiều schema.

Trong project mode:

- Catalog lấy duy nhất từ vars.lakehouse_catalog. Catalog phải được tạo trong Catalog UI trước, với storage root phù hợp.
- Schema đầu ra khai báo bằng +schema trong project theo thư mục hoặc từng model. Tên dùng nguyên giá trị, không thêm tiền tố từ target.schema.
- Model/seed/snapshot enabled thiếu schema sẽ lỗi khi parse; không fallback sang DEFAULT_SCHEMA của Compute/env. Mọi resource enabled được kiểm tra, kể cả khi Selection chỉ chọn một phần.
- +schema trong dbt_project.yml phải là literal identifier; phải có ít nhất một schema tại đây. Cấu hình schema trực tiếp trong model vẫn theo quy tắc exact name và được kiểm tra sau parse. Không khai báo +database/+catalog; sources cũng không đặt database/catalog khác.
- Không truyền lakehouse_catalog qua Parameters/dbt vars. Workflow chỉ chọn đường dẫn project, command, selection và biến nghiệp vụ.

Project không có vars.lakehouse_catalog vẫn chạy **legacy mode**: giữ Target catalog/schema cũ hoặc mặc định Compute/env. Trong UI, các trường này nằm trong **Legacy project overrides**. Không bỏ qua override xung đột một cách âm thầm: project mode từ chối schema override và catalog khác cấu hình project.

## Ví dụ source → schema a → schema b

Tạo catalog analytics trước. Bảng analytics.raw.orders cần có sẵn với các cột order_id, customer_id, amount. Cấu trúc project:

```text
dbt/
  dbt_project.yml
  models/
    sources.yml
    staging/stg_orders.sql
    marts/fct_orders.sql
  macros/
    lakehouse_schema.sql
```

dbt_project.yml:

```yaml
name: analytics_project
version: '1.0.0'
config-version: 2
profile: lakehouse
model-paths: [models]
vars:
  lakehouse_catalog: analytics
models:
  analytics_project:
    +materialized: table
    +file_format: delta
    staging:
      +schema: a
    marts:
      +schema: b
```

models/sources.yml:

```yaml
version: 2
sources:
  - name: landing
    schema: raw
    tables:
      - name: orders
```

models/staging/stg_orders.sql:

```sql
select order_id, customer_id, amount
from {{ source('landing', 'orders') }}
where amount > 0
```

models/marts/fct_orders.sql:

```sql
select customer_id, count(*) as order_count, sum(amount) as total_amount
from {{ ref('stg_orders') }}
group by customer_id
```

Một task dbt command build, Workspace path dbt, Selection +fct_orders, Parameters {} sẽ dựng analytics.a.stg_orders trước analytics.b.fct_orders. Không cần For each; ref() biểu diễn dependency. Để trống Selection nếu muốn build toàn bộ project. Lệnh table dựng lại bảng; append/merge cần model incremental riêng.

Để chọn schema cho từng model thay vì theo thư mục, ví dụ với file models/stg_orders.sql và models/fct_orders.sql:

```yaml
models:
  analytics_project:
    stg_orders:
      +schema: a
    fct_orders:
      +schema: b
```

Khai báo tương tự dưới seeds/snapshots nếu dùng chúng. Model dependency nên dùng ref(); nguồn có sẵn dùng source(). Viết tên bảng SQL cố định không được tự chuyển catalog và không tạo dbt lineage.

## Macro schema và kết nối nội bộ

Lần đầu chạy project mode, runner thêm macros/lakehouse_schema.sql (hoặc macro-paths đầu tiên) nếu project chưa định nghĩa generate_schema_name. File này thuộc source workspace và có thể commit bằng Git native. Nó dùng schema được khai báo nguyên tên và báo lỗi resource thiếu schema. Nếu đã có macro riêng, runner giữ nguyên, không ghi đè; manifest sau parse phải chứng minh schema cuối đúng schema khai báo. Macro cũ ghép tiền tố cần được sửa thủ công theo quy tắc này.

dbt-spark vẫn yêu cầu schema trong profile kết nối. Runner chọn schema đầu tiên theo thứ tự chữ từ các +schema khai báo trong project, tạo namespace này trong catalog nếu thiếu, rồi dùng nó làm schema kết nối. Nó không phải fallback cho model và không tạo schema default trong catalog project. dbt tạo các schema đầu ra còn lại khi thực thi. Namespace có thể còn lại nếu job thất bại sau bước chuẩn bị.

dbt_job.py chỉ trong subprocess dbt sửa lời gọi PyHive connect để dùng schema kết nối đã chọn, thay vì USE default mặc định của thư viện. Sau dbt parse, runner kiểm tra manifest trước khi thực thi model/seed/snapshot. deps không cần SQL; debug chỉ kiểm tra cấu hình/kết nối, không thay thế parse/build để kiểm tra toàn bộ model.

Compute/bootstrap của platform và legacy project vẫn có default schema cho notebook/SQL/incoming volume. Nâng cấp không xóa hoặc di chuyển schema/bảng đã có. Catalog/schema đầu ra project có thể khác hoàn toàn mặc định Compute.

## Vận hành, Docs và chuyển project cũ

1. Trong repo source trên Ubuntu, git pull --ff-only rồi bash scripts/rebuild.sh; Windows dùng .\scripts\start.ps1 để build/start. Không reset metadata để nâng cấp tính năng này. Refresh trình duyệt sau rebuild.
2. Trong repo workspace, thêm vars.lakehouse_catalog và +schema cho toàn bộ model/seed/snapshot cần dùng. Giữ nguyên vị trí bảng cũ nếu muốn tiếp tục ghi đúng nơi cũ.
3. Mở tab dbt hoặc từng task workflow, xóa Legacy target schema và catalog override khác project; Apply task changes, Save & publish lại flow. Flow đã publish không tự cập nhật.
4. Chạy deps nếu có packages, debug, build, test, docs. Không cần nhập Target schema trong chế độ project. Từ Runs → View → Parameters kiểm tra Resolved dbt destination và Code snapshot.
5. Commit dbt_project.yml, model, YAML và macro vào repo workspace. Existing project/flow sample được bootstrap giữ nguyên, không tự migrate.

Open Docs lấy snapshot thành công còn lưu gần nhất của đường dẫn project và catalog ở project mode. Sau khi đổi model/schema, bấm docs để generate mới. Run Results/Models nằm ở Runs; Docs không thay thế kết quả test của một build cụ thể. Artifact lưu trong lakehouse_data, áp dụng retention chung theo [OPERATIONS](OPERATIONS.md).

Đổi catalog/schema không tự chuyển hoặc xóa dữ liệu cũ. Không dùng lại một catalog/schema cho dev và production nếu không muốn các model cùng tên ghi chung vị trí. Per-model catalog, nguồn khác catalog qua source.database và nhiều catalog trong một build chưa được hỗ trợ; cần adapter khác hoặc mở rộng adapter, không chỉ đổi YAML.

## Chẩn đoán

| Lỗi | Xử lý |
|---|---|
| dbt_project.yml not found | Nhập thư mục chứa file tương đối từ /workspace; dùng . khi file ngay root |
| Catalog ... does not exist | Tạo catalog qua Catalog UI, không đổi sang mặc định để né lỗi |
| Declare +schema | Bổ sung schema cho model/seed/snapshot hoặc package enabled; kiểm cả resource ngoài Selection |
| Schema macro must return ... exactly | Sửa generate_schema_name hiện có, bỏ phép ghép target.schema |
| Catalog/schema are owned ... | Xóa override cũ trong panel/flow rồi publish lại |
| Cannot set database in spark | Bỏ +database/database khỏi model/source; chọn catalog bằng vars.lakehouse_catalog |
| DBT project chạy vào vị trí cũ | Kiểm YAML có bật project mode, đúng workspace path và flow đã publish, xem Resolved dbt destination |

Nguồn: [dbt custom schemas](https://docs.getdbt.com/docs/build/custom-schemas), [Spark profile](https://docs.getdbt.com/docs/local/connect-data-platform/spark-setup), [dbt source/ref practices](https://docs.getdbt.com/best-practices/best-practice-workflows).
