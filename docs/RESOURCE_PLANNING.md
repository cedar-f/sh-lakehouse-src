# RAM, CPU, disk và quy mô dữ liệu

Đây là ngân sách khởi đầu cho single host, không phải benchmark hoặc bộ giới hạn đã cài riêng trên server. `.env` trên Ubuntu mới là cấu hình triển khai; không suy ra từ máy dev. Xem thêm [ENVIRONMENT.md](ENVIRONMENT.md).

## 16 GB RAM: cấu hình cân bằng hiện hỗ trợ

Dành trần khoảng 11 GiB cho bốn container có biến memory; để phần còn lại cho Ubuntu, Docker, UC, registry proxy, PostgreSQL và cache. Với 16 GB RAM vật lý, hệ điều hành có thể báo thấp hơn 16 GiB.

```dotenv
SPARK_THREADS=2
SPARK_DRIVER_MEMORY=2g
SPARK_SHUFFLE_PARTITIONS=8
NOTEBOOK_MEMORY=3g
SQL_MEMORY=3g
RUNNER_MEMORY=3g
KESTRA_MEMORY=2g
KESTRA_JAVA_OPTS=-Xms256m -Xmx1g -XX:ActiveProcessorCount=2
```

Đây là proposal cho một người dùng, một interactive kernel và workload nhỏ/vừa, chưa được nghiệm thu cho tải lớn trên Ubuntu 16 GB. Nếu đang bring-up/test rất nhỏ và cần thêm headroom, dùng Spark 1g và ba container notebook/sql/runner 2g; kiểm tra lỗi JVM/Python/memory trước khi tăng.

| Nhóm | Memory ở profile cân bằng |
|---|---:|
| notebook | Cap 3 GiB, Spark heap 2 GiB mỗi kernel |
| sql | Cap 3 GiB, Spark heap 2 GiB; dbt SQL chạy tại đây |
| runner | Cap 3 GiB, notebook nền có Spark heap 2 GiB; dbt client/process cũng ở đây |
| kestra | Cap 2 GiB, Java heap tối đa 1 GiB |
| registry | Cap 256 MiB bổ sung, cấu hình REGISTRY_MEMORY; không chạy Spark |
| Ubuntu/Docker/PostgreSQL/UC/cache | Ngân sách phần còn lại; chưa có hard cap cho catalog/postgres trong env |

Cap container không được cấp phát hết ngay khi bật. JVM heap nằm trong cap container và còn cần Python, native/off-heap, thread stack, Jupyter. Mỗi notebook kernel tạo Spark riêng; hai heap 2g có thể vượt cap notebook 3g. Đóng tab không shutdown kernel. Không cộng heap của SQL/notebook/background thành một pool cho query.

### Muốn ưu tiên Spark 4 GB

2g tương đối ít cho join/sort/aggregation nặng. Có thể đọc dữ liệu lớn hơn RAM theo partition/spill, nhưng performance/OOM phụ thuộc query, Python UDF, cache và toPandas/collect. Không có cam kết xử lý 300 GB bằng một heap 2g.

**Hiện chưa hỗ trợ driver_memory riêng theo service trong config UI.** SPARK_DRIVER_MEMORY và `.lakehouse/spark.json` dùng chung. Proposal SQL heap 4g/container 6g, interactive/background heap 1g/container 2g và Kestra 2g cần sửa thiết kế config theo service trước; không phải profile có thể đạt chỉ bằng thêm biến env. Tăng biến chung lên 4g trong khi cap vẫn 3g sẽ không hợp lệ về ngân sách.

## 32 GB và CPU

Defaults .env.example: Spark 4g, notebook/sql/runner 6g mỗi container, Kestra 4g với Java heap 2g; đây là trần 22 GiB cho bốn container, còn phần cho OS/UC/PG/cache. Vẫn cần giới hạn số kernel/workload đồng thời và đo thực tế.

SPARK_THREADS=auto dùng local[*] theo CPU process nhìn thấy; không phải CPU quota cho toàn stack. Mỗi JVM đều có thể dùng nhiều core. Nên bắt đầu 2 threads ở 16 GB, sau đó thử 4 khi còn headroom và CPU chưa bão hòa. Chưa có biến env CPU quota container; KESTRA_JAVA_OPTS ActiveProcessorCount chỉ điều chỉnh JVM nhìn CPU.

## Disk và R2

- start.sh yêu cầu ít nhất khoảng 15 GiB trống theo filesystem của DockerRootDir trước build. Đây là kiểm tra tối thiểu, không phải tổng ngân sách vận hành; containerd image store có thể ở filesystem khác tùy Docker.
- Gợi ý ban đầu dành 80–100 GB SSD cho image/build cache, Maven, metadata, local temp/shuffle và artifact/backup; cần tăng theo truy vấn thực tế. 300 GB R2 không cần copy hết về SSD nhưng shuffle/spill có thể lớn.
- RUN_STORAGE_MAX_GB chỉ giới hạn artifact terminal; không cap toàn volume, PostgreSQL, cache Maven hoặc warehouse. Spark tmp, image cache và local backups phải quan sát riêng.
- 50 GB/tháng là dự kiến lưu lượng, không suy ra số S3 GET/PUT/LIST của Spark. Scan, shuffle giữa process và lịch dbt có thể thay đổi request/egress. Không có cost cap hay billing monitor tự động trong repo.
- Swap có thể giảm đột biến OOM nhưng không thay RAM cho Spark; chưa có script provision/tune swap. Không dùng tăng swap làm bằng chứng workload đã ổn định.

## Đo trước khi chỉnh

```bash
free -h
docker stats --no-stream
df -h
docker system df
```

Xem available RAM, swap activity nếu có, memory/cap từng container và filesystem Docker/temp. Khi một container restart, kiểm tra đúng tên lấy từ `docker compose ps -a`:

```bash
docker inspect r2-lakehouse-v3-sql-1 --format '{{.State.OOMKilled}} {{.RestartCount}}'
docker compose logs --tail=100 sql runner
```

OOMKilled=false không loại trừ JVM/Python tự out-of-memory. Nếu đã lưu Compute config, đổi env chưa đủ; đồng bộ Compute và restart Spark/session được chọn. Lưu notebook/chờ job trước recreate container.
