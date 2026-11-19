# PostgreSQL: dữ liệu thô và dữ liệu đã xử lý

Một PostgreSQL container, cổng Windows `127.0.0.1:2001`, chứa hai database:

| Database | Nội dung |
|---|---|
| `flight_raw_db` | Response API trước khi kiểm tra, làm sạch, loại trùng và đổi đơn vị |
| `flight_processed_db` | Dữ liệu ingestion đã xử lý và kết quả Analytics / Clustering / Prediction |

Luồng: API → commit vào `flight_raw_db` → ingestion chuẩn hóa → commit vào `flight_processed_db` → các service phân tích. Nếu ghi raw thất bại, không ghi dữ liệu đã xử lý. Nếu xử lý thất bại, raw vẫn còn để kiểm tra. API key được loại khỏi thông tin request/response đã lưu.

## Chạy PostgreSQL mới

Từ thư mục gốc repo:

```powershell
docker compose --env-file backend/.env -f backend/database/docker-compose.yml up -d --wait
```

Compose dùng `PROCESSED_POSTGRES_DB=flight_processed_db` và `RAW_POSTGRES_DB=flight_raw_db`, tài khoản `root`, mật khẩu `123456`. Dữ liệu vẫn nằm trong volume `flight-delay-backend_analytics_data`; giữ tên volume này để dùng lại dữ liệu cũ.

Script `init-databases.sh` tạo hai database và schema khi khởi tạo volume mới. Với volume đang có database `analytics_db`, thực hiện migration bên dưới; restart container không chạy lại init script.

## Chuyển dữ liệu cũ

Dừng các worker Ingestion, Analytics, Clustering, Prediction trước khi migration. Sao lưu PostgreSQL bằng `pg_dump` trước khi đổi tên. Không dùng `docker compose down -v`.

Cập nhật các file `.env` theo `.env.example`: `DATABASE_URL` và `SOURCE_DATABASE_URL` dùng `flight_processed_db`; riêng ingestion thêm `RAW_DATABASE_URL` dùng `flight_raw_db`. Sau đó chạy trong môi trường Python backend:

```powershell
python backend/database/migrate_databases.py
docker compose --env-file backend/.env -f backend/database/docker-compose.yml up -d --wait
```

Script đổi tên `analytics_db` thành `flight_processed_db`, giữ nguyên các bảng/dữ liệu hiện có; tạo `flight_raw_db` và nhập các JSON gốc còn lưu trong `live_flight_details` và `airport_weather`. Chạy lại script không nhân đôi các bản ghi đã nhập. Bản ghi nhập có `archive_kind='legacy_snapshot'`: đây là snapshot cũ còn giữ, không phải lịch sử đầy đủ các request trước đây.

Khởi động lại các worker để nạp tên database mới. Các service Docker dùng `postgres:5432`; các terminal Miniconda trên Windows dùng `127.0.0.1:2001`.

## Xem bằng DBeaver

Host `127.0.0.1`, port `2001`, database kết nối `postgres`, username `root`, password `123456`. Bật **Show all databases** và Refresh.

Trong `flight_raw_db` → `public` → Tables:

- `raw_api_responses`: mỗi response AirLabs/OpenWeather là một snapshot, có endpoint, tham số không chứa key, thời điểm lấy và JSON gốc.
- `raw_flights`: từng dòng lịch bay, giữ cả dòng trùng và dòng không hợp lệ; `processing_status` là `pending`, `processed`, `rejected` hoặc `duplicate`.
- `raw_weather`: gió gốc m/s, tầm nhìn gốc mét, JSON thời tiết gốc.

Trong `flight_processed_db`:

- `public.ingested_flights`: các chuyến đã chuẩn hóa và cập nhật theo khóa chuyến; có `raw_response_id` và `raw_row_index` để đối chiếu nguồn.
- `public.airport_weather`: gió km/h, tầm nhìn km; `raw_response_id` trỏ tới response gốc.
- `flight_data.*`: dữ liệu chuyến bay theo mô hình quan hệ.
- `analytics.*`: các kết quả thống kê/dự báo.
- Các bảng legacy từ phiên bản cũ được giữ nguyên; luồng live mới đọc raw từ `flight_raw_db`.

Ví dụ mở hai SQL Editor, mỗi editor chọn đúng database:

```sql
-- Kết nối flight_raw_db
SELECT response_id, row_index, airline_iata, flight_number, dep_time,
       processing_status, processing_error, processed_flight_key
FROM public.raw_flights ORDER BY raw_id DESC LIMIT 50;
SELECT response_id, airport_code, wind_speed_ms, visibility_m
FROM public.raw_weather;
```

```sql
-- Kết nối flight_processed_db
SELECT raw_response_id, raw_row_index, flight_key, crs_dep_time,
       crs_elapsed_time, distance, delay_status
FROM public.ingested_flights ORDER BY ingested_at DESC LIMIT 50;
SELECT raw_response_id, airport_code, wind_speed_kmh, visibility_km
FROM public.airport_weather;
```

Ghép theo `response_id = raw_response_id` và `row_index = raw_row_index`. Ví dụ raw gió `10 m/s`, tầm nhìn `8000 m` trở thành `36 km/h`, `8 km`. Số dòng raw có thể lớn hơn số chuyến đã xử lý vì giữ nhiều lần lấy và các dòng bị loại/trùng.

API `/api/ingestion/raw` đọc từ database raw; `/api/ingestion/flights` đọc dữ liệu đã xử lý. Trang danh sách chuyến bay giữ hai chế độ Raw/Processed và hiển thị trạng thái xử lý của dòng raw.
