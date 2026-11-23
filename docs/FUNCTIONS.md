# Functions trong Catalog và registry R2

Functions là các định nghĩa đã đăng ký dưới namespace catalog.schema.function. UC giữ metadata trong PostgreSQL khi đang chạy; registry giữ bản portable trên R2 để phục hồi sang UC mới. Màn hình Catalog quản lý định nghĩa, không chạy code function, không tạo Spark UDF và không tự expose MCP tool.

## Tạo và xem function

1. Mở Catalog, chọn catalog và schema, bấm **+ Function**.
2. Điền tên, Language PYTHON hoặc SQL, Return type, Input parameters, Description và Function body.
3. Bấm **Register function**. Nếu registry được bật, response thành công chỉ được trả sau khi đồng bộ R2 thành công.
4. Chọn Asset type = Functions hoặc All assets. Bấm tên function để xem tham số, kiểu trả về, language, mô tả và code. Copy full name sao chép catalog.schema.function.

Ví dụ function increment, Language PYTHON, Return type INT:

```json
[{"name":"value","type":"INT"}]
```

Body là phần thân, không gồm def:

```python
return value + 1
```

UI hỗ trợ scalar INT, LONG, SHORT, BYTE, STRING, BOOLEAN, FLOAT, DOUBLE, DATE, TIMESTAMP, BINARY. SQL function dùng SQL expression thay cho Python body. Đây vẫn là đăng ký metadata; UI không kiểm chứng kết quả thực thi. Với complex type, return_params hoặc dependency metadata, dùng UC API/native function_info thay vì form đơn giản.

Không ghi credential vào body/comment/default parameter. Registry chứa source function nên cần được bảo vệ như code riêng tư. Chỉ người dùng workspace tin cậy có quyền quản lý; UC authorization hiện đang tắt, không có EXECUTE permission được enforce theo từng user trong bộ project này.

UC 0.7 không có PATCH function. Register không ghi đè tên đã có. Để sửa, có thể đăng ký tên phiên bản mới rồi chuyển client sang tên mới. Nếu cần giữ nguyên tên, chủ động xóa rồi tạo lại; hai thao tác không atomic và có khoảng thời gian function không tồn tại. Màn hình không tự delete/recreate thay người dùng.

## Xóa function

Chọn **Delete function**, nhập đúng full name rồi xác nhận. Nó xóa định nghĩa UC và đồng bộ việc xóa lên R2. Sync thành công nghĩa là lần dựng host mới sẽ không phục hồi function đã xóa. Không có thùng rác hoặc version history trong current.json.

Nếu nhận lỗi R2/pending, thay đổi UC có thể đã áp dụng. Refresh Catalog, kiểm Compute → Catalog registry on R2, sửa kết nối/credential và sync lại trước khi retry. Không xóa database để chữa lỗi đồng bộ.

## Nội dung trên R2 và phục hồi

Vị trí giữ nguyên: s3://<bucket>/<UC_REGISTRY_PREFIX>/current.json. Collection functions lưu definition UC trả về: namespace, input/return parameters và type metadata, routine body/definition/language, comment, flags và các trường definition được allowlist. ID, owner, created/updated audit fields không replay. Dependency metadata, nếu UC trả về, được giữ như definition; không tự deploy các thư viện/hệ thống bên ngoài mà code phụ thuộc.

UC 0.7 có các trường experimental mà backend có thể không persist/return, ví dụ function properties; registry không suy diễn hoặc khôi phục trường chưa được UC lưu. Chức năng này bảo đảm các trường core đã đăng ký: tên, tham số, kiểu trả về, body/language, comment và flags. Source/dependency package vẫn nên được quản lý trong Git.

Khi UC mới trống: tạo catalogs → schemas → external volumes/tables → functions trước bootstrap. Code được phục hồi dưới dạng definition, không được thực thi trong startup. Định nghĩa cùng tên nhưng khác nội dung gây conflict; không tự ghi đè. Managed table/volume vẫn có giới hạn replay riêng theo [CATALOG_REGISTRY](CATALOG_REGISTRY.md).

## Nâng cấp registry v1 lên v2

Code mới đọc được manifest v1 và v2. v1 chưa có functions được hiểu là danh sách rỗng; khi sync, UC hiện tại được quét gồm functions và manifest được ghi v2 bằng conditional PUT tại cùng key. Không đổi UC_REGISTRY_PREFIX, không reset PostgreSQL, không sửa current.json bằng tay.

Sau khi git pull và rebuild stack, kiểm registry ready/counts và chức năng xem function; Sync trước mọi thao tác xóa state local. Code cũ chỉ đọc v1 sẽ từ chối v2 để tránh ghi mất function. Nếu rollback, dừng writer và làm theo quy trình restore/registry disabled tại [DISASTER_RECOVERY](DISASTER_RECOVERY.md); không sửa version=1 thủ công. Không chạy hai thế hệ code ghi cùng registry.

## API và thực thi tương lai

Gateway có GET functions, GET function, POST functions và POST functions/delete, cùng Jupyter authentication. Native UC API vẫn dùng POST functions với wrapper function_info; gửi qua UC_URL (registry proxy), không bypass trực tiếp backend nếu cần acknowledgement R2.

Để thực thi Python catalog function cần client/runtime tương thích và dependencies của nó. Python function trong notebook/Flask không tự trở thành UC function; Spark session UDF cũng không tự được catalog hóa. Bộ runtime hiện không cài Unity Catalog AI client và không cung cấp Execute hoặc MCP endpoint. Các phần này là integration riêng trong tương lai.

Tham khảo [UC API v0.7.0](https://raw.githubusercontent.com/unitycatalog/unitycatalog/v0.7.0/api/all.yaml).
