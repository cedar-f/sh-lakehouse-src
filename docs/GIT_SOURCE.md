# Git source và Git workspace

## Hai repo, hai mục đích

Repo source ở thư mục chứa compose.yaml lưu application, scripts, tests, docs và templates. `.env`, workspace, data volumes và backups không được commit. Repo trong workspace lưu notebook/model/workflow do người dùng phát triển. Git panel Jupyter thao tác repo workspace; terminal trên host thao tác repo source.

Docker bind-mount thư mục host vào `/workspace`; cùng một `.git` có thể hiện trên Windows và trong container Linux vì cùng bộ file. Git gắn với thư mục, không gắn với hệ điều hành. Không tự biến workspace thành submodule/copy nó vào source khi push platform.

```text
lakehouse-platform/        Repo source; compose.yaml và .env riêng
lakehouse-data/workspace/  Repo/code làm việc riêng
```

Đặt WORKSPACE_DIR=../lakehouse-data/workspace để tách dữ liệu. Đường dẫn chỉ là ví dụ; thông tin triển khai được báo tại [HANDOVER.md](HANDOVER.md).

## Kiểm tra trước khi thao tác

Chạy trong root source trên host, không trong terminal notebook:

```bash
git rev-parse --show-toplevel
git branch --show-current
git remote -v
git status --short
```

Repo hiện đã có commit và origin; không dùng git init/đổi remote như bước update thường ngày. Nếu nhận source chưa có `.git`, làm quy trình tạo repo mới dưới đây. Source repo đang dùng là https://github.com/cedar-f/sh-lakehouse-src.git; xác nhận đúng tài khoản/repo trước push.

## Tạo repo mới từ source chưa có Git

Trên GitHub tạo repo trống, có thể Private, không thêm README/.gitignore/license. Theo [GitHub import local source](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github):

```bash
git init -b main
git add .
git diff --cached --name-only
git diff --cached --stat
git commit -m "Initial lakehouse platform source"
git remote add origin https://github.com/OWNER/REPO.git
git push -u origin main
```

Thay OWNER/REPO. Nếu thiếu danh tính, đặt user.name/user.email của bạn bằng git config rồi commit lại. Staged files không được có env riêng, workspace, key, dump/artifact. Ignore không gỡ file đã track; không dùng add -f để bỏ qua.

## Update từ máy dev sang Ubuntu

Ví dụ source Windows ở D:\r2-lakehouse-v3, branch main, lần sửa chỉ có docs:

```powershell
cd D:\r2-lakehouse-v3
git status
git add docs README.md CHANGELOG.md
git diff --cached --stat
git commit -m "Document platform handover"
git push origin main
```

Khi thay code hãy stage đúng file liên quan. Nếu commit đã được tạo sẵn, kiểm tra git log rồi chỉ push. HTTPS Credential Manager có thể mở browser login; không lưu token vào remote URL. Tham chiếu [GitHub credentials](https://docs.github.com/en/get-started/git-basics/caching-your-github-credentials-in-git).

Ubuntu đã clone:

```bash
cd ~/data/sh-lakehouse-src
git status --short
umask 022
git pull --ff-only
```

Nếu worktree dirty/pull không fast-forward, xử lý branch/local edits có chủ đích, không reset hard. Docs-only không cần rebuild app. Thay runtime/Dockerfile/frontend/config cần lưu công việc rồi `bash scripts/rebuild.sh`; proxy template cần cấu hình riêng mới có hiệu lực.

Clone Ubuntu mới/deploy key read-only: [UBUNTU_DEPLOYMENT.md](UBUNTU_DEPLOYMENT.md). Key host để pull source khác git_ssh của analyst; Windows Git không tự dùng key Docker.

## Workspace mới và chuyển workspace cũ

Bootstrap tạo dbt_sample/dbt_sample_pipeline nếu thiếu; repo source không có notebook/dbt cá nhân. Muốn mang code phân tích sang, clone repo workspace riêng hoặc restore snapshot. Clone source/copy env/cùng bucket không chuyển UC metadata. Dùng [MIGRATION.md](MIGRATION.md) và [DISASTER_RECOVERY.md](DISASTER_RECOVERY.md), dừng writer host cũ khi chuyển. Git không thay backup DB, artifact, secret và Delta data.
