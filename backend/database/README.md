# PostgreSQL cho Plant-Delay

Từ thư mục gốc repo, chạy riêng PostgreSQL. Compose dùng image PostgreSQL 16 có sẵn và tạo schema trong lần khởi tạo volume đầu tiên.

```powershell
docker compose -f backend/database/docker-compose.yml up -d --wait
```

Khi chạy Ingestion hoặc Analytics bằng Miniconda, đặt biến sau trong terminal của từng service:

```powershell
$env:DATABASE_URL = "postgresql://analytics:analytics@127.0.0.1:2001/analytics_db"
```

Nếu đã cấu hình `backend/.env`, dùng `--env-file backend/.env` cho lệnh chạy Compose riêng và dùng thông tin kết nối tương ứng. Các service chạy trong Docker kết nối qua `postgres:5432`.

### Chuyển từ container cũ

PostgreSQL riêng dùng lại volume Compose `analytics_data`. Nếu PostgreSQL cũ đang chạy trong container `ingestion` hoặc `analytics`, dừng container cũ trước khi chạy Compose database để giải phóng volume:

```powershell
docker compose -f backend/docker-compose.yml stop ingestion analytics
```

Nếu từng dùng cấu hình `main` với volume `postgres_data` và database `flight_db`, dữ liệu đó vẫn nằm trong volume cũ. Cần sao lưu và khôi phục các bảng cần giữ vào `analytics_db` khi chuyển dữ liệu giữa hai volume.

PostgreSQL áp dụng `schema.sql` tự động khi tạo volume mới. Với volume có sẵn từ phiên bản schema cũ, có thể áp dụng lại script sau khi container đã chạy:

```powershell
docker compose -f backend/database/docker-compose.yml exec -T postgres psql -X -v ON_ERROR_STOP=1 -U analytics -d analytics_db -f /docker-entrypoint-initdb.d/01-schema.sql
docker compose -f backend/database/docker-compose.yml exec -T postgres psql -X -v ON_ERROR_STOP=1 -U analytics -d analytics_db -f /docker-entrypoint-initdb.d/02-legacy.sql
```

Xem [cách nạp CSV](../ingestion/db/README.md) và [bảng cổng backend](../README.md).
