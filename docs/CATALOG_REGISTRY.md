# Registry metadata Unity Catalog trên R2

Registry giữ định nghĩa portable của UC độc lập với vòng đời PostgreSQL local. Đây là JSON metadata hiện tại, không là database dump và không copy table/file data. PostgreSQL vẫn phục vụ UC trong lúc chạy. Registry không thay thế backup dữ liệu Delta hoặc backup toàn bộ UC/Kestra/workspace.

## Phạm vi

| Đối tượng | Nội dung giữ trên R2 | Khi UC mới trống |
|---|---|---|
| Catalog, kể cả rỗng | name, comment, properties, storage_root; storage_location được giữ để tham khảo | Tạo lại tên/comment/properties/root; ID và managed location được UC cấp lại |
| Schema, kể cả rỗng | catalog cha, name, comment, properties, storage_root riêng nếu có | Tạo lại sau catalog; không suy ra từ danh sách bảng |
| External volume | catalog/schema/name, comment, type và storage_location | Đăng ký lại cùng location, không ghi file dữ liệu |
| External Delta table | Namespace/name, location, columns, properties, comment, format/type | Đăng ký metadata qua UC API, không copy hoặc overwrite Delta |
| Function | Namespace, tham số/return types, body/language, comment và flags UC trả về | Tạo lại definition sau namespace; không thực thi code |
| Managed table/volume và các loại table khác | Giữ inventory/định nghĩa để không mất dấu location | Không replay thành external hoặc cấp một managed location mới để giả phục hồi; báo unrestored |

Object unrestored được hiện trong Compute. Registry vẫn giữ bản ghi nếu namespace cha còn, và chặn tạo table/volume cùng tên qua proxy để tránh thay thế inventory cũ. Sau khi khôi phục bằng phương án riêng và UC có object cùng tên, định nghĩa UC mới thay bản inventory. DROP namespace cha chủ động sẽ loại inventory con khỏi registry ở lần sync kế tiếp. Phục hồi managed nguyên trạng cần database UC tương thích; không tự sửa ID/coordinator hoặc Delta log để ép nhận lại.

Owner, grants, ID/audit timestamps UC, models/views đầy đủ, Spark config, env, credential, notebook, Git, workflow và run history không được phục hồi bởi registry này. Field cấu hình được giữ là properties/storage root của UC, không phải mọi cấu hình của server. Secret kết nối vẫn ở env/secret store.

## Vị trí và cấu hình

Mặc định: `s3://<R2_BUCKET>/_lakehouse/registry/v1/current.json`.

```dotenv
UC_REGISTRY_ENABLED=true
UC_REGISTRY_PREFIX=_lakehouse/registry/v1
UC_REGISTRY_SYNC_SECONDS=60
REGISTRY_MEMORY=256m
```

Các biến có default nên env cũ không bắt buộc thêm ngay. Prefix phải riêng, không nằm trong warehouse/incoming; không đặt lifecycle xóa registry nếu muốn dùng để dựng lại host. Chỉ dùng cùng bucket cấu hình; location trong registry phải là path s3/s3a thuộc bucket đó. Identifier phải theo quy tắc tên của UI project. JSON tối đa 16 MiB, có version/bucket và kiểm quan hệ cha/con. Manifest v2 bổ sung functions; code mới đọc v1 và conditional-upgrade lên v2 tại cùng key. Code cũ từ chối v2; xem [FUNCTIONS](FUNCTIONS.md) trước rollback.

Registry là object private, dùng bộ R2 S3 credential hiện có; không có secret cố định hoặc temporary credential được xuất từ UC. Function source/defaults có thể chứa literal nhạy cảm do tác giả nhập; không ghi credential trong function. Custom properties có thể chứa nội dung do người dùng đặt nên cần bảo vệ registry như metadata nhạy cảm. Không public bucket/prefix.

## Luồng khởi động

```text
PostgreSQL healthy → UC backend healthy + runtime-init complete
→ registry đọc R2, kiểm tra hoặc phục hồi UC
→ registry healthy → bootstrap → notebook/SQL → runner → Kestra
```

Nếu R2 chưa có registry, service xuất UC hiện tại thành registry mới bằng conditional create. Nếu UC trống và registry hợp lệ đã có, phục hồi catalog → schema → external volume → external Delta table → functions trước bootstrap. Catalog/schema rỗng vẫn có bản ghi riêng. Restore ngắt giữa chừng có marker local để tiếp tục idempotent; object có tên trùng nhưng định nghĩa khác bị từ chối, không tự ghi đè.

Nếu UC đã có metadata khác registry và không có lineage local khớp, service không chọn bên nào thay người vận hành. Startup dừng với thông báo conflict. Chỉ một host được quản lý registry tại một thời điểm; đây không phải cơ chế workspace đa writer.

Registry không tự suy ra được tên/comment của UC đã bị xóa trước lần export đầu tiên. Chỉ có data Delta trên R2 không đủ để phục hồi namespace rỗng hay comment đã mất.

## Đồng bộ trong lúc chạy

UC_URL của notebook/SQL/runner trỏ tới proxy `http://registry:8080`; Java UC backend vẫn ở `http://catalog:8080`. Proxy forward API và serialize metadata writes cho catalogs/schemas/tables/volumes/functions. Với các API này, UC mutation được áp dụng rồi registry phải sync thành công trước khi client nhận response thành công.

Nếu UC đổi thành công nhưng R2 ghi lỗi, client nhận 503 với thông báo thay đổi có thể đã áp dụng. Không retry mù; kiểm UC/status trước. Local pending marker được giữ để reconcile lại. Khi pending, metadata writes tiếp theo bị chặn; đọc vẫn được forward.

Reconcile định kỳ quét toàn bộ catalog/schema/table/volume/function với pagination, đọc cả namespace rỗng. Nó cũng bắt thay đổi bypass proxy/đường API khác, nhưng chỉ sau khoảng thời gian poll và lần scan thành công. Không hứa durable ngay khi nhận response từ một client gọi trực tiếp backend. Thay đổi chỉ tồn tại trong khoảng chưa sync có thể mất khi xóa host đột ngột. Dùng Sync trước reset và cho các client đi qua UC_URL của project.

Mỗi lần sync kiểm registry ETag; chỉ PUT khi định nghĩa thay đổi. Conditional PUT IfMatch/IfNoneMatch ngăn writer cũ ghi đè object mới. Registry bị sửa/xóa ngoài service gây conflict, không tự coi đó là registry trống để ghi lại. Một manifest duy nhất tránh đọc lẫn các collection từ nhiều phiên xuất; đây không là transaction phân tán giữa UC và R2. Không có lịch sử rollback registry nhiều phiên trong tính năng này.

## Kiểm tra và sync trước khi reset

Trong UI: **Compute → Catalog registry on R2 → Refresh registry status / Sync registry now**. Kiểm Synchronized, counts, thời điểm sync và danh sách unrestored. Nonportable inventory được cảnh báo cả trước khi reset; đồng bộ thành công không có nghĩa các managed asset sẽ được tự phục hồi.

Trong terminal Ubuntu tại repo source:

```bash
docker compose exec -T registry python3 /opt/lakehouse/registry_service.py status
docker compose exec -T registry python3 /opt/lakehouse/registry_service.py sync
docker compose logs --tail=100 registry
```

Nếu mới nâng cấp, rebuild/start trước, kiểm registry sync và object current.json trên R2 trước khi xóa local state. Cùng bucket/prefix và credential hợp lệ phải được giữ khi dựng host mới. Reset metadata local sẽ kích hoạt replay từ registry; không là yêu cầu xóa trắng catalog bền vững.

Bootstrap vẫn tạo DEFAULT_CATALOG/default schema/incoming/sample thiếu sau replay. Nó không phục hồi workflow, notebook hoặc run history đã xóa; starter dbt không tự publish/chạy.

## Xung đột và phục hồi database backup

- Local UC khác registry khi không có lineage: dừng writer, xác định nguồn đúng. Muốn giữ UC local: chọn UC_REGISTRY_PREFIX mới chưa có registry rồi recreate service. Không tự xóa registry cũ để bỏ qua conflict.
- Muốn dùng registry R2: dùng UC local mới/trống có chủ đích, giữ R2/prefix; không merge đè state không liên quan.
- Muốn restore database UC đầy đủ từ snapshot: đặt UC_REGISTRY_ENABLED=false trong env trước restore để tắt replay/export, đồng thời dừng registry khi restore (script đã làm). Sau khi nghiệm thu DB, chọn prefix mới để xuất state đã restore rồi bật registry và recreate. Không để snapshot UC cũ ghi đè registry mới hơn theo suy đoán.
- R2 Unauthorized/timeout: sửa key/endpoint/network, không reset database để chữa lỗi này. Poll sẽ thử sync lại sau khi lỗi được xử lý; ETag conflict cần quyết định của người vận hành.
- Registry hỏng JSON/version/bucket/path: startup từ chối, không ghi đè registry. Kiểm nguồn và khôi phục định nghĩa đúng bằng quy trình quản trị riêng.

Không đưa PostgreSQL data directory lên R2/rclone mount. Không copy file `.db` đang chạy. Các thao tác của registry là UC metadata REST và một JSON object trên R2.

## Functions và xóa bảng

Catalog UI quản lý function theo [FUNCTIONS](FUNCTIONS.md). Function definition được sync/replay, không là managed compute hoặc MCP hosting. Xóa function/table được đồng bộ để không phục hồi metadata đã xóa sau một lần sync thành công. Delete table trên UI đi qua Spark DROP TABLE; external data không tự xóa khỏi R2, managed data có thể bị xóa theo engine. Không dùng UC metadata DELETE để giả thực hiện DROP có quản lý dữ liệu.

Notebook/SQL editor/workflow SQL tạo SQL scalar function bằng DDL qua cùng registry. SELECT đọc definition và biên dịch vào session Spark; startup replay vẫn chỉ phục hồi metadata. `OR REPLACE` dùng compare-and-replace có `function_replacement` intent trong state local trước delete/create. Sync phải reconcile intent trước export; nếu không khôi phục được definition đang thiếu hoặc có conflict, giữ snapshot R2 cuối và chặn metadata writes. Không xóa state/intent khi đang pending; kiểm UC definition, registry logs và kết nối rồi Sync lại. UC delete/create không atomic và không bảo toàn ID/grants/ownership.

## Kiểm thử

Unit/contract ở runtime/tests/test_catalog_registry.py và test_registry_service.py kiểm empty namespace, properties/root/comment, pagination, replay/resume/conflict, conditional writes, failed sync và managed inventory guard. Kiểm R2 thật/UC thật trên deployment theo [VALIDATION](VALIDATION.md) và [ACCEPTANCE](ACCEPTANCE.md); mock store không thay credential/provider integration.

Nguồn API: [UC 0.7.0 definitions](https://raw.githubusercontent.com/unitycatalog/unitycatalog/v0.7.0/api/all.yaml), [Volumes](https://unitycatalog.io/docs/how-to/manage-volumes/), [Managed storage](https://unitycatalog.io/docs/how-to/managed-storage-s3/), [R2 conditional operations](https://developers.cloudflare.com/r2/api/s3/conditional-operations/).
