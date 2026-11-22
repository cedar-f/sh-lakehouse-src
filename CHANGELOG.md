# Changelog

Commit tồn tại không đồng nghĩa đã push hoặc triển khai. Kiểm tra git log/image IDs trên host.

## Tài liệu bàn giao — sau e842c7a

- Bổ sung handover, kiến trúc/sequence, source map, API, versions và quyết định thiết kế.
- Đưa luồng Ubuntu/Git/SCP env/SSH/UFW/public HTTP/HTTPS cùng mẫu proxy vào repo.
- Bổ sung ngân sách tài nguyên, security/trust boundary, backup scope/DR/rollback và acceptance checklist.
- Đồng bộ Git/user guide/requirements và tách validation lịch sử.
- Thay đổi tài liệu/template tham khảo không tự bật proxy, firewall, RBAC, cron backup hoặc RAM theo service.

## Hotfix quyền image — e842c7a — 22/11/2026

- Chuẩn hóa read/traverse cho code/template/frontend, giữ root ownership/runtime user analyst.
- UC startup mode 0755; regression build với source 600/700, không dùng R2.

## V3.1.3 — a6f8ca7 — 22/11/2026

- Delete file/subfolder incoming có confirmation, bounded batch và partial error UI/API.
- Bootstrap prefix R2 idempotent, giữ nội dung cũ.
- dbt_sample + flow seed/build/docs; schedule off, không auto-run.
- Rebuild/reset metadata có flag, R2 preflight và volume ownership checks.
- 87 Python tests, UI fixture/offline Docs đã kiểm tra; sample R2 end-to-end còn chờ credential hợp lệ.

## Baseline source — dad0b78

Tách platform khỏi workspace và đưa lên Git. Chức năng baseline: notebook/SQL, UC/Delta/R2, Compute restart, Git, Runs, Kestra workflow logic/history, retention, backup/restore, optional JupyterHub. Bằng chứng cũ ở docs/history không chứng minh tự động rằng phiên bản sau đã được nghiệm thu lại toàn bộ.
