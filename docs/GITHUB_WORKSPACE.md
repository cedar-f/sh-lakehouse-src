# GitHub workspace: thiết lập và vận hành Git

Tab GitHub thiết lập repository của notebook/model/workflow. Git panel có sẵn của Jupyter thực hiện diff, stage, commit, branch, pull và push hằng ngày. Hai giao diện dùng cùng `.git`, author config và SSH agent của user Jupyter. Repo source dựng platform được quản lý trên host theo [GIT_SOURCE](GIT_SOURCE.md).

## Chuẩn bị repository trên GitHub

Tạo repository trên GitHub trước, hoặc dùng repository có sẵn mà tài khoản của bạn được cấp quyền. Tab không tạo repository qua GitHub API; nút **Create repository on GitHub** mở https://github.com/new.

- Repo mới để nhận code local: để trống README/license/.gitignore trên GitHub, tránh có hai lịch sử commit độc lập.
- Repo có code: clone xuống thư mục mới trong workspace; không init một lịch sử mới rồi force push đè remote.
- Repo URL nhận dạng HTTPS hoặc SSH, ví dụ https://github.com/OWNER/REPO hoặc git@github.com:OWNER/REPO.git. Wizard chuẩn hóa sang SSH; không nhập token trong URL.

## SSH dùng chung với Jupyter

1. Mở tab GitHub. Nếu chưa có key, nhập passphrase rồi **Create SSH key**. Nếu key đã tồn tại, giữ nguyên và dùng **Unlock SSH key** với passphrase của key đó.
2. **Copy public key**, mở **GitHub SSH keys**, thêm public key vào tài khoản có quyền ghi repo. Private key không được hiển thị hoặc gửi lên GitHub.
3. Có thể dùng Deploy key của riêng repo; chọn Allow write access nếu cần push. Key chỉ đọc đủ cho clone/pull nhưng không push.
4. Điền repo URL và bấm **Test repository access**. Phép thử xác nhận quyền đọc; quyền ghi chỉ được xác nhận khi push thành công.

Private key single-user ở `/home/analyst/.ssh/id_ed25519`, được giữ trong Docker volume git_ssh. Agent có socket `$HOME/.ssh/lakehouse-agent.sock`; Jupyter server kế thừa SSH_AUTH_SOCK từ entrypoint nên Git panel dùng key đã mở khóa. Passphrase chỉ gửi trong request và child environment của ssh-add/ssh-keygen, không ghi vào env/config/log. Dùng HTTPS hoặc SSH tunnel khi nhập passphrase.

Sau khi container/agent khởi động lại: key không passphrase được nạp lại; key có passphrase cần Unlock một lần nữa. Không cần nhập lại cho mỗi push. Agent không chia sẻ bộ nhớ qua restart dù file key vẫn còn trong volume. Hub có agent theo user và key trong home của user, khác key analyst của single-user.

## Luồng A: đẩy code local lên repository mới

1. Lưu notebook. Mở GitHub, nhập Repository directory: `.` cho toàn workspace hoặc đường dẫn thư mục code hiện có, ví dụ `analytics`.
2. Nhập repo URL đã tạo, Git author name/email và branch, thường là main. Bấm **Initialize / connect repository**.
3. Hệ thống init Git nếu chưa có, gắn origin, lưu author/SSH config theo repo và tự tạo/bổ sung `.gitignore`. Không đổi origin sang repo khác hoặc đổi tên branch đang tồn tại.
4. Thiết lập SSH như trên. Bấm **Review files**, kiểm tra các file sẽ commit, bỏ chọn file không cần; notebook có thể chứa dữ liệu trong output.
5. Nhập message rồi **Create initial commit**. Đây là commit local; chưa push. Preview bị vô hiệu nếu file hoặc staging đã đổi, cần Review lại.
6. Ở ô Confirm destination SSH URL nhập đúng URL dạng `git@github.com:OWNER/REPO.git`, bấm **Push first commit**. Push đặt upstream để các lần sau dùng nút Push của Jupyter.
7. Bấm **Open native Git panel**, tiếp tục stage/commit/pull/push tại cùng repository.

First push từ wizard chỉ nhận remote trống, hoặc retry khi remote có đúng branch/commit vừa push. Remote có lịch sử khác bị từ chối; không force push, reset hoặc xóa dữ liệu để hòa giải tự động. Nếu push lỗi sau commit, commit local vẫn còn; sửa SSH/quyền rồi thử push lại.

## Luồng B: repository đã có code

1. Nhập repo URL, author name/email; thiết lập/mở khóa SSH.
2. Clone destination là thư mục mới hoặc trống, ví dụ `analytics`. Thư mục cha phải có sẵn trong workspace. Không clone đè vào workspace root, folder có file, hoặc vào bên trong một Git repo khác.
3. Bấm **Clone existing repository**. Wizard lấy default branch từ GitHub, giữ history/upstream, gắn SSH config và tự thêm managed `.gitignore`.
4. Review thay đổi `.gitignore` trong Git panel, commit và push như một thay đổi bình thường. Wizard không tự commit hoặc push repo đã có history.

Có thể clone thủ công trong terminal/Git panel Jupyter bằng URL SSH. Sau khi clone, chọn đúng thư mục trong tab GitHub, **Refresh status**, điền author và branch được hiển thị rồi **Initialize / connect repository** để tự áp `.gitignore` và config dùng chung. Không cần viết `.gitignore` bằng tay. Nếu đã có clone local, fetch/pull/reconcile bằng Git panel; không clone đè.

## `.gitignore` tự động

Wizard tạo hoặc cập nhật block BEGIN/END Lakehouse workspace defaults, giữ nguyên rule riêng bên ngoài block. Block loại env/private key/profile, runtime/warehouse/metastore local, notebook checkpoint, dbt target/log/packages và backup/archive/database local. `.env.example` vẫn có thể track. Nội dung chính xác nằm trong `runtime/git_integration.py`.

Ignore không untrack file đã commit, không xóa file trên disk, và không bảo đảm phát hiện mọi secret trong code/output. Khi repo cũ đã track secret: xử lý việc untrack, rotate và lịch sử Git theo quyền quản trị; việc thêm ignore không tự sửa lịch sử. Preview commit đầu chặn một số file nhạy cảm/private-key content, symlink/nested repo, file >20 MiB; giới hạn 2000 file và tổng 100 MiB. Repo lớn dùng Git panel/terminal và chính sách LFS phù hợp.

## Sử dụng Git panel mỗi ngày

Mở đúng thư mục repo trong File Browser → Git panel → xem Diff → Stage file → nhập commit message → Commit → Push. Pull trước khi cập nhật nếu đồng đội có thay đổi. Nếu có conflict, hòa giải và commit bằng công cụ Git, không dùng wizard để tạo repo mới.

Commit thông thường không cần GitHub auth; push/pull private cần SSH. `Enter passphrase` là mật khẩu mở khóa private key, không phải nội dung key. HTTPS prompt username/password thường cần PAT; wizard này chuyển repo sang SSH. Key trên Windows/Ubuntu host không tự trở thành key của Jupyter container.

## Chẩn đoán

| Dấu hiệu | Cách xử lý |
|---|---|
| Key exists, chưa loaded | Unlock đúng passphrase; không tạo đè key |
| Permission denied (publickey) | Kiểm public key đã add đúng tài khoản/repo, agent loaded và origin SSH |
| Đọc được nhưng push bị từ chối | Quyền write, deploy key write, branch protection hoặc quy định tổ chức |
| Remote không trống ở First push | Dùng Luồng B hoặc fetch/reconcile bằng native Git |
| Wrong directory / nested repo | Chọn root của repo; không tạo `.git` lồng nhau |
| File thay đổi sau preview | Save notebook, Review lại trước commit |
| Agent vẫn lỗi sau update | Rebuild/recreate notebook để Jupyter kế thừa socket; terminal tự bật agent khác không cập nhật server |
| GitHub host key thay đổi | Xác minh host key chính thức và cập nhật pin trong source; không tắt StrictHostKeyChecking |

Nguồn: [JupyterLab Git authentication](https://github.com/jupyterlab/jupyterlab-git/blob/v0.51.2/README.md#authentication-to-remote-repository-hosts), [GitHub SSH agent](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/generating-a-new-ssh-key-and-adding-it-to-the-ssh-agent), [Deploy keys](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys).
