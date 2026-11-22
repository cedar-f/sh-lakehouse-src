# API và data contracts

Tham chiếu: `runtime/lakehouse_server.py`, `runner.py`, `run_store.py`, `workflows.py`, `workflow_runtime.py`. Đây là API nội bộ của UI hiện tại, chưa có cam kết backward compatibility cho client bên ngoài. Ghi commit khi tích hợp.

## Ba bề mặt HTTP

| Bề mặt | Base URL mặc định | Xác thực |
|---|---|---|
| Jupyter gateway | `http://127.0.0.1:8888/lakehouse/api/` | Jupyter login cookie/XSRF hoặc `Authorization: token <JUPYTER_TOKEN>` |
| Runner private | `http://runner:8765/` trong Docker network | `X-Runner-Token: <RUNNER_TOKEN>` cho application endpoints; health không yêu cầu token |
| Kestra | `http://kestra:8080/api/v1/main/` trong Docker network | Basic auth KESTRA_USER/KESTRA_PASSWORD |

Runner có FastAPI OpenAPI mặc định; không publish port 8765 chỉ để xem swagger. Có thể lấy schema trong container:

```bash
docker compose exec -T runner python3 -c 'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8765/openapi.json").read().decode())'
```

Các route runner riêng không được gateway forward cùng tên: GET `/health` (không auth), GET `/config`, GET `/sql/status`, POST `/run` (đồng bộ), POST `/workflow/execute` (advanced orchestration). Gateway dùng GET cluster và POST cluster/restart cho các thao tác status/restart ở UI; không gọi GET /lakehouse/api/config như thể đó là runner trực tiếp.

Jupyter gateway gom nhiều lỗi thành HTTP 400 `{"error":"..."}`; runner trực tiếp có HTTPException/validation status riêng. Chưa login gateway có thể redirect tới login. Không giả định HTTP 200 submission đồng nghĩa task đã SUCCESS. Không `source .env`: file dotenv có giá trị chứa khoảng trắng và không được thiết kế như shell script.

## Gateway: catalog, files và compute

Các path sau tính từ `/lakehouse/api/`:

| Method / path | Request chính | Kết quả / tác động |
|---|---|---|
| GET catalogs | — | `catalogs` list, tự theo pagination UC |
| GET schemas | `catalog`, optional `page_token` | UC schemas payload |
| GET tables / volumes | `catalog`, `schema`, optional `page_token` | UC payload tương ứng |
| GET table | `name=catalog.schema.table` | Metadata + authorization.enforced=false |
| POST catalogs | JSON name, optional comment | Tạo catalog rồi schema default |
| POST schemas | JSON name, catalog_name, optional comment | Tạo schema |
| GET files | prefix (default incoming/), optional page_token | folders, files[{key,size}], next_page_token, bucket; page tối đa 200 keys |
| GET download | key | Redirect URL R2 presigned 300 giây |
| POST files/delete | key, kind, confirmation | deleted, has_more, errors[{key,code,message}] |
| GET cluster | — | Saved Spark config, kernel IDs/paths/states, SQL status và restart snapshot |
| POST cluster/restart | scope, kernel_ids, config | Restart operation có id/state; poll path dưới |
| GET cluster/restarts/{id} | — | Snapshot restart nằm trong Jupyter memory, không giữ qua restart Jupyter |
| GET preferences | — | timezone |

Identifiers catalog/schema/table theo pattern chữ/số/underscore, bắt đầu bằng chữ/underscore. Delete chỉ nhận exact file key hoặc prefix thư mục con dưới incoming/, confirmation phải bằng key. Không xóa root incoming, warehouse hoặc backup qua endpoint này. Folder phải có `/` cuối; mỗi request tối đa 1000 object, gọi tiếp cùng target khi has_more=true. Dừng khi có errors; không coi deleted là atomic transaction hoặc có undo. Multipart upload đang có ở target chặn xóa; không upload đồng thời từ phiên khác trong lúc xóa.

### Multipart upload

| Method / path | Request | Response |
|---|---|---|
| POST upload/start | JSON key, size | id 32 hex, part_size=33554432 |
| GET upload | query id | id, key, parts đã có trên R2 |
| POST upload/part | query id, part; **binary body** | ETag, PartNumber |
| POST upload/complete | JSON id | CompleteMultipartUpload sau kiểm đủ tổng size |
| POST upload/abort | JSON id | Abort và xóa session metadata local |

Key upload phải nằm dưới incoming/, không kết thúc bằng `/`, không chứa đoạn `..`, độ dài kiểm ở gateway tối đa 1000 ký tự; R2 còn giới hạn key riêng. Size >0 và tối đa 32 MiB × 10000; mỗi part 1..32 MiB, số part 1..10000. Backend từ chối file key đã tồn tại ở bước start. UI truyền từng file/part tuần tự và nhớ identity key+size+lastModified trong localStorage. Resume cần cả session JSON trong runtime volume lẫn multipart state R2; đây không phải upload transaction với writer khác.

## Gateway proxy: job, history, workflow và bảo trì

| Method / path | Contract |
|---|---|
| POST jobs | Submit async job; trả id/status QUEUED; poll runs/{id} |
| GET jobs | Tối đa 100 run.json gần nhất; UI history mới dùng endpoint có paging |
| GET jobs/{id} | Legacy status kèm log tail nếu có |
| POST sql | JSON sql, optional catalog; response columns/rows, truncated nếu có resultset; tối đa 1000 rows |
| GET history/runs | search, kind, status, from_time, to_time, page, page_size |
| GET history/workflows | Cùng filters; đồng bộ từ Kestra, warning nếu chỉ đọc cache |
| GET runs/{id} | Metadata, code snapshot, artifacts và summary |
| GET runs/{id}/logs | cursor, limit, level, search, source; trả items/cursor/has_more/timezone |
| GET runs/{id}/models | dbt model/test status từ manifest/run_results/live events |
| GET runs/{id}/cells | page, page_size; notebook cells/output |
| GET workflow-history/{execution_id} | Kestra tasks, advanced local trace, inputs/output, runs và logs nếu có |
| GET docs/latest | project, default dbt; run_id hoặc null |
| GET flows | Danh sách JSON workflow trong workspace |
| POST flows | Workflow object; compile, create/update Kestra, lưu JSON/YAML sau khi publish thành công |
| POST flows/{flow_id}/execute | Optional parameters object; tạo execution Kestra |
| GET executions | Legacy search tối đa 30 executions |
| POST config | Lưu Spark config chung; restart_sql=true để queue SQL restart |
| GET maintenance | Preview artifact cleanup |
| POST maintenance | Apply cleanup; xem retention policy trước khi gọi |

History response: `items,total,page,page_size,pages,timezone`; page >=1 và page_size chỉ nhận 10/25/50/100/200. Endpoint cells có page_size riêng 1..100. Filter timestamp chấp nhận ISO datetime; giá trị không có offset được diễn giải bằng TZ. Date range lọc thời điểm bắt đầu run, không phải ended. Run ID là 32 hex; execution ID thuộc Kestra, không dùng thay run ID để tải artifact.

Structured log page: `items` gồm timestamp, level, source, message và các field cell/model khi có. Cursor opaque; dùng nguyên cursor trả về cho page tiếp, không tự tăng số. File log/artifact còn tùy retention; history row tồn tại không bảo đảm artifact vẫn còn.

Artifact download và Docs nằm ngoài `/api/`:

```text
GET /lakehouse/artifacts/{run_id}?path=target/run_results.json
GET /lakehouse/docs/{run_id}/index.html
GET /lakehouse/docs/{run_id}/manifest.json
GET /lakehouse/docs/{run_id}/catalog.json
```

Cùng Jupyter auth. Artifact path bị chặn traversal/secret-named file/profiles.yml; không public thư mục runs bằng web server riêng. UI log giữ 1000 event gần nhất trong browser; dùng paging/artifact cho phần đầy đủ còn được giữ.

## Gateway: GitHub workspace

Các route dưới `/lakehouse/api/git/` dùng Jupyter auth/XSRF. Không đưa passphrase vào query string, URL hoặc log. Phạm vi là user Jupyter hiện tại; các action không chạy trong runner.

| Method / path | Request / response |
|---|---|
| GET status | path relative workspace, mặc định .; trả initialized/branch/head/remote/upstream/name/email và ssh key_exists/public_key/fingerprint/agent_running/key_loaded |
| POST key | passphrase string; tạo Ed25519 khi chưa có key, không overwrite |
| POST unlock | passphrase string; nạp key vào agent dùng chung, không lưu passphrase |
| POST test | remote; kiểm ls-remote, trả readable/empty, không xác nhận write |
| POST init | path, remote, name, email, branch; init/connect và auto ignore, giữ origin khác/branch khác bằng cách từ chối |
| POST clone | path đích mới/trống dưới workspace, remote, name, email; clone default branch và tự áp config/ignore |
| GET preview | path; trả files[{path,size,blocked}], total_bytes và token ràng buộc file/index |
| POST commit | path, token, files[], message; commit đầu local, không push |
| POST push | path, confirmation đúng SSH URL; first push không force, đặt upstream |

Remote chỉ nhận GitHub URL không có credential và chuẩn hóa SSH. Clone không overlay folder đã có file; first push không hòa giải remote có history khác. Git command timeout local 30 giây, network 90 giây; preview tối đa 2000 file/100 MiB, mỗi file 20 MiB. Chỉ tạo initial commit khi chưa có HEAD. `.gitignore` managed block được merge/update nhưng không untrack file đã commit. Agent socket và private key không được trả qua API; public_key/key_path/fingerprint dùng để thiết lập và chẩn đoán. Xem [GITHUB_WORKSPACE](GITHUB_WORKSPACE.md).

## Payload mẫu chạy job

Notebook job (file phải có trong workspace):

```json
{"kind":"notebook","path":"notebooks/etl.ipynb","parameters":{"batch":"daily"},"timeout":3600}
```

dbt job:

```json
{"kind":"dbt","path":"dbt_sample","command":"build","catalog":"lakehouse","schema":"dbt_sample","select":"customer_totals","parameters":{},"timeout":7200}
```

Commands dbt: build/run/test/seed/snapshot/docs/deps/debug; UI gọi docs, runner chuyển thành `dbt docs generate`. parameters được truyền thành dbt vars. Không có endpoint chạy shell command tùy ý.

Compute restart:

```json
{"scope":"sql","kernel_ids":[],"config":{"threads":"2","driver_memory":"2g","shuffle_partitions":8,"default_catalog":"lakehouse","default_schema":"default","extra":{"spark.sql.sources.default":"delta"}}}
```

scope nhận sql/notebooks/both; scope notebooks cần kernel_ids còn hoạt động. Config driver_memory là chuỗi như 2g/1536m; threads là auto hoặc 1..512; shuffle_partitions 1..10000; extra chỉ spark.sql.*, spark.hadoop.*, spark.jars.* với scalar value. Cấu hình ghi vào file trước khi restart; restart fail không tự rollback file cấu hình.

Một flow đơn giản có node SQL:

```json
{"id":"first_check","cron":"","scheduleEnabled":false,"timezone":"Asia/Ho_Chi_Minh","nodes":[{"id":"check","kind":"sql","sql":"SELECT 1 AS ok","dependsOn":[],"parameters":{},"timeout":120,"attempts":1,"x":30,"y":50}]}
```

Node hỗ trợ notebook/dbt/sql/variable/condition/loop, parent, branch then/else, dependsOn và runWhen success/failure/always. Chi tiết expression và ví dụ ở [RUNS_WORKFLOWS.md](RUNS_WORKFLOWS.md). Render `{{ expression }}` toàn chuỗi giữ kiểu JSON; render trong chuỗi tạo text. Đây không phải SQL parameter binding; cần kiểm tra input trước khi ghép SQL.

## Gọi gateway thủ công trong Bash

Đọc token tương tác, không ghi token thật vào source/example:

```bash
read -r -s -p 'Jupyter token: ' LH_API_TOKEN
printf '\n'
curl -fsS -H "Authorization: token $LH_API_TOKEN" http://127.0.0.1:8888/lakehouse/api/preferences
curl -fsS -H "Authorization: token $LH_API_TOKEN" -H 'Content-Type: application/json' -d '{"sql":"SELECT 1 AS ok"}' http://127.0.0.1:8888/lakehouse/api/sql
unset LH_API_TOKEN
```

Client bên ngoài nên dùng HTTPS URL hoặc tunnel. Synchronous runner POST /run (Kestra dùng) chờ đến terminal, có thể trả 500 với job detail khi failed. Runner POST /workflow/execute nhận flow_b64/execution_id/inputs_b64 cho advanced flows; để compiler tạo payload này, không giả lập retry/cancellation từ HTTP client mà không kiểm tra side effects.
