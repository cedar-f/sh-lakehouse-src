# Phiên bản và tính tái lập

Phiên bản application lấy từ RELEASE.json và package metadata trong source. File source có thẩm quyền: compose.yaml, runtime/Dockerfile, runtime/requirements.txt, runtime/config.py, catalog/Dockerfile và runtime/labextension/package.json. Bảng mô tả dependency trong source; deployment phải ghi image IDs thực tế.

| Thành phần | Giá trị trong source |
|---|---|
| App / frontend package | 3.1.3; hotfix đóng gói image theo Git commit |
| UC image | unitycatalog/unitycatalog:v0.7.0 |
| UC Spark connector | io.unitycatalog:unitycatalog-spark_4.0_2.13:0.7.0 |
| PySpark | 4.0.1 |
| Delta Python package | delta-spark 4.3.1 |
| Delta Spark connector | io.delta:delta-spark_4.0_2.13:4.3.1 |
| Hadoop AWS Maven | org.apache.hadoop:hadoop-aws:3.4.1 |
| Java/runtime base | eclipse-temurin:17-jdk-jammy |
| Python trong image | Python 3 từ Ubuntu Jammy apt; patch version không pin riêng |
| PostgreSQL | postgres:16.6 |
| Kestra | Pin digest sha256:494d2e81aacd92c0353098822aa7214833f8b1ed7a8fe6b5a46b79b1caec3ec5 trong Compose; không suy ra release chỉ từ tên local image |
| JupyterLab / Git extension / JupyterHub | 4.4.10 / 0.51.2 / 5.4.3 |
| dbt-core / dbt-spark[PyHive] | 1.12.7 / 1.11.0 |
| Node / configurable-http-proxy | Node 22.x qua installer / proxy 5.1.0 |
| boto3 / pandas / pyarrow | 1.44.4 / 2.3.3 / 21.0.0 |
| FastAPI / uvicorn / httpx | 0.162.5 / 0.54.0 / 0.28.1 |
| PyYAML / croniter / nbclient | 6.0.3 / 6.2.4 / 0.11.0 |
| pure-sasl / pytest | 0.6.2 / 8.4.2 |
| Playwright UI test package | 1.65.2; cài browser tương ứng |

Frontend dependency ranges: @jupyterlab/application ^4.4.0, apputils ^4.5.0, services ^7.4.0, @lumino/widgets ^2.5.0, builder ^4.4.0. Chưa commit npm lockfile; pip chỉ pin direct dependencies, transitive có thể thay đổi. Java/UC image tag và apt/Node inputs còn mutable. Vì vậy source hiện **chưa bảo đảm rebuild byte-identical** dù cùng Git commit.

## Ghi nhận deployment thật

Tại root repo, lưu output vào hồ sơ bàn giao riêng (không dump `.env` hoặc toàn inspect environment):

```bash
git rev-parse HEAD
git status --short
docker version
docker compose version
docker compose ps -a
docker compose images
docker image inspect r2-lakehouse-v3-runtime:local --format '{{.Id}}'
docker image inspect r2-lakehouse-v3-catalog:local --format '{{.Id}}'
docker compose exec -T runner python3 --version
docker compose exec -T runner dbt --version
```

Ghi riêng image ID Kestra từ `docker compose images`, thông tin CPU/RAM/disk/OS, commit config proxy và thời gian TZ. Root API/schema compatibility xác nhận bằng checklist, không chỉ bằng version string.

## Khi nâng dependency

Nâng Spark/Delta/UC theo một change set có test tương thích Scala coordinates, managed/external tables, fresh Thrift session, R2 credential expiry/read/write, dbt seed/build/tests/docs và restore. Nâng Kestra cần test namespace API `/api/v1/main`, Basic auth, HTTP task timeout/retry và retention flow. Không đổi digest Kestra sang latest để chữa lỗi login.

Giữ snapshot metadata và image đã chạy trước khi upgrade. Nâng database major/version có thay schema có thể cần restore snapshot thay vì chỉ checkout code cũ. Các phiên bản tham khảo ở tài liệu bên ngoài có thể mới hơn source pin; không tự nâng chỉ vì trang docs upstream chuyển mặc định sang version mới.
