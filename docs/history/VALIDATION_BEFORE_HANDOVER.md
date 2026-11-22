# Bản lưu trước khi tổ chức tài liệu bàn giao

Bằng chứng và ghi chép lịch sử, không phải hướng dẫn triển khai hiện tại. Các câu “hiện tại” bên dưới là trạng thái ở thời điểm ghi cũ. Xem [Validation hiện tại](../VALIDATION.md).

# Kiểm chứng bản cleanup V3.1.1

## Bổ sung V3.1.3 — 22/11/2026

Hotfix quyền image: đã tái hiện PermissionError bằng module root-owned mode 600 trên image cũ. Regression build dùng Python/template mode 600 và directory mode 700: image mới cho phép analyst import backend, đọc frontend/template và tạo starter; code vẫn không writable. Catalog startup mode 600 trong context được chuẩn hóa thành 0755 và đọc/chạy được bằng user unitycatalog. Cả hai image test đều PASS; không truy cập R2/volume dữ liệu.

- Build image/runtime và extension 3.1.3 thành công. Compose config, Bash syntax, PowerShell parser đạt.
- **87 kiểm thử Python PASS**: bao gồm xác nhận/path traversal, vùng storage được bảo vệ, xóa folder hơn 2000 object theo batch, lỗi từng object, upload đang diễn ra; bootstrap chạy lại không ghi đè dữ liệu/project/flow; reset chỉ chọn volume metadata thuộc đúng project.
- Project dbt mẫu parse thành công bằng dbt-core 1.12.7/dbt-spark 1.11.0: 1 seed, 1 model, 7 data tests. Sinh dbt Docs offline thành công bằng empty catalog; đây chưa phải kết quả chạy 7 test trên Spark.
- Kiểm tra trình duyệt với frontend build thật và API/storage fixture: cancel xóa, xác nhận file, nhập sai/đúng đường dẫn folder, xóa cây con, bảo vệ warehouse/root incoming và Open Docs ở tab mới đều đạt. Trang Docs tải index/manifest và render project lakehouse_sample.
- Kiểm thử end-to-end với R2 thật chưa hoàn tất: credential trong các `.env` local hiện trả Unauthorized ở ListObjectsV2. Không reset volume dữ liệu thật; kiểm thử dùng một Compose project/workspace riêng. Cần credential hợp lệ để xác nhận toàn bộ flow seed/build/test/docs trên Spark/R2.

Hướng dẫn sử dụng và cập nhật: [REBUILD_DBT.md](../REBUILD_DBT.md).

Ngày: 22/11/2026. Máy thực hiện là Windows 11 + Docker Desktop Linux containers. Ubuntu 22.04 là nền tảng triển khai đích; chưa cài lại trực tiếp host Ubuntu của người dùng trong đợt này.

## Phạm vi cleanup

- Dọn 4 notebook mẫu trong workspace/examples cùng checkpoint của ví dụ cũ.
- Dọn định nghĩa JSON/YAML của 7 workflow demo/test cũ: control_demo, daily_demo, daily_lakehouse, v3_integration_check, v3_ui_check, v31_control_check, v31_native_check.
- Giữ **variable_if_foreach_demo**, hai notebook cá nhân và toàn bộ project dbt hiện có. Không tự commit Git.
- Dọn proxy PID cũ và bytecode sinh tự động trong source. Hub tùy chọn ghi PID vào hub_state.
- Bản sao file trước cleanup từng được lưu tại `work/cleanup-20261122`, có kiểm tra hash. Bản tạm này đã được dọn trong đợt tách source/data tiếp theo theo yêu cầu người dùng; không còn là điểm rollback.
- Kiểm tra Kestra: 7 định nghĩa cũ đã không còn được publish trước đợt này; giữ nguyên source flow mẫu mới. 18 execution lịch sử được giữ nguyên qua kiểm tra cleanup. Flow quản trị retention thuộc namespace khác được giữ.
- `.env`, Docker data volumes, bảng UC/R2 và Git history được bảo toàn. Run artifact và execution history tiếp tục chịu retention vận hành.

## Tài liệu và helper

- Tài liệu tập trung trong docs: tính năng/giới hạn, Windows/Ubuntu, .env, sử dụng, workflow, vận hành/backup, migration, multiuser, client ngoài và troubleshooting.
- Windows có init.ps1/start.ps1 tương thích PowerShell 5.1. Kiểm tra parser, tạo .env mới và chạy init lần hai giữ nguyên hash của .env đã qua. Nội dung script ASCII; .env sinh ra UTF-8 không BOM, credential được tạo ngẫu nhiên.
- Đường dẫn notebook trong UI để người dùng nhập; helper check-notebook.sh nhận path làm tham số, không trỏ vào notebook mẫu đã xóa.
- Dùng cùng source cho Windows/Ubuntu. Bản phát hành trước từng giữ dbt baseline và workflow mẫu; repo source hiện tại đã loại toàn bộ workspace. Code cá nhân và Git cũ nằm trong thư mục dữ liệu riêng.

## Kết quả kiểm tra

- **48 kiểm thử Python PASS** trên image/runtime hiện tại; warning deprecation của dependency không làm thất bại kiểm thử.
- **Windows PowerShell 5.1:** init.ps1 tạo credential ngẫu nhiên, UTF-8 không BOM; lần init thứ hai giữ nguyên hash `.env`. start.ps1 -SkipBuild chạy qua kiểm tra engine/config, khởi động và đợi stack thành công trên máy dev.
- **Shell/config:** PowerShell parser, Bash syntax và `docker compose config --quiet` đã qua. Frontend trong container có version 3.1.1; đường dẫn notebook không còn gán sẵn file mẫu đã xóa.
- **Workflow giữ lại:** execution `5dEFQyjRL3EkFbRUvMektY` SUCCESS; ba lượt cho `[1,10,3,30]`, `[2,20,3,60]`, `[3,30,3,90]`. Definition file giữ nguyên hash, SQL trả timezone Asia/Ho_Chi_Minh. Run kiểm chứng tạo thêm một execution bình thường sau khi cleanup đã bảo toàn lịch sử trước đó.
- **Tài liệu/package trước tách source:** đã kiểm tra link, manifest và quét credential. Bản sao phát hành Ubuntu trước đây đã được bỏ sau khi đối chiếu manifest; dùng một source repository chung, không mang theo bất kỳ workspace nào.

Bằng chứng các tính năng trước cleanup nằm ở [history/VALIDATION_3_1.md](VALIDATION_3_1.md); các notebook/sample cũ nhắc trong tài liệu lịch sử đã được dọn khỏi workspace.

## Tách source và dữ liệu để đưa lên Git

Đợt tiếp theo cùng ngày 22/11/2026:

- Chuyển nguyên workspace sang `../r2-lakehouse-data/workspace`; so SHA-256 của toàn bộ **67 file** trước/sau di chuyển, giữ nguyên Git HEAD và trạng thái các file chưa commit. Không sửa remote của repo workspace.
- Thêm WORKSPACE_DIR vào Compose mặc định/restore và init Windows/Bash. Đường dẫn container vẫn `/workspace`; project name, named volumes và R2 table không thay đổi.
- Recreate stack thành công: 6 dịch vụ running, các healthcheck được khai báo đều đạt. Kestra không khai báo healthcheck; được kiểm chứng thêm bằng execution thật của workflow giữ lại, SUCCESS với kết quả **30/60/90**. SQL trả đúng timezone cấu hình.
- Chạy lại **48 kiểm thử Python, tất cả PASS**.
- Init Git mới ở gốc source, nhánh main, stage **93 file**; không commit, không gắn remote, không push. Kiểm tra staged tree không chứa workspace, notebook, `.env`, backup, database hay private key; đối chiếu nội dung với credential riêng đang dùng không tìm thấy giá trị secret.
- Xuất chính staged tree ra thư mục tạm, kiểm tra init mới/lặp lại trên Windows PowerShell 5.1 và Bash trong Linux container; `.env` giữ nguyên khi init lần hai. Workspace mới không có notebook/dbt/workflow cá nhân, không tự tạo backups. Kiểm tra đường dẫn workspace có khoảng trắng, Compose mặc định/Hub/restore, Bash syntax và link tài liệu nội bộ đều qua. Thư mục kiểm thử đã được dọn.
- So manifest SHA-256 trước khi bỏ bản source phát hành Ubuntu trùng; nay dùng một source chung. Dọn thư mục backup rỗng và snapshot cục bộ `20261117T115201Z` sau khi tải/so SHA-256 đủ 4 object tương ứng trên R2. Giữ bản R2; không xóa database/volume. Dọn bản tạm cleanup và fixture restore/restart cũ, không được dịch vụ đang chạy sử dụng.

Kiểm chứng này không thay thế cài mới toàn bộ stack trên host Ubuntu thật; phần Linux mới kiểm tra init/config trong container. Git source không thay thế backup metadata UC: dùng quy trình [MIGRATION.md](../MIGRATION.md) để kế thừa dữ liệu khi chuyển host.

## Những gì chưa được kiểm chứng trong đợt này

- Cài mới Docker/OS trên Ubuntu thật, upload 300 GB hoặc chạy tải lớn.
- License/driver và kết nối Power BI/ADF trên môi trường thực tế của bạn.
- Cô lập quyền dữ liệu từng user; UC authorization vẫn tắt, xem [FEATURES.md](../FEATURES.md).
- Round trip backup lên R2 mới trong đợt cleanup; các kiểm thử archive offline và lịch sử thử restore trước đây được ghi ở tài liệu lịch sử.
