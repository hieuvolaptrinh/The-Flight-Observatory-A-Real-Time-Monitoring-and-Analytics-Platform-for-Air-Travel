# Flight Observatory — Live APIs

Luồng mặc định: **AirLabs schedules + OpenWeather → Ingestion → PostgreSQL → Analytics / Clustering / Prediction → Frontend**.
Không khởi động simulator, không mount CSV và không fallback sang CSV trong chế độ live.

## 1. Cấu hình

Mở `backend/.env` (copy từ `.env.example` nếu chưa có):

```dotenv
AIRLABS_API_KEY=your_key
AIRLABS_AIRPORTS=JFK
AIRLABS_MAX_PAGES=1
AIRLABS_MONTHLY_BUDGET=800
AIRLABS_RESET_DAY=1
OPENWEATHER_API_KEY=your_key
OPENWEATHER_MONTHLY_BUDGET=10000
OPENWEATHER_RESET_DAY=1
WEATHER_CACHE_SECONDS=900
INGESTION_INTERVAL_SECONDS=300
```

Không gửi key vào frontend. Các hạn mức ở trên là ngân sách do ứng dụng tự đặt, không phải cam kết quota của nhà cung cấp. Đặt ngày reset và ngân sách theo dashboard, trừ lượt đã dùng bên ngoài ứng dụng. Bộ đếm không tự đồng bộ với nhà cung cấp.

Backend tự lên lịch ingestion mỗi 300 giây theo mặc định. Hai lượt bắt đầu cách nhau tối thiểu 300 giây. Mốc lượt gần nhất lưu trong DB để lần khởi động lại dùng chung lịch. Một sân bay/một trang mỗi 5 phút chạy 24/7 cần khoảng 8.640 request schedules/30 ngày, chưa tính tra sân bay. Với budget 800, service sẽ dừng gọi khi hết budget và giữ dữ liệu đã lưu.

Mỗi trang schedules yêu cầu tối đa 50 dòng. Tăng `AIRLABS_MAX_PAGES` trong `.env` (ví dụ `2`) để lấy thêm trang khi nguồn còn dữ liệu. Mỗi trang và mỗi lượt tra sân bay chưa có cache tính riêng vào ngân sách AirLabs. Nếu chạm giới hạn phân trang, `/providers` ghi coverage partial. `AIRLABS_AIRPORTS=JFK` lấy chuyến khởi hành từ JFK, gồm cả tuyến quốc tế.

## 2. Chạy Docker

Từ thư mục `backend`:

```powershell
docker compose up --build -d --remove-orphans
docker compose ps
docker compose logs -f --tail 100 ingestion
```

`--remove-orphans` gỡ container simulator cũ thuộc cùng Compose project. Không xóa volume PostgreSQL. Không dùng `down -v` khi muốn giữ dữ liệu.

- Frontend: http://localhost:3000
- Ingestion Swagger: http://localhost:2002/api/ingestion/docs
- Trạng thái nguồn/quota: http://localhost:2002/api/ingestion/providers
- Chuyến bay: http://localhost:2002/api/ingestion/flights
- Snapshot response đã lưu: http://localhost:2002/api/ingestion/raw

Khi sửa `.env`, chạy `docker compose up -d ingestion` để tạo lại container với biến mới. `restart` không nạp lại cấu hình Compose. Khi sửa code, thêm `--build`.

Thiếu key vẫn khởi động được và `/providers` báo nguồn chưa sẵn sàng. Tải lại trang và đổi bộ lọc chỉ đọc dữ liệu đã lưu. Scheduler backend là điểm khởi chạy lượt thu thập AirLabs và OpenWeather.

## 3. Nhiều tài khoản

Chỉ cấu hình tài khoản được phép dùng cho ứng dụng. `AIRLABS_ACCOUNTS` là JSON một dòng, ghi trong dấu nháy đơn của `.env`. Khi có biến này, nó thay thế `AIRLABS_API_KEY`/`AIRLABS_AIRPORTS`:

```dotenv
AIRLABS_ACCOUNTS='[{"name":"team_a","key":"KEY_A","airports":["JFK"],"quota_group":"account_a","budget":800,"reset_day":1},{"name":"team_b","key":"KEY_B","airports":["ORD"],"quota_group":"account_b","budget":800,"reset_day":1}]'
```

Mỗi sân bay chỉ gán một lần. Key dùng chung quota phải cùng `quota_group`, `budget`, `reset_day`. Không tự chuyển sang tài khoản khác khi hết quota. Lượt schedules, airports, phân trang và request lỗi đều được tính trước khi gửi; mất kết nối vẫn tính bảo thủ. Lỗi giới hạn kích hoạt thời gian chờ lưu trong DB. Tạo key mới không tự thêm quota.

## 4. Database và dữ liệu

Ingestion tự chạy migration idempotent lúc khởi động cho DB hiện có:

- Cho phép `delay_minutes` và `is_delayed` là NULL; trạng thái `unknown`.
- Thêm `provider_cache`, `provider_usage`, `airport_weather`, `live_flight_details` và số lượng cập nhật batch.
- Giữ dữ liệu cũ. Dữ liệu API có khóa bắt đầu bằng `airlabs:`; không trộn định danh với CSV.
- Upsert chuyến bay; bảng raw lưu snapshot mới nhất, không phải lịch sử mọi response.

Airports API được cache 30 ngày, thời tiết theo sân bay 15 phút. Khoảng cách là great-circle ước tính theo miles; thời gian bay tính từ giờ lịch UTC hoặc giờ địa phương + IANA timezone. Khi API không cấp tọa độ/múi giờ, trường không tính được để NULL. Không gọi dữ liệu địa điểm cho mỗi chuyến nếu đã có cache.

Delay ước tính hiển thị có nhãn riêng; chỉ giờ thực tế mới ghi delay quan sát vào `flight_data.flight_outcomes`. Giữ dấu âm cho chuyến đến/đi sớm. Dữ liệu thiếu không được coi là đúng giờ. Các KPI delay của ingestion tính trên những chuyến có giá trị delay (bao gồm ước tính); Analytics tính arrival delay từ outcome quan sát.

Weather hiện tại dùng cho demo chuyến gần thời điểm hiện tại. Không dùng nó làm thời tiết lịch sử hoặc dự báo ngày mai. Prediction bỏ qua snapshot quá 2 giờ; trường thời tiết tùy chọn thiếu được dùng default của model và liệt kê trong `weather_defaults_used`.

## 5. Mô hình

Prediction cần artifact **prediction_bundle.joblib** đã huấn luyện theo 12 feature hiện có. Không có artifact thì service vẫn healthy nhưng `/results` báo `ready=false`, `reason=model_missing`; không tự sinh dự báo hoặc train CSV.

Để đưa model có sẵn vào volume (thay đường dẫn trên máy):

```powershell
docker compose cp ./prediction/models/prediction_bundle.joblib prediction:/service/models/prediction_bundle.joblib
docker compose restart prediction
```

Chỉ nạp artifact tin cậy và dùng phiên bản scikit-learn tương thích lúc huấn luyện. `joblib` không phải định dạng an toàn để nạp file không rõ nguồn.

Clustering dùng model có sẵn trong image/volume. Nếu chưa có model, nó có thể huấn luyện từ DB khi đủ sân bay với khoảng cách, thời gian và delay; ít dữ liệu thì trả trạng thái chờ. Scheduler clustering mặc định 24 giờ; có thể dùng nút Chạy K-Means sau khi lấy dữ liệu mới.

Analytics và Prediction có scheduler riêng mỗi 5 phút. `TRIGGER_DOWNSTREAM_URLS` tùy chọn có thể chứa URL `/run` nội bộ nếu muốn gọi sau ingestion; tránh bật trùng cả webhook và scheduler khi không cần.

## 6. Kiểm thử

Python 3.12:

```powershell
python -m pip install -r requirements.txt pytest pyyaml
python -m pytest ingestion/tests -q
```

Test dùng HTTP mock, không tiêu quota hoặc cần key thật. Kiểm thử PostgreSQL tùy chọn bằng `TEST_DATABASE_URL` trong một database test riêng. Không dùng DB chứa dữ liệu cần giữ.

Tài liệu nguồn: https://airlabs.co/docs/schedules · https://airlabs.co/docs/airports · https://openweathermap.org/api/current
