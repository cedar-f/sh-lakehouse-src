# Trạng thái kiểm chứng

Baseline ứng dụng: **V3.1.3 + hotfix quyền image e842c7a**. Bảng này tách kết quả được ghi nhận ở phiên bản hiện tại với kết quả lịch sử. Tài liệu mới không tự nâng trạng thái thành đã nghiệm thu trên Ubuntu thật.

## Đã kiểm tra cho baseline này

| Phạm vi | Phương pháp / kết quả | Giới hạn |
|---|---|---|
| Unit/contract tests | 87 pytest PASS, Docker Linux trên máy dev Windows | Fake storage/API, không là R2 integration |
| Build/frontend | Image runtime/catalog và extension 3.1.3 build được | Dependency inputs chưa lock toàn bộ; xem VERSIONS |
| Shell/config | Compose config, Bash syntax, PowerShell parser đạt | Không thay thế chạy OS installer thật |
| Quyền image | Tái hiện lỗi root-only 600 trên image cũ; build context 600/700 của image sửa đọc được bằng analyst/UC user | Không dùng R2/production volumes |
| Bootstrap idempotent | Empty/existing prefix, race marker, không overwrite project/flow, sample opt-out qua unit tests | R2 live chưa hoàn tất |
| Delete | Unit: path boundary, confirmation, >2000 object batches, partial errors, active multipart. Browser: cancel/file/folder/path confirmation/protected roots PASS | Browser kiểm tra bằng API/storage fixture |
| dbt sample | dbt 1.12.7 + spark adapter 1.11.0 parse 1 seed/1 model/7 tests; offline Docs generate được | 7 test mới **chưa được xác nhận đã chạy trên Spark/R2** |
| Open Docs | Browser tải site/index/manifest và render lakehouse_sample | Dùng offline empty catalog, không có live catalog introspection |
| Reset helper | Test selection đúng 4 owned volumes; refuse external/unowned volumes | Không reset data volumes thật trong test |

Lệnh tái hiện unit/image tests ở [DEVELOPMENT.md](DEVELOPMENT.md). Unit output baseline: `87 passed`. Image regression output: analyst import/read/template generation PASS; catalog non-root startup readable/executable PASS. Đây là kết quả ghi nhận, không phải job CI tự chạy.

## Kiểm tra bộ tài liệu bàn giao

Đã kiểm tra 30 file Markdown: 201 liên kết file nội bộ, code fence/table columns, bao phủ 36 biến của .env.example và toàn bộ module Python cấp đầu trong runtime ở source map. Parser đạt cho 44 block Bash, 9 PowerShell, 2 Python, 10 JSON và 1 YAML; các Python heredoc được kiểm cú pháp riêng. Đã kiểm Compose merge của proxy override, Jupyter proxy traits và Caddyfile qua `caddy adapt`; đã rà credential thật của env local và private-key headers trong file thay đổi, không phát hiện khớp. Đây là kiểm tra tài liệu/cấu hình tham khảo, không chạy các lệnh cài đặt, firewall, TLS hay phục hồi trên server thật.

## Chưa hoàn tất hoặc chưa chạy

- End-to-end flow **seed → build/7 tests → docs** mới trên R2: lần thử credential local trả Unauthorized ở ListObjectsV2; không được gán SUCCESS dựa vào parse/UI fixture.
- Cài máy Ubuntu 22.04 trắng, public HTTP/HTTPS/SSH/firewall và profile RAM 16 GB trên host của người dùng: cần biên bản thực tế.
- Power BI/ADF/gateway/driver thực tế; DirectQuery và Delta sink qua ODBC.
- Tải/throughput 300 GB, traffic 50 GB/tháng, upload lớn và memory/performance SLA.
- Restore drill mới cho đúng bản backup/Delta data/config deployment hiện tại; RPO/RTO chưa đo.
- Các tính năng chưa triển khai như per-user UC auth/shared cluster không phải mục có thể tick PASS bằng test hiện có; xem [DECISIONS.md](DECISIONS.md).

## Bằng chứng lịch sử

- [VALIDATION_3_1.md](history/VALIDATION_3_1.md): các lần Spark/UC/R2, restart, workflow, archive/restore và UI trước baseline này.
- [VALIDATION_BEFORE_HANDOVER.md](history/VALIDATION_BEFORE_HANDOVER.md): bản lưu chronology cleanup, source/data split và bổ sung 3.1.3 trước khi tổ chức lại docs.

Các kiểm thử tạo/đọc table và restore trước đây có giá trị làm regression reference, không chứng minh chúng đã được chạy lại sau đổi credential/host/metadata. Screenshot cũ có tên sample đã dọn; ảnh Files/Delete và dbt starter Docs mới cũng được ghi rõ là fixture/offline.

## Ghi kết quả mới

Dùng [ACCEPTANCE.md](ACCEPTANCE.md), ghi ngày/TZ, người thực hiện, commit, image IDs, phương pháp, side effects, cleanup và PASS/FAIL/NOT RUN. Đưa log đã loại secret/screenshot vào hồ sơ kiểm chứng được bảo vệ; không đưa env/private key vào Git. Không thay lỗi thực tế bằng ảnh mock hoặc chỉ một HTTP 200.
