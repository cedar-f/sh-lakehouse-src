# Lich su kiem thu truoc dot don project

> Tai lieu lich su. Notebook/workflow mau cu duoc nhac den ben duoi da duoc don khoi workspace ngay 22/11/2026. Xem [kiem thu hien tai](../VALIDATION.md).

# Kiểm chứng V3

Ngày kiểm tra: 17/11/2026. Môi trường kiểm tra: Docker Linux containers trên máy dev Windows 11, dùng bucket Cloudflare R2 thật. Ubuntu 22.04 là nền tảng triển khai đích; chưa truy cập server Ubuntu của người dùng trong phiên này.

Ngày 21/11/2026 kiểm tra lại: Docker vẫn dùng dữ liệu tại D qua junction; sáu dịch vụ V3 đang chạy, các dịch vụ có healthcheck đều healthy. Các kết quả end-to-end bên dưới là các lần chạy ngày 17/11.

### V3.1 — 21/11/2026

- Ví dụ mới `variable_if_foreach_demo`: task Variables gán `vars.enabled`, `vars.numbers`, `vars.factor`; If kiểm tra vars; For each đọc `vars.numbers`; Variables trong từng iteration tính kết quả để SQL dùng lại. Đã chạy 4 execution SUCCESS: mặc định `M4A7sd6UXXERQGQXKZ8L0` cho 30/60/90; enabled=false `7ikcbC8Qej5Uaskal4QRQC` vào Else; numbers=[] `3nss1rY3VYAFqBYLUwYgEM` vào Else; numbers=[4,7], factor=5 `1ysTRhpIavPK6x2Q2pXhfb` cho 20/35. Các định nghĩa workflow khác không đổi; flow mẫu không bật lịch.

- 48 kiểm thử Python: giữ kiểm tra restart/readiness; thêm timezone UTC+07, filter/paging, log cursor không mất/trùng event, redaction/traversal, typed output, Failure/Always, biến, loop, cycle/expression, retention bảo vệ run đang chạy, notebook thật thành công/thất bại, giới hạn process/artifact, backup/restore archive và không dọn nhầm temp của container khác, phục hồi trạng thái INTERRUPTED sau restart.
- Chuyển 23 run cũ sang volume, so hash trước khi bỏ bản cũ. `SHOW TABLES IN spark_catalog.default` rỗng; metastore/warehouse local được lưu chuyển. Không đổi dữ liệu UC/R2 hoặc metadata PostgreSQL.
- Notebook `462c2b1546cb435da07010efe78e2536` SUCCESS; hai cell có trạng thái/thời gian, stdout, bảng HTML và output JSON `[2,3]`.
- dbt docs `422717a566ba4fe48d94cd1e5392b465` SUCCESS; index.html, manifest.json và catalog.json phục vụ qua route có xác thực. dbt build riêng `635aabc087624e28a3c2cce7b49228ea` SUCCESS; model status, SQL compile và structured log. Bảng thử riêng đã được DROP; không sửa model người dùng.
- Kestra advanced execution `3d2forn8DBdXqoAHwrI4hE` SUCCESS: input JSON, notebook output, If, 2 iteration, biến, SQL 20/30, SQL cố ý lỗi, handler và Always. Task lỗi giữ FAILED dù handler đã xử lý để flow thành công. Nhánh Else không chạy.
- Flow mẫu `control_demo` chạy Then/Else thành công trên image cuối: `6jACtAtEbtq6igE3MZRR0U` và `54FKZTPSYGmvF63cksS05R`; 7 flow được publish lại, định nghĩa/schedule không đổi.
- Native DAG `1PHdZ0uD8pZTMn8ud7SGog` SUCCESS; hai SQL run được liên kết vào history. Filter theo name/type/status và cleanup preview hoạt động.
- Kestra validate chấp nhận controller, JSON inputs và flow PurgeExecutions. YAML lưu timezone explicit Asia/Ho_Chi_Minh; JVM/container nhận cùng TZ. Không kích hoạt purge thủ công trên dữ liệu người dùng.
- Kiểm tra UI qua trình duyệt: bảng Runs/Workflow Run History, bộ lọc, cell, từng iteration và run con. Ảnh mới: runs-history.jpg, workflow-history.jpg, dbt-docs.jpg.
- Môi trường kiểm tra vẫn là Windows 11 + Docker Linux; chưa kiểm tra trực tiếp Ubuntu của người dùng. Backup/restore archive có kiểm thử round trip offline với bản mới và manifest cũ 4 file; S3 được thay bằng fake trong bộ nhớ. Không upload backup mới lên R2 trong lần này.

### Sửa lỗi workflow 3.0.4 — 21/11/2026

- Các lần chạy dbt cũ đọc nhầm model/seed trong `.ipynb_checkpoints`. Các lần mới nhất không kết nối được cổng SQL 10000: sau khi cả bộ dịch vụ bật lại, SQL đã thoát vì Unity Catalog chưa sẵn sàng.
- SQL chờ lỗi kết nối/HTTP tạm thời từ UC trong lúc khởi động; lỗi cấu hình hoặc xác thực không bị retry vô hạn. Runner chờ SQL trước khi chạy dbt/SQL, tính thời gian chờ trong timeout của task và trả lỗi rõ khi dịch vụ thất bại.
- Runner bổ sung `.dbtignore` cho checkpoint, giữ quy tắc người dùng và file recovery. `dbt ls` với project thật chỉ còn 1 model, 1 seed và 2 test; không còn resource `*-checkpoint`.
- 27 kiểm tra Python đã qua, gồm phục hồi sau lỗi UC tạm thời, giới hạn thời gian chờ, báo lỗi SQL, giữ quy tắc ignore cũ và che secret trong lỗi CLI trả cho Kestra.
- Phát hiện Kestra chạm giới hạn container 1 GiB, liên tục reclaim bộ nhớ và API timeout. Đổi mặc định sang giới hạn 4 GiB, heap Java 2 GiB, JVM thấy 2 CPU; cấu hình được qua `.env`. SQL/runner/Kestra được cập nhật, notebook không recreate.
- Chạy lại flow người dùng `daily_lakehouse` qua Kestra sau sửa: execution `7RE9bDNwjOZsHebcevvSWF` SUCCESS; cả `dbt_1` và `notebook_2` SUCCESS. dbt có PASS=4, ERROR=0; notebook output có 4 code cell đã thực thi, không có output lỗi. API Refresh executions cũng trả về lần chạy SUCCESS này. Các execution FAILED trước đó được giữ nguyên.

### Save & Restart Spark và tên tab 3.0.3 — 21/11/2026

- Compute có lựa chọn SQL/dbt, notebook được đánh dấu, hoặc cả hai. Nút Save & Restart Spark kiểm tra/lưu cấu hình rồi theo dõi đến READY/FAILED. Có chặn thao tác trùng khi đang restart.
- 19 kiểm tra Python đã qua: kiểm tra cấu hình trước khi lưu, xác thực runner, chống save trùng, bỏ qua trạng thái READY của request cũ, lỗi/timeout khởi động, thay đúng tiến trình SQL và chỉ restart kernel được chọn.
- Kiểm thử trình duyệt với SQL, runner và Jupyter riêng trên Docker, dùng workspace kiểm thử riêng: SQL-only áp dụng Delta nhưng giữ nguyên PID và biến RAM của notebook; both thay PID cả SQL và kernel được chọn; notebooks-only giữ PID SQL.
- Cố ý đặt giá trị Spark không hợp lệ: giao diện báo FAILED, không báo READY giả. Sửa cấu hình và bấm Save & Restart Spark lần nữa phục hồi SQL thành công. dbt debug kết nối thành công sau phục hồi.
- Trong các lần bấm Save, thời điểm khởi động container SQL/Jupyter không đổi; chỉ các tiến trình Spark cần áp dụng được thay. Không tạo/sửa bảng R2 trong kiểm thử này. Các container kiểm thử đã được dọn.
- Cả 9 tab có tên Catalog, Files, Compute… không còn tiền tố Lakehouse; vẫn chung một dải tab và tự được chọn khi mở. Không có JavaScript page error.
- Đã triển khai image 3.0.3 trên bộ V3 đang chạy: SQL/runner/notebook healthy; kiểm tra giao diện sau triển khai xác nhận tên tab, đóng/mở lại Compute, nút Save & Restart Spark và cấu hình Delta đã lưu đều đúng. Việc nâng cấp backend ban đầu cần recreate notebook một lần; các lần Save & Restart sau đó không recreate Jupyter/container.
- Script `tests/ui_compute_restart.py` yêu cầu cấu hình URL/container/workspace kiểm thử riêng, tuyệt đối không chạy trên workspace đang làm việc vì script chủ động thử cấu hình lỗi và restart Spark. Ảnh: `compute-restart.png`.

### Điều hướng tab 3.0.2 — 21/11/2026

- Các panel Lakehouse mới và panel mở lại sau khi đóng dùng `tab-after`, tự chuyển lên phía trước và giữ các tab khác. Notebook tạo từ SQL cũng dùng `tab-after`.
- Kiểm tra qua trình duyệt trong workspace kiểm thử riêng: mở liên tiếp cả 9 panel, xác nhận cùng một dải tab, mỗi lần chỉ một panel hiển thị và tab vừa mở được chọn.
- Chuyển về SQL, đóng rồi mở lại: nội dung SQL đang nhập vẫn còn, đủ 9 tab và không tạo vùng chia màn hình mới. Không có JavaScript page error.
- Cập nhật frontend trên container đang chạy, không khởi động lại notebook hoặc thay đổi metadata UC.

### Bản sửa giao diện 3.0.1 — 21/11/2026

- Tái hiện lỗi Catalog không mở lại được sau khi đóng. Sửa việc gắn lại widget đã bị JupyterLab gỡ khỏi layout, giữ nguyên dữ liệu đang nhập.
- Kiểm tra qua trình duyệt: cả 9 tab mở lại được sau hai lần đóng/mở liên tiếp, không reload; nội dung SQL đang soạn được giữ lại.
- Files dùng cây thư mục từ gốc bucket, mở/thu gọn, tải nội dung theo nhánh, hỗ trợ bàn phím và giữ trạng thái khi đóng/mở tab.
- Kiểm tra với file thử trên R2 thật: thư mục lồng nhiều cấp, thư mục trống và upload vào thư mục đang chọn. Đọc lại object xác nhận nội dung chính xác; đã dọn file thử sau khi kiểm tra.
- Phân trang và Retry được kiểm tra bằng response định trước cho một thư mục chỉ tồn tại trong trình duyệt kiểm thử; không tạo hàng trăm object trên R2 để kiểm tra UI.
- Không thay đổi cấu hình hoặc cơ chế lưu metadata của Unity Catalog. Ảnh giao diện: `files-tree.png`. Regression script: `tests/ui_tabs_files.py` (cần `tests/requirements-ui.txt` và Playwright Chromium).

## Đã qua

- Build image runtime và custom Unity Catalog image; build extension JupyterLab bằng webpack.
- Native extension được JupyterLab nhận là enabled/OK. Browser headless mở panel Catalog, không có iframe, không có JavaScript page error. Đã sửa lỗi chờ layout làm JupyterLab treo Loading và lỗi layout/encoding phát hiện qua ảnh chụp thật.
- PostgreSQL + UC khởi động healthy; bootstrap tạo catalog/schema/volume.
- Spark Thrift endpoint chạy SELECT; đã sửa classpath Delta/UC của Thrift worker.
- `CREATE TABLE ... USING DELTA AS SELECT` không có LOCATION tạo **MANAGED table thật trong UC**, file ở R2; SELECT trả dữ liệu đúng. Table kiểm tra: `lakehouse.default.v3_check_4ff2a11f`.
- Credential tạm R2 ký theo cơ chế Cloudflare: đọc prefix cho phép thành công; đọc ngoài prefix bị 403; ghi bằng credential read-only bị 403. Đã xóa file thử.
- Upload multipart qua Jupyter API, liệt kê phần đã gửi để tiếp tục, complete và đọc từ R2 so sánh đúng từng byte. Bài kiểm tra 6 MiB + 3 byte; chưa thử file hàng trăm GB. Đã xóa file thử.
- dbt Core 1.12.7 + dbt-spark 1.11.0: `debug`, `seed`, `build` thành công; 1 seed, 1 model Delta và 2 data tests (not-null/unique), PASS=4.
- Tạo catalog/schema mới trong UC, tạo và SELECT managed table bằng tên ba phần thành công; dbt seed vào catalog/schema mới thành công. Đã sửa cách truyền SQLConf qua Thrift và tự bảo đảm namespace `default` cho metadata của dbt.
- Visual workflow được biên dịch, publish qua API Kestra và chạy hai SQL tasks có dependency tới trạng thái SUCCESS; cron + timezone được lưu với lịch disabled. Đã sửa schema timeout/retry theo image Kestra được pin bằng digest trong compose.
- Đã kiểm tra trực tiếp qua trình duyệt: kéo node, sửa dependency/retry, Save & publish và Execute tới SUCCESS; không có JavaScript page error. Ảnh thật: `workflow-ui.png`.
- Notebook `03_workflow.ipynb` chạy qua runner tới SUCCESS; truyền tham số, tự khởi tạo Spark và SQL cell; file output chứa kết quả HTML và tham số đúng.
- Backup UC/Kestra/workspace lên R2; tải xuống và xác nhận 4 SHA-256. Khôi phục vào PostgreSQL mới, khởi động UC mới và dùng Spark riêng SELECT managed table cũ trên R2 thành công. Đây là mô phỏng chuyển host bằng các container tách biệt, không phải thao tác trên server Ubuntu thật của người dùng.
- JupyterHub/PAM: tạo tài khoản riêng, đăng nhập và spawn server riêng, mở native panels, chạy SQL grid thành công. Xóa/tạo lại container với home/state volumes giữ nguyên, đăng nhập lại bằng cùng tài khoản và truy vấn SQL thành công. Không có JavaScript page error.
- Đã build lại Dockerfile cuối, gồm proxy JupyterHub và phiên bản package đã khóa.
- 6 unit tests về DAG, dependency thiếu, cycle, cron, dbt command allowlist và đường dẫn notebook thoát workspace đã qua.
- Python syntax và JavaScript syntax được kiểm tra trên source.

## Chưa hoàn tất kiểm tra

- Kết nối thực tế Power BI/ADF và GitHub private cần driver/tài khoản của người dùng; chưa kiểm tra end-to-end.
- Chưa thử upload hàng trăm GB, workload 300 GB, độ trễ mạng dài hoặc nhiều người cùng xử lý dữ liệu nặng. Phép thử multipart hiện dùng file nhỏ để kiểm chứng cơ chế.
- Chưa chạy cài đặt trên server Ubuntu đích. `scripts/start.sh` kiểm tra dung lượng tối thiểu trước khi build; cú pháp các shell scripts đã được kiểm tra.

## Khắc phục dung lượng máy dev

Với sự cho phép của người dùng, đã chuyển cả data disk và engine disk Docker từ `C:\Users\dotun\AppData\Local\Docker\wsl` sang `D:\DockerData\wsl` khi Docker/WSL dừng. Đường dẫn cũ là junction trỏ sang D, giữ nguyên đường dẫn Docker và WSL đã đăng ký. Image và các volume V2/V3 được nhận lại sau khởi động; ổ C có lại khoảng 48 GB trống. Các phép thử bị gián đoạn trước đó đã được chạy lại sau khi chuyển.

## Giới hạn có chủ đích

Mặc định dùng một workspace tin cậy. UC authorization chưa bật; các user Hub dùng chung quyền dữ liệu. R2 credential được giới hạn theo location **không tự biến thành** quyền table theo từng user. Panel Permissions ghi rõ trạng thái này. Row/column security và cơ chế chống người dùng có thể chạy Python truy cập storage trực tiếp chưa được triển khai.

Power BI/ADF là đường kết nối tùy chọn qua Spark Thrift/ODBC; cần driver tương thích và gateway/SHIR Windows. Generic Power BI ODBC dùng Import; chưa cam kết DirectQuery.

## Tài liệu đối chiếu

- UC Spark / bộ phiên bản: https://unitycatalog.io/docs/how-to/configure-spark/
- UC PostgreSQL: https://docs.unitycatalog.io/how-to/configure-backend-db
- UC credential generator extension point: https://github.com/unitycatalog/unitycatalog/blob/v0.7.0/server/src/main/java/io/unitycatalog/server/service/credential/aws/AwsCredentialVendor.java
- R2 temporary credentials / local signing: https://developers.cloudflare.com/r2/examples/authenticate-r2-temp-credentials/
- dbt Spark: https://docs.getdbt.com/docs/local/connect-data-platform/spark-setup?version=1.13
- Power BI ODBC: https://learn.microsoft.com/en-us/power-query/connectors/odbc
- ADF ODBC: https://learn.microsoft.com/en-us/azure/data-factory/connector-odbc
