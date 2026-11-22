# Runs, dbt Docs, workflow và dữ liệu vận hành

Áp dụng implementation V3.1.3; phần ví dụ variable_if_foreach_demo có thể dựng lại từ các bước bên dưới. Starter cài mới là dbt_sample_pipeline theo [REBUILD_DBT.md](REBUILD_DBT.md).

## Các màn hình

- **Runs**: bảng notebook/dbt/SQL và restart Spark; tìm theo tên/ID, lọc type/status/from–to, chọn 10/25/50/100/200 item/trang. Bộ lọc thời gian áp dụng lên thời điểm bắt đầu. Bấm **Apply filters** sau khi nhập search hoặc ngày.
- **View → Code**: snapshot code thực thi, không lấy lại file mới nhất trong workspace. **Logs**: bảng thời gian, level, nguồn/cell/model, message; lọc nguồn, level, nội dung; Load more và Live. Trình duyệt chỉ giữ 1000 event mới nhất; file đầy đủ còn trong Artifacts đến khi hết retention.
- **Models**: trạng thái model/test/seed/snapshot, thời gian và SQL compile từ dbt artifacts. **Cells**: code, trạng thái, thời gian, stdout/error, bảng HTML và hình ảnh của từng cell notebook. Notebook được lưu cả khi một cell thất bại. Kết quả HTML chạy trong iframe sandbox không có script; đây là vùng output, không phải notebook editor nhúng.
- **Outputs**, **Parameters**, **Artifacts**: dữ liệu trả về, tham số và tải file kết quả. Các file profile chứa thông tin kết nối bị chặn tải qua endpoint này. Không ghi đè notebook nguồn.
- **dbt → Open Docs**: mở bản docs thành công gần nhất của project. Nếu chưa có, tự xếp một run `dbt docs generate`, chờ rồi mở. Nút **docs** dùng để chủ động tạo lại docs sau khi đổi model/schema. Docs giữ snapshot theo từng run; build mới không tự làm mới docs cũ.
- **Workflow Run History**: nút riêng trong sidebar và editor. Bảng có các bộ lọc/phân trang như Runs. Chi tiết gồm task, từng iteration, nhánh, input/variables/output, run con và log Kestra. Bấm run con để xem code/cell/model/log của nó. Editor không còn nhúng bảng execution cũ.

Lần chạy trước V3.1 vẫn được nhập vào lịch sử. Những lần cũ có thể thiếu snapshot code, tham số hoặc liên kết run với execution. Nếu log cũ không ghi timestamp, thời gian event được ước tính từ thời điểm bắt đầu run. Không thể khôi phục thông tin chưa được ghi.

## Tạo workflow có logic

1. Mở **Workflows**, tạo flow hoặc Load flow đã lưu.
2. Khai báo Default inputs và Initial variables trong **Inputs, variables and limits**. Khi chạy thủ công có thể nhập Execution input overrides.
3. Thêm Notebook/dbt/SQL, đặt task ID và **Depends on sibling task IDs**. Có thể kéo node để bố trí.
4. **Run when dependencies**: All succeeded; Any failed để xử lý lỗi; Finished, regardless of status để chạy bước cuối. Bước Always không tự biến flow lỗi thành thành công. Nếu handler Failure thành công, các lỗi dependency được handler nhận xử lý sẽ được xem là đã xử lý; trạng thái task lỗi vẫn giữ FAILED trong history.
5. **+ If**: nhập biểu thức như `inputs.enabled == true` hoặc `outputs.extract.count > 0`. Thêm các task con, chọn Parent block bằng ID của If và Then/Else. Task ngoài block phụ thuộc vào ID của If để chờ cả nhánh hoàn tất.
6. **+ For each**: Items là JSON array như `[1, 2, 3]`, hoặc chuỗi JSON `"{{ outputs.extract.items }}"`. Task con chọn Parent block bằng ID của loop. Tham chiếu `{{ item }}`, `{{ loop.index }}` (bắt đầu từ 0). Các iteration chạy tuần tự; biến riêng mỗi iteration. Output loop là `{count, items}`; mỗi phần tử items chứa output task con.
7. **+ Variables**: Values là JSON object, ví dụ `{"batch": "{{ inputs.batch }}", "limit": 100}`. Bước tiếp theo dùng `{{ vars.limit }}`. Trường Parameters/dbt vars là JSON object và hỗ trợ cùng cú pháp.
8. Save & publish áp dụng cả thay đổi đang nhập ở task. Schedule chỉ chạy sau khi bật Enable schedule và Publish. Execution luôn dùng flow đã publish.

Notebook nhận tham số và trả output:

```python
batch = parameters.get("batch", "daily")
set_output("batch", batch)
set_output("items", [2, 3])
set_output("count", 2)
```

Bước tiếp theo đặt Parameters thành `{"batch": "{{ outputs.extract.batch }}"}` nếu notebook có task ID `extract`. Helper `set_output` được runner gắn vào notebook; khi chạy tay không có run context, helper sẽ báo rõ cần chạy bằng runner.

Biểu thức chỉ hỗ trợ JSON fields/index, so sánh, toán học số, boolean và `len()`. Không có Python eval, shell, import hay gọi hàm tùy ý. Giới hạn: 100 node định nghĩa, 5 tầng block, 1000 iteration/block, 10.000 bước thực thi/flow, timeout tối đa 24 giờ. Output notebook tối đa 1 MiB; output tổng của một task/loop tối đa 10 MiB. Với dữ liệu lớn, trả tên bảng/đường dẫn R2 thay cho toàn bộ dữ liệu.

DAG đơn giản vẫn là từng task HTTP trong Kestra. Flow có logic/input/biến/tham chiếu động dùng một task điều phối trong Kestra, runner thực thi các bước và lưu trace. **Kestra giữ lịch và trạng thái tổng; Workflow Run History giữ chi tiết các bước logic.** Các bước trong loop không phải những node native riêng trong Kestra. Retry/timeout của task I/O cấu hình trong editor; flow có nhánh được runner áp dụng. Dừng execution từ Kestra chưa bảo đảm dừng ngay request đang thực thi trong runner; timeout vẫn giới hạn thời gian chạy.

## Ví dụ thực hành: Variable dùng trong cả If và For each

Trên workspace máy dev trước khi tách source/data, flow `variable_if_foreach_demo` đã được giữ tại `/workspace/workflows/variable_if_foreach_demo.json` và đã publish/chạy thử. Đây là trạng thái lịch sử của máy dev, không phải file được Git cài vào host mới. Khi cài mới từ Git, tạo workflow mới với các task và trường mô tả dưới đây, rồi Save & publish. Ví dụ chỉ dùng SQL SELECT tính toán.

1. Refresh trang, mở **Workflows**.
2. Nếu có sẵn `variable_if_foreach_demo`, chọn Saved workflow và bấm **Load**. Nếu cài mới, đặt Flow ID này rồi thêm task theo cấu trúc dưới đây.
3. Bấm vào từng node để xem các trường bên dưới. Bấm **Apply task changes** sau khi chỉnh node.
4. Bấm **Execute saved flow**. Mở **Workflow Run History**, search `variable_if_foreach_demo`, chọn View.

Trong **Inputs, variables and limits**, Default inputs là:

```json
{
  "enabled": true,
  "numbers": [10, 20, 30],
  "factor": 3
}
```

Initial variables để `{}`: bước **+ Variables** tên `set_variables` sẽ gán các input vào tập biến `vars`. Trường **Variable assignments (JSON object)** của bước đó:

```json
{
  "enabled": "{{ inputs.enabled }}",
  "numbers": "{{ inputs.numbers }}",
  "factor": "{{ inputs.factor }}"
}
```

Các biểu thức chiếm toàn bộ giá trị `{{ ... }}` giữ nguyên kiểu dữ liệu: boolean, array và number. `vars.factor` là biến factor; không cần thêm tên node `set_variables` vào đường dẫn.

Node **+ If** tên `check_enabled` có **Depends on** là `set_variables`, **Condition expression**:

```text
vars.enabled and len(vars.numbers) > 0
```

Khi enabled là true và danh sách numbers có phần tử, chạy Then. Ngược lại, chạy Else.

Node **+ For each** tên `for_each_number`: Parent block = `check_enabled`, Condition branch = Then, Depends on để trống. Trường **Items (JSON array or quoted {{ expression }})** nhập cả dấu ngoặc kép:

```json
"{{ vars.numbers }}"
```

Maximum iterations = 20. For each lấy danh sách từ biến `vars.numbers`; mỗi lượt, `item` là phần tử hiện tại và `loop.index` là chỉ số bắt đầu từ 0.

Trong loop có node **+ Variables** tên `calculate`, Parent block = `for_each_number`, Depends on trống:

```json
{
  "iteration": "{{ loop.index + 1 }}",
  "current_number": "{{ item }}",
  "result": "{{ item * vars.factor }}"
}
```

Tiếp theo là **+ SQL** tên `show_result`, Parent block = `for_each_number`, Depends on = `calculate`:

```sql
SELECT {{ vars.iteration }} AS iteration,
       {{ vars.current_number }} AS input_number,
       {{ vars.factor }} AS factor,
       {{ vars.result }} AS result
```

Quan hệ đầy đủ:

| Task | Loại | Parent block | Nhánh | Depends on |
|---|---|---|---|---|
| set_variables | Variables | Top level | — | trống |
| check_enabled | If | Top level | — | set_variables |
| for_each_number | For each | check_enabled | Then | trống |
| calculate | Variables | for_each_number | — | trống |
| show_result | SQL | for_each_number | — | calculate |
| show_skipped | SQL | check_enabled | Else | trống |
| finished | SQL | Top level | — | check_enabled |

Nội dung SQL của `show_skipped`:

```sql
SELECT 'skipped: disabled or empty list' AS message
```

Nội dung SQL của `finished`:

```sql
SELECT 'workflow finished' AS message
```

Giữ Run when dependencies = All succeeded cho ví dụ này; cron để trống, Enable schedule bỏ chọn. Các trường chưa nêu dùng giá trị mặc định của editor.

**Parent block** tạo quan hệ lồng nhau; **Depends on** sắp thứ tự các task cùng cấp. Task con không điền ID cha vào Depends on. `finished` chờ toàn bộ nhánh If được chọn hoàn tất.

Kết quả mặc định của ba lượt `show_result`:

| iteration | input_number | factor | result |
|---|---|---|---|
| 1 | 10 | 3 | 30 |
| 2 | 20 | 3 | 60 |
| 3 | 30 | 3 | 90 |

Trong Workflow Run History → View: **Inputs & variables** hiện biến chung; **Tasks** có `check_enabled/for_each_number[0]/calculate`, `[1]`, `[2]` và các SQL run con. **Outputs → for_each_number → items → 0 → calculate** hiện biến của lượt đầu; thay 0 bằng 1/2 cho các lượt khác. Bấm run con `show_result` để xem Code và Outputs của SQL đã thay biến.

Biến gán bên trong loop được giữ riêng từng lượt. Sau loop, dùng `outputs.for_each_number.items` để lấy kết quả đã gom; không dùng `vars.result` ở cấp ngoài. Các giá trị trong cùng một node Variables được tính trước khi cập nhật vars, vì vậy nếu muốn tham chiếu biến vừa gán, hãy thêm task tiếp theo có Depends on.

Thử thay **Execution input overrides** rồi Execute saved flow:

```json
{"enabled": false}
```

If trả false, `show_skipped` chạy trong Else và không có iteration. Thử `{"numbers": []}` cũng vào Else. Với:

```json
{"numbers": [4, 7], "factor": 5}
```

If dùng biến mới, For each lặp 2 lần và result là 20, 35. Không cần sửa định nghĩa flow khi thay input mỗi lần chạy. Cả 4 trường hợp trên có kết quả SUCCESS qua Kestra/Spark SQL trong đợt kiểm tra lịch sử; xem [Validation](VALIDATION.md). Host mới vẫn cần chạy lại nghiệm thu.

Cấu hình timezone và retention nằm trong [ENVIRONMENT.md](ENVIRONMENT.md); backup, volume và cleanup được hướng dẫn trong [OPERATIONS.md](OPERATIONS.md).
