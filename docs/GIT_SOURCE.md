# Git source hệ thống và Git workspace

## Hai phạm vi độc lập

Repo source trên host chứa compose.yaml, application, scripts, tests, docs và template sample. Repo workspace chứa notebook/dbt/workflow của người dùng. Git panel Jupyter thao tác repo workspace; Git của host thao tác source platform.

Docker bind mount cùng thư mục vào `/workspace`; `.git` hiện cả trên host và trong container vì cùng bộ file, không phụ thuộc Windows/Linux. Đặt WORKSPACE_DIR=../lakehouse-data/workspace để tách dữ liệu khỏi source. Không commit env, workspace, volumes, key hay backup vào source.

## Repository workspace

Tạo repo trên GitHub trước → tab GitHub init/connect code local và commit/push đầu, hoặc clone repo có code xuống folder mới → dùng Git panel Jupyter hằng ngày. `.gitignore` được sinh tự động khi init/connect/clone. Hướng dẫn đầy đủ ở [GITHUB_WORKSPACE](GITHUB_WORKSPACE.md).

## Tạo repository source từ bộ source chưa có Git

Trên GitHub tạo repository trống. Chạy tại root source của host, sau khi kiểm tra `.gitignore` đi cùng source:

```bash
git init -b main
git add .
git diff --cached --name-only
git diff --cached --stat
git commit -m "Initial platform source"
git remote add origin git@github.com:OWNER/REPO.git
git push -u origin main
```

Thay OWNER/REPO; cấu hình Git author nếu cần. Nếu source đã có `.git`/origin, không init lại hoặc đổi remote tùy ý. Kiểm tra git rev-parse --show-toplevel, git remote -v và git status trước thao tác. SSH key của host đọc source khác key trong container notebook.

## Cập nhật source và triển khai

Máy phát triển, tại thư mục source:

```bash
git status --short
git add PATH_TO_CHANGED_FILE
git diff --cached --stat
git commit -m "Describe the resulting behavior"
git push origin main
```

Stage đúng file thay đổi, kiểm tra secret trước commit. Không dùng add -f để bỏ qua ignore. Ignore không loại file đã track. Khi dùng HTTPS, dùng cơ chế credential manager/PAT thích hợp, không nhúng token vào URL.

Trên Ubuntu đã clone:

```bash
cd ~/data/sh-lakehouse-src
git status --short
umask 022
git pull --ff-only
bash scripts/rebuild.sh
```

Lưu notebook/chờ job trước rebuild. Docs-only không cần rebuild; thay backend/frontend/entrypoint cần build và recreate để nhận code mới. Không dùng reset hard để bỏ local edits hoặc reset-metadata để update. Các file env/deployment local và workspace được giữ ngoài Git source.

Clone host mới xem [UBUNTU_DEPLOYMENT](UBUNTU_DEPLOYMENT.md). Chuyển state xem [MIGRATION](MIGRATION.md); clone source không thay restore UC metadata/data.
