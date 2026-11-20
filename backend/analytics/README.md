# Analytics API

Từ gốc repo, chạy stack Docker Compose:

```powershell
docker compose -f backend/docker-compose.yml up -d --build --wait
```

Swagger ở `http://localhost:2002/api/analytics/docs`. Ingestion lấy dữ liệu nguồn theo lịch backend mỗi 300 giây mặc định. Dùng `GET /api/ingestion/flights` để đọc bản ghi đã lưu.

Chạy riêng Analytics trên Windows từ `backend/analytics` với Uvicorn mới cần Selector event loop để Psycopg async hoạt động:

```powershell
uvicorn app.main:app --env-file .env --host 127.0.0.1 --port 2005 --loop asyncio:SelectorEventLoop
```

| Phương thức và đường dẫn dưới `/api/analytics` | Kết quả |
| --- | --- |
| `GET /summary` | Tổng chuyến, thời điểm cập nhật và số chuyến có quan sát trễ đến. |
| `GET /line` | Số chuyến và số liệu theo kỳ. |
| `GET /scatter` | Từng chuyến với ngày, giờ địa phương và thời lượng dự kiến. |
| `GET /histogram` | Các khoảng thời lượng rộng 30 phút theo kỳ. |
| `GET /trend` | Đường xu hướng hồi quy tuyến tính theo tháng, tuần, hoặc theo ngày khi chưa có hai tuần quan sát. |
| `GET /seasonality` | Thành phần mùa vụ sau khi bỏ xu hướng. Chu kỳ 12 tháng hoặc 4 tuần, cần ít nhất hai lần quan sát mỗi pha. Khi chưa đủ mẫu, trả thêm `hourly_profile` với phân bố khởi hành theo giờ. |
| `GET /correlation` | Ma trận Pearson và số mẫu cho từng cặp biến. |
| `POST /run` | Cập nhật snapshot ngay. |
| `POST /forecast` | Tạo và lưu dự báo Gemini cho ngày mai theo múi giờ cấu hình. |
| `GET /forecast` | Đọc số chuyến dự báo, giải thích và trạng thái sẵn sàng. |
| `GET /classification` | Đọc nhãn lưu lượng `high` hoặc `low` của cùng dự báo. |

Các endpoint danh sách hỗ trợ `limit` mặc định 5, `offset` và trả `has_more`. Line, scatter và histogram nhận `grain=day|week|month`. Trend và seasonal nhận `grain=auto|week|month`. `auto` dùng tháng khi có đủ tháng quan sát. Trend cần ít nhất 6 tháng để chọn tháng. Seasonal cần ít nhất 24 tháng để chọn tháng. `GET /coverage` trả ngày đầu và ngày cuối có bản ghi. Dùng `date_from` và `date_to` cùng nhau để lọc khoảng ngày. `date_to` là cận loại trừ. Khoảng mặc định và khoảng chỉ định hỗ trợ tối đa 1.096 ngày.

```text
GET /api/analytics/line?grain=week&limit=5&offset=0
GET /api/analytics/histogram?grain=day&date_from=2025-01-06&date_to=2025-01-07
```

Đặt `GEMINI_API_KEY` trong `backend/analytics/.env`. Có thể đặt `GEMINI_MODEL` và `FORECAST_TIMEZONE` tại cùng file. Múi giờ mặc định là `America/New_York`. Với Docker, đặt `FORECAST_AIRPORTS` trong `backend/.env` nếu muốn dùng phạm vi khác `AIRLABS_AIRPORTS`. Các sân bay trong một dự báo nên cùng múi giờ.

Analytics cần ít nhất 5 ngày có chuyến từ nguồn live trong 28 ngày trước hôm nay. Gemini nhận số chuyến khởi hành đã tổng hợp theo ngày và ước tính trong cùng phạm vi thu thập. Nhãn `high` nghĩa là số dự báo bằng hoặc vượt trung vị mẫu lịch sử. Khi scheduler bật và có khóa, service kiểm tra lúc khởi động và mỗi giờ. Lượt tạo thủ công và scheduler dùng lại kết quả lưu trong PostgreSQL cho cùng ngày và phạm vi. Các request GET chỉ đọc dữ liệu.

Khi demo với lịch sử ngắn, đặt `FORECAST_MIN_OBSERVED_DAYS=1` trong `backend/analytics/.env`. Dự báo dùng dưới 5 ngày được hiển thị là **Dự báo sơ bộ**. Đặt lại 5 để dùng ngưỡng mặc định.

Có thể [nạp CSV trước](../ingestion/db/README.md) để demo trend và seasonality. Dự báo ngày mai dùng lịch sử live.

## Kiểm tra trên dashboard

- Trang `/analytics` tải line, scatter, histogram, trend, seasonality và ma trận tương quan qua gateway. Bộ chọn ngày, tuần, tháng áp dụng cho line, scatter và histogram. Scatter và histogram dùng kỳ được chọn. Tham số `period_start` là ngày bắt đầu kỳ theo `grain`.
- Mọi GET biểu đồ chỉ đọc snapshot đã lưu, kể cả khi lọc ngày. Scheduler hoặc `POST /run` tạo đồng thời line, histogram, scatter, trend, seasonal và ma trận correlation ba biến trong cùng transaction. Payload có `version=2`; snapshot cũ được tạo lại khi chạy service mới.
- Nút **Chạy phân tích** gọi `POST /run`. Khi lọc ngày, request có JSON `{"date_from":"2026-11-01","date_to":"2026-11-20"}`; `date_to` là cận loại trừ. **Tải lại** chỉ đọc kết quả. Trend/seasonal chưa đủ lịch sử hiển thị trạng thái thiếu dữ liệu.
- Trong database demo riêng, tắt scheduler, chạy `/run`, xóa các dòng `analytics.schedule_snapshots`, rồi tải lại để thấy thiếu kết quả. Gọi `/run` để phục hồi. GET không tự tạo lại dữ liệu đã xóa. Kiểm thử bằng `TEST_ANALYTICS_DATABASE_URL` trỏ tới database có tên bắt đầu bằng `test` và chạy `python -m pytest backend/analytics/tests -q`.
- Trang `/forecast` đọc dự báo lưu lượng đã lưu. Nút **Tạo dự báo** gọi `POST /forecast` và cần cấu hình Gemini như trên. Để chuẩn bị model dự đoán delay cho demo, chạy `docker compose -f backend/docker-compose.yml run --rm --no-deps prediction python -m app.train` trước buổi demo. Lệnh lưu model vào volume `prediction_models`, cần giữ volume này khi dựng lại container.
