# PostgreSQL cho Flight Analytics

PostgreSQL 16 chạy trong container `postgres`. Các service trong mạng Compose kết nối tới `postgres:5432`, còn ứng dụng chạy bằng Miniconda kết nối tới `127.0.0.1:2001`. Xem [cách khởi động và chuyển volume cũ](../../database/README.md).

Mỗi bản ghi `flight_data.flights` là một chặng bay theo lịch. Dữ liệu lịch bay đi vào `flight_data`. Kết quả mà API Analytics đọc nằm trong `analytics`.

| Bảng hoặc view | Vai trò |
| --- | --- |
| `flight_data.airlines` | Một dòng mỗi hãng vận hành, khóa `carrier_code` lấy từ `OP_UNIQUE_CARRIER`. Tên hãng có thể bổ sung từ danh mục. |
| `flight_data.airports` | Định danh sân bay xuyên thời gian, khóa `airport_id`. |
| `flight_data.airport_versions` | Một dòng mỗi `airport_seq_id`, chứa mã sân bay và `city_market_id` ở phiên bản đó. Hai đầu chặng đều tham chiếu đến phiên bản sân bay. |
| `flight_data.flights` | Ngày, hãng, số hiệu chuyến, số hiệu tàu bay, hai đầu chặng, giờ địa phương theo lịch, thời lượng phút, quãng đường mile. |
| `flight_data.flight_schedule` | View đọc các trường tương ứng đủ 17 cột CSV, kèm `flight_id`. `DAY_OF_WEEK` lấy từ ngày theo ISO, thứ Hai là `1`. |
| `flight_data.flight_outcomes` | Tối đa một kết quả thực tế mỗi `flight_id`, dùng khi có dữ liệu trễ, hủy hoặc chuyển hướng. |
| `analytics.schedule_snapshots` | Một bản kết quả JSONB hoàn chỉnh cho mỗi khoảng ngày. Tính lại cùng khoảng ngày sẽ cập nhật bản kết quả đó trong một giao dịch. |

`FL_DATE` dùng `date`. Import hiểu `1/6/2025` theo tháng/ngày/năm, thành `2025-01-06`. Giờ `0829` thành `08:29:00`. Giờ `2400` giữ thành `24:00:00`. Giờ cất cánh và hạ cánh thuộc hai múi giờ địa phương tương ứng. Khi cần thời lượng bay theo lịch, dùng `CRS_ELAPSED_TIME` có sẵn trong nguồn. `loaded_at` và `computed_at` là `timestamptz`.

Khóa chính nội bộ là `flight_id`. Khóa chống trùng gồm ngày, hãng, số hiệu chuyến, ID sân bay đi, ID sân bay đến và giờ cất cánh theo lịch. Hướng chặng có ý nghĩa, ví dụ `SFO → JFK` và `JFK → SFO` là hai chặng riêng. Index phục vụ khoảng ngày, hãng theo ngày và chặng theo ngày. Khi nạp lại, giữ dòng đã lưu nếu khóa trùng. CSV này được xử lý như dữ liệu lịch sử, nên bản sửa lịch có cùng khóa cần thao tác cập nhật riêng.

## Cài và nạp CSV

Chạy từ thư mục gốc repo bằng PowerShell. Ví dụ dùng thông tin PostgreSQL mặc định của Compose. Nếu đã đặt `ANALYTICS_POSTGRES_USER` hoặc `ANALYTICS_POSTGRES_DB` trong `backend/.env`, thay `analytics` sau `-U` hoặc `analytics_db` sau `-d` tương ứng.

Tên database, user và mật khẩu được dùng để khởi tạo PostgreSQL khi volume còn trống. Khi tái sử dụng volume, dùng thông tin của lần khởi tạo đó.

```powershell
docker compose -f backend/database/docker-compose.yml up -d --wait
docker compose -f backend/database/docker-compose.yml exec -T postgres psql -X -v csv_path=/data-source/T_ONTIME_REPORTING_1.csv -U analytics -d analytics_db -f /opt/analytics-db/import_csv.sql
docker compose -f backend/database/docker-compose.yml exec postgres psql -X -U analytics -d analytics_db
```

Pipeline Ingestion nạp dữ liệu Simulator vào `flight_data.flights` ngay khi khởi động, rồi lặp lại mỗi 300 giây với mặc định 5 chuyến một lô. Con trỏ nằm trong `flight_data.simulator_offsets` và được commit cùng các chuyến. Import CSV là cách nạp nhanh lịch sử cho demo. `csv_path` trỏ đến tệp trong thư mục `/data-source` được mount vào container `postgres`.

```sql
SELECT flight_date, day_of_week, carrier_code, flight_number, origin, dest,
       scheduled_dep_local, scheduled_arr_local, scheduled_elapsed_min, distance_miles
FROM flight_data.flight_schedule
WHERE flight_date = DATE '2025-01-06'
  AND carrier_code = 'AA'
  AND tail_number = 'N102NN'
  AND flight_number IN ('16', '179')
ORDER BY flight_number;
```

## Kết quả Analytics

Khoảng ngày gồm ngày bắt đầu và loại trừ ngày kết thúc. Hàm nhận từ 1 đến 1.096 ngày. Tuần bắt đầu thứ Hai. Bucket ở đầu hoặc cuối có thể chỉ bao gồm một phần tuần hoặc tháng.

```sql
SELECT analytics.refresh_schedule(DATE '2025-01-01', DATE '2025-02-01');

SELECT computed_at, flight_count, payload
FROM analytics.schedule_snapshots
WHERE date_from = DATE '2025-01-01' AND date_to = DATE '2025-02-01';
```

| Thành phần `payload` | Cách đọc |
| --- | --- |
| `series` | Line dùng `flight_count` theo ngày, tuần hoặc tháng. Scatter có một điểm mỗi bucket, trục X là `avg_distance_miles`, trục Y là `avg_scheduled_elapsed_min`, chỉ tính trên các chuyến có cả hai trường. `pair_count` cho biết số chuyến trong điểm. |
| `histogram` | Phân bố thời lượng theo ngày, tuần hoặc tháng. Mỗi khoảng dài 30 phút, gồm cận dưới và loại cận trên. |
| `trend` | Trung bình trượt số chuyến trong 7 ngày lịch, gồm ngày hiện tại. `days_in_average` cho biết số ngày ở đầu khoảng. |
| `seasonality` | Lưu lượng trung bình mỗi ngày theo thứ trong tuần và tháng trong năm. `days_in_range` cho biết số ngày lịch thuộc nhóm. |
| `correlation` | Pearson giữa quãng đường và thời lượng theo từng chuyến, kèm số cặp hợp lệ. Pearson trả về `NULL` khi thiếu biến thiên hoặc thiếu cặp hợp lệ. |

Bucket không có dòng đã nạp có `flight_count = 0`. Chỉ diễn giải đây là lưu lượng thực khi biết CSV hoặc luồng đã bao phủ ngày đó. Với đúng hai dòng mẫu ngày 06/01, số chuyến là 2, quãng đường trung bình 2.586 mile, thời lượng trung bình 375,5 phút, và Pearson là `NULL` vì cả hai chuyến có cùng quãng đường.

Khi có dữ liệu quan sát, lấy `ARR_DELAY`, `DEP_DELAY`, `CANCELLED`, `DIVERTED` từ BTS. `arrival_delay_pct` dùng tỷ lệ số chuyến đến trễ ít nhất 15 phút trên số chuyến có phút trễ lúc đến và không hủy/chuyển hướng. CSV lịch bay hiện tại cho `observed_arrivals = 0` và `arrival_delay_pct = NULL`. Dữ liệu trễ do ingestion mô phỏng thuộc bộ demo riêng.

`POST /api/analytics/run` hoặc job 5 phút gọi `refresh_schedule()` rồi commit. Xem [API Analytics cho UI](../../analytics/README.md) để dùng các biểu đồ và dự báo.

Tham khảo [từ điển dữ liệu BTS](https://www.transtats.bts.gov/Fields.asp?gnoyr_VQ=FGJ) và [kiểu ngày giờ của PostgreSQL 16](https://www.postgresql.org/docs/16/datatype-datetime.html).
