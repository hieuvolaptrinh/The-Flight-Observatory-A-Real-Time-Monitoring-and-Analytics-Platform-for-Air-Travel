# Analytics API

Từ gốc repo, chạy Simulator, Ingestion, PostgreSQL và Analytics qua gateway:

```powershell
docker compose -f backend/docker-compose.yml up -d --build --wait
```

Swagger ở `http://localhost:2002/api/analytics/docs`. Ingestion nạp 5 chuyến mỗi 300 giây theo mặc định. Có thể kiểm tra bản ghi đã lưu bằng `GET /api/ingestion/flights` hoặc nạp một lô ngay bằng `POST /api/ingestion/run`.

| Phương thức và đường dẫn dưới `/api/analytics` | Kết quả |
| --- | --- |
| `GET /summary` | Tổng chuyến, thời điểm cập nhật và số chuyến có quan sát trễ đến. |
| `GET /line` | Số chuyến và số liệu theo kỳ. |
| `GET /scatter` | Từng chuyến với ngày, giờ địa phương và thời lượng dự kiến. |
| `GET /histogram` | Các khoảng thời lượng rộng 30 phút theo kỳ. |
| `GET /trend` | Đường xu hướng hồi quy tuyến tính trên chuỗi đã gom theo tháng hoặc tuần. |
| `GET /seasonality` | Thành phần mùa vụ sau khi bỏ xu hướng. Chu kỳ 12 tháng hoặc 4 tuần, cần ít nhất hai lần quan sát mỗi pha. |
| `GET /correlation` | Ma trận Pearson và số mẫu cho từng cặp biến. |
| `POST /run` | Cập nhật snapshot ngay. |
| `POST /forecast` | Tạo và lưu dự báo Gemini cho ngày kế tiếp trong lịch giả lập. |
| `GET /forecast` | Đọc số chuyến dự báo, giải thích và trạng thái sẵn sàng. |
| `GET /classification` | Đọc nhãn lưu lượng `high` hoặc `low` của cùng dự báo. |

Các endpoint danh sách hỗ trợ `limit` mặc định 5, `offset` và trả `has_more`. Line, scatter và histogram nhận `grain=day|week|month`. Trend và seasonal nhận `grain=auto|week|month`. `auto` dùng tháng khi có đủ tháng quan sát. Trend cần ít nhất 6 tháng để chọn tháng. Seasonal cần ít nhất 24 tháng để chọn tháng. Dùng `date_from` và `date_to` cùng nhau để lọc khoảng ngày. `date_to` là cận loại trừ. Mặc định dùng tối đa 366 ngày gần nhất đã nạp. Khoảng chỉ định hỗ trợ đến 1.096 ngày.

```text
GET /api/analytics/line?grain=week&limit=5&offset=0
GET /api/analytics/histogram?grain=day&date_from=2025-01-06&date_to=2025-01-07
```

Đặt `GEMINI_API_KEY` trong `backend/analytics/.env`. `GEMINI_MODEL` có thể thay trong cùng file. `POST /forecast` gửi tối đa 28 ngày số chuyến đã tổng hợp, cần ít nhất 5 ngày có dữ liệu, và dùng lại kết quả đã lưu cho cùng ngày dự báo. Nhãn `high` nghĩa là số dự báo bằng hoặc vượt trung vị mẫu lịch sử. Dự báo là **ước lượng lưu lượng trong mẫu lịch giả lập**. Ngày dự báo là `FL_DATE` lớn nhất đã nạp cộng một ngày. Với CSV lịch bay hiện tại, tỷ lệ trễ thực tế trả `null`.

Có thể [nạp CSV trước](../ingestion/db/README.md) để demo trend, seasonal hoặc forecast mà không phải đợi luồng 5 chuyến tích lũy đủ lịch sử.
