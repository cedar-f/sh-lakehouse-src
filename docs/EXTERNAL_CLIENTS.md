# Power BI và Azure Data Factory

SQL endpoint là Spark Thrift / HiveServer2 binary, port 10000, auth NOSASL. Dùng driver ODBC hỗ trợ **Apache Spark/HiveServer2 và NoSASL**. Một số driver thương mại có license riêng; không giả định driver Databricks chỉ cần đổi hostname là dùng được.

## Power BI

Trên Windows 11 cài driver ODBC 64-bit tương thích. Tạo System DSN, host `localhost`, port `10000`, schema `default` khi dùng SSH tunnel trong [INSTALLATION.md](INSTALLATION.md); thay port/schema nếu đã cấu hình khác. Catalog mặc định của SQL endpoint theo cấu hình Spark đang áp dụng. Power BI Desktop → Get Data → ODBC → DSN → Import. Thử trước query:

```sql
SELECT current_catalog(), current_schema()
```

Sau khi publish Power BI Service, cài on-premises data gateway trên một máy Windows luôn bật, cài cùng driver/DSN. Gateway phải kết nối được Ubuntu qua LAN/VPN. Generic ODBC được hỗ trợ ở chế độ Import; DirectQuery cần driver/connector tương thích và kiểm chứng thêm, chưa mặc định được bật ở V3.

Tham khảo [ODBC generic interface của Power Query](https://learn.microsoft.com/en-us/power-query/connect-using-generic-interfaces) và [DirectQuery qua ODBC extension](https://learn.microsoft.com/en-us/power-query/odbc). Query bảng của bạn dùng tên đầy đủ catalog.schema.table.

## ADF

ADF → Linked Services → ODBC. Cần Self-hosted Integration Runtime trên Windows và driver 64-bit. SHIR không chạy trực tiếp trên Ubuntu. Dùng Windows 11 hiện có nếu chấp nhận nó phải bật trong lúc pipeline chạy. Bắt đầu bằng Lookup/Copy source chạy SELECT; ghi vào Delta bằng ODBC sink chưa được cam kết vì phụ thuộc driver và SQL được sinh ra.

Để kích hoạt workflow, ADF có thể dùng Web Activity gọi API Kestra với xác thực và đường mạng phù hợp. Không dùng activity Databricks Notebook cho notebook self-hosted này. Chỉ public endpoint qua VPN/TLS và xác thực thích hợp; V3 mặc định không public SQL.

Các kết nối Windows thực tế cần kiểm tra trên máy bạn vì project không cài hoặc cấp license driver Power BI/ADF.

Microsoft mô tả SHIR là loại IR chạy trên Windows tại [Integration runtime](https://learn.microsoft.com/en-us/azure/data-factory/concepts-integration-runtime); xem [hướng dẫn cài SHIR](https://learn.microsoft.com/en-us/azure/data-factory/create-self-hosted-integration-runtime) để chọn đúng host.
