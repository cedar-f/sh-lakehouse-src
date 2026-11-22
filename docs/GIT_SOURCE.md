# Đưa source dựng lakehouse lên GitHub

## Hai repository có mục đích khác nhau

Repository ở **gốc project chứa compose.yaml** lưu code dựng hệ thống: runtime, extension giao diện, catalog, scripts, tests và docs. Repository này không chứa notebook, model dbt, workflow đang làm, `.env`, SSH key, database, run log hay backup.

Repository cũ trong **workspace/.git** lưu code phân tích của bạn. Docker bind-mount thư mục host vào `/workspace` trong container, nên Windows và Linux cùng nhìn thấy một `.git`. Git gắn với thư mục source, không phải với hệ điều hành. Giữ hai repo riêng; Git panel trong Jupyter quản lý repo workspace, còn source hệ thống được commit từ terminal trên host.

Cấu trúc đã áp dụng trên máy dev:

```text
outputs/
  r2-lakehouse-v3/          Source hệ thống; .git ở đây
    compose.yaml
    .env                   Cấu hình riêng, Git bỏ qua
    .env.example           Cấu hình mẫu được commit
    runtime/ catalog/ scripts/ tests/ docs/
  r2-lakehouse-data/
    workspace/             Code hiện tại và .git cũ, giữ nguyên
```

Trong `.env` đang dùng: `WORKSPACE_DIR=../r2-lakehouse-data/workspace`. Trong container vẫn là `/workspace`. Di chuyển này không đổi tên Compose project và không xóa named volumes. Code của workspace hiện tại không được sao vào source hệ thống.

## 1. Tạo repository GitHub mới

Đăng nhập GitHub → dấu **+** → **New repository**. Đặt tên, ví dụ `lakehouse-platform`; chọn **Private** nếu muốn giới hạn người đọc. Giữ repository **trống**: không tạo README, .gitignore hoặc license ở bước này vì source local đã có file. Bấm **Create repository**, copy URL HTTPS của repo mới.

Không chọn nhầm repo notebook/dbt hiện tại. Hướng dẫn chính thức: [Adding locally hosted code to GitHub](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github).

## 2. Commit source trên máy dev

Mở PowerShell **trên Windows**, vào thư mục source chứa compose.yaml. Ví dụ nếu đặt source ở D:\lakehouse-platform:

```powershell
cd D:\lakehouse-platform
git rev-parse --show-toplevel
git status
git diff --cached --stat
git diff --cached --name-only
```

Trên máy đã được chuẩn bị trong đợt cleanup, Git ở gốc đã được init với nhánh `main`, source đã được stage; chưa commit và chưa gắn remote. Kiểm tra danh sách trước khi commit: không có `workspace/`, `.env`, `backup/`, `backups/`, notebook cá nhân hoặc database.

Nếu dùng bản source chưa có Git, chỉ khi đó chạy:

```powershell
git init -b main
git add .
```

Commit:

```powershell
git commit -m "Initial lakehouse platform source"
```

Nếu Git báo thiếu danh tính, đặt thông tin **của bạn** cho repo này rồi chạy lại commit:

```powershell
git config user.name "TEN_CUA_BAN"
git config user.email "EMAIL_GIT_CUA_BAN"
```

Có thể dùng email noreply do GitHub cung cấp. Không copy giá trị placeholder nguyên xi.

## 3. Kết nối repo mới và push

Thay `OWNER` và `REPO` bằng URL đã copy:

```powershell
git remote add origin https://github.com/OWNER/REPO.git
git remote -v
git push -u origin main
```

Nếu Git báo origin đã tồn tại, xem `git remote -v` để xác nhận trước khi dùng `git remote set-url origin URL_REPO_MOI`. Không chạy lệnh đổi remote trong workspace cũ.

Với HTTPS, Git Credential Manager trên Windows có thể mở trình duyệt để đăng nhập GitHub; hoàn tất đăng nhập/ủy quyền bằng tài khoản có quyền push. Không gõ mật khẩu đăng nhập GitHub vào ô mật khẩu Git. Nếu môi trường yêu cầu personal access token, dùng token có quyền phù hợp và không ghi vào URL/file source. Xem [GitHub: caching credentials](https://docs.github.com/en/get-started/git-basics/caching-your-github-credentials-in-git).

SSH key của user trong container nằm trong Docker volume `git_ssh`; Windows Git không tự dùng key đó. HTTPS trên host là cách độc lập với Git panel trong workspace.

Sau khi push, refresh trang repo: cần thấy compose.yaml, runtime, catalog, scripts và docs; không thấy notebook/model hiện tại.

## 4. Dựng workspace mới từ repository này

Trên Ubuntu:

```bash
git clone https://github.com/OWNER/REPO.git lakehouse-platform
cd lakehouse-platform
bash scripts/init.sh
nano .env
```

Điền R2 và tài nguyên; nếu muốn để dữ liệu ngoài source, đặt `WORKSPACE_DIR=../lakehouse-data/workspace`, lưu `.env`, rồi chạy init lần nữa để tạo đúng thư mục:

```bash
bash scripts/init.sh
bash scripts/start.sh
```

Windows dùng `scripts/init.ps1` và `scripts/start.ps1` theo [INSTALLATION.md](INSTALLATION.md). Mặc định `WORKSPACE_DIR=./workspace`; thư mục này vẫn được Git bỏ qua. Clone source không mang theo notebook/dbt/workflow cá nhân; workspace mới bắt đầu trống và chỉ sinh cấu hình nội bộ cần thiết khi chạy. Tạo project dbt theo [USER_GUIDE.md](USER_GUIDE.md).

Clone source cũng không mang theo metadata Unity Catalog: cần [backup/restore](MIGRATION.md) nếu muốn kế thừa table/catalog và lịch sử cũ. Dùng cùng R2 bucket không tự khôi phục PostgreSQL metadata. Khi migrate, dừng host cũ theo quy trình tài liệu.

## 5. Các lần cập nhật sau

```powershell
git status
git add .
git diff --cached --stat
git commit -m "Describe platform changes"
git push
```

Không dùng `git add -f .env` hoặc `git add -f workspace`. `.gitignore` không gỡ file đã track trước đó; kiểm tra staged file trước mỗi commit. Backup dữ liệu vận hành và Git source là hai phần cần lưu riêng.
