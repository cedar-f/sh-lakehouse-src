# Files: đường dẫn và metadata R2

**Files** duyệt bucket theo cây lazy-load, phân trang từng nhánh. File/folder và root có **Copy path** để sao chép `s3a://<bucket>/<key>` dùng trực tiếp với Spark. Đây là địa chỉ storage, không là URL download và không kèm credential. `s3://` cũng được project ánh xạ tới S3A. Thao tác copy không mở/đóng nhánh; trình duyệt HTTP có fallback copy hoặc hộp thoại copy thủ công khi Clipboard API không dùng được.

**Details** mở thông tin đối tượng tại vùng chính: bucket/key, Spark/S3 path, ID, ngày giờ, size, content type, ETag, storage class, version ID và custom metadata nếu provider trả về. File CSV/JSON/Parquet có nút copy ví dụ `spark.read` và preview giới hạn 20 dòng; chọn schema/format options phù hợp dữ liệu của bạn. File có thể download bằng presigned URL ngắn hạn. Không đưa presigned URL vào Git hoặc dùng như storage path lâu dài.

## Ý nghĩa các trường

| Trường | Ý nghĩa |
|---|---|
| Created | R2 S3 không trả ngày tạo gốc. Hiện `Not reported`, không dùng Last-Modified để giả ngày tạo |
| Updated | Last-Modified của phiên bản object hiện tại, hiển thị theo TZ workspace |
| Object ID | Địa chỉ `bucket/key`, ghi rõ nguồn ID; không là UUID do provider cấp, đổi key là đổi địa chỉ |
| ETag | Giá trị opaque của provider để nhận diện nội dung/phiên bản theo API; không coi là ID hay luôn là MD5 |
| Size | Bytes của object hiện tại; không là tổng dung lượng thư mục |
| Version ID | Chỉ hiển thị khi API trả về, không suy ra từ ETag |

Folder thường chỉ là prefix, không có object riêng: không có ngày tạo/cập nhật, dung lượng hay UUID độc lập. Nếu có marker object kết thúc bằng `/`, metadata thuộc **marker**, không đại diện toàn bộ nội dung folder. Root bucket cũng là virtual folder. Không suy ra ngày folder từ file con.

Danh sách dùng LIST tối đa 200 keys mỗi trang. Details mới gọi HEAD cho object được chọn; không HEAD mọi file và không quét đệ quy để tính tổng folder. Thao tác upload/delete/refresh có thể làm metadata thay đổi; bấm Details lại để đọc trạng thái mới. Quyền truy cập metadata dùng token R2 workspace; lỗi 403 không bị che thành folder rỗng.

Catalog dùng UUID và audit timestamps thật từ UC; các trường này khác metadata R2. Replay registry tạo ID/audit mới, xem [CATALOG_REGISTRY](CATALOG_REGISTRY.md). Cấu hình TZ theo [ENVIRONMENT](ENVIRONMENT.md).

Upload/delete/progress/resume và giới hạn `incoming/` theo [USER_GUIDE](USER_GUIDE.md), [REBUILD_DBT](REBUILD_DBT.md). Table Delta phải chỉnh qua Spark; không xóa file bên trong `warehouse/` bằng tay.

Tham chiếu: [R2 S3 API compatibility](https://developers.cloudflare.com/r2/api/s3/api/), [S3 HeadObject response](https://docs.aws.amazon.com/AmazonS3/latest/API/API_HeadObject.html).
