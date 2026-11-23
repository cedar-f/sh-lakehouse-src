# Quy trình kiểm thử và xác minh deployment

Tài liệu định nghĩa cách kiểm tra; không là nhật ký kết quả của một host. Ghi kết quả thực tế trong hồ sơ nghiệm thu riêng theo [ACCEPTANCE](ACCEPTANCE.md), kèm commit, image IDs, thời gian, môi trường, PASS/FAIL và giới hạn.

## Các lớp kiểm tra

| Lớp | Mục tiêu | Không thay thế |
|---|---|---|
| Unit/contract | Logic workflow, history/retention, path/permission, bootstrap/reset, Git onboarding | Kết nối R2/GitHub thật |
| Build/package | Backend import, extension bundle, file mode non-root | Start/readiness trên host đích |
| Git local integration | Agent encrypted key, init/ignore/preview, clone/first push bằng repo fixture, Git native tiếp tục commit/push | Quyền GitHub/branch protection thực tế |
| UI | Mở lại tab, form/trạng thái/lỗi, preview/selection và native Git handoff | Toàn bộ side effects của provider |
| R2/Spark/dbt | Tạo/đọc table UC, upload/readback/Delete, seed/build/tests/docs | Restore, performance và an toàn multi-user |
| Vận hành | SSH/firewall/TLS, RAM/disk, restart/retention, backup/restore | SLA nếu chưa đo tải và RPO/RTO |

Lệnh và side effects của các test ở [DEVELOPMENT](DEVELOPMENT.md). Chạy storage tests trên bucket/schema/prefix thử; kiểm kế hoạch cleanup trước thao tác ghi/xóa. Unit fixtures không dùng credential hay volume production.

## Kiểm tra registry UC

Tạo catalog rỗng, schema rỗng có comment/properties/root riêng, external volume và external Delta table và Python function có input/return types/comment/body sandbox; sync và kiểm current.json. Dựng UC đích trống cùng registry, kiểm tên/comment/properties/root, volume/table location, function definition và query data đã biết. Kiểm pagination, restore bị ngắt, JSON/bucket/path lỗi, R2 403, stale ETag và UC conflict. Managed asset phải hiện unrestored, giữ inventory và không tự biến thành external. Không xóa UC thật để test khi chưa xác định dữ liệu thuộc diện thử.

## Kiểm tra Git

Kiểm cả repo mới và repo có code. Repo mới: tạo GitHub repo trống → init/connect → ignore tự động → SSH key/Unlock → Review → commit → push/upstream. Repo có code: clone vào folder mới → giữ history/upstream → ignore được bổ sung → native Git commit/push tiếp. Cần thử wrong passphrase, key có sẵn không bị ghi đè, remote khác/non-empty bị từ chối, file đổi sau preview, custom ignore được giữ và container restart yêu cầu unlock lại encrypted key.

GitHub read test không chứng minh write access. Kiểm protected branch/quyền tổ chức bằng repo thử được cấp phép. Không dùng force push để làm test đạt.

## Kiểm tra tài liệu/cấu hình

Kiểm local Markdown links/ảnh, bảng/code fences, biến env được giải thích, command phù hợp Bash/PowerShell, secret không lọt vào source. Kiểm Compose merge và proxy syntax trước apply. Cú pháp hợp lệ không chứng minh DNS/firewall/TLS/provider credential đúng.

## Tiêu chí nghiệm thu dữ liệu

SELECT 1 chưa đủ để chứng minh Delta/UC/R2. Tạo một Delta table sandbox bằng tên ba phần, đọc lại từ session khác, kiểm metadata location và aggregate đã biết. Chạy sample dbt seed → build → docs; xác nhận 7 data tests thực thi, không chỉ dbt parse. Docs là snapshot riêng; run report phải lấy đúng Run ID.

Restore drill dùng đích sạch, writer cũ dừng và snapshot đã kiểm checksum. Đọc lại dữ liệu bảng đã biết, kiểm workspace/history/config và đo thời gian restore. Snapshot metadata không tái tạo Delta object đã mất.

## Quản lý bằng chứng và kết quả

Hồ sơ mỗi deployment chứa kết quả thực tế, lỗi còn mở, ảnh/log đã loại secret và người phê duyệt ngoại lệ. Không đưa R2 key/env/private key hoặc notebook output nhạy cảm vào Git. Ghi NOT RUN khi chưa thử; việc có code/docs/test fixture không được dùng thay kết quả live integration.
