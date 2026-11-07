# Flight Data Simulator

Giả lập luồng dữ liệu chuyến bay động bằng cách phát từng batch từ file CSV.

## Cấu trúc

```
data-simulator/
├── app/
│   ├── __init__.py
│   ├── main.py      # FastAPI app + endpoint GET /flights
│   ├── config.py    # đọc biến môi trường
│   └── loader.py    # đọc & chuẩn hóa CSV 1 lần lúc khởi động
├── data/            # các file *.csv (T_ONTIME_REPORTING_*.csv)
├── .env.example
├── .env.local
├── requirements.txt
└── Dockerfile
```

## Cách chạy

```bash
# Tạo môi trường ảo
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/Mac

pip install -r requirements.txt

# Chạy server
uvicorn app.main:app --reload --port 8000
```

## Biến môi trường

| Biến | Mặc định | Mô tả |
|------|----------|-------|
| `CSV_PATH` | `./data` | File CSV hoặc thư mục chứa `*.csv` |
| `BATCH_SIZE` | `100` | Số bản ghi trả về mỗi lần gọi API |

## API

### `GET /flights`

Mỗi lần gọi tự động trả về batch kế tiếp từ dataset. Hết dữ liệu thì wrap về đầu.

**Query params:**
- `batch_size` *(tùy chọn)*: ghi đè BATCH_SIZE, từ 1 đến 1000

**Response mẫu:**
```json
{
  "fetched_at": "2025-01-01T00:00:00Z",
  "cursor": 0,
  "next_cursor": 100,
  "batch_size": 100,
  "total": 7000000,
  "wrapped": false,
  "data": [
    {
      "DAY_OF_WEEK": 1,
      "FL_DATE": "2025-01-06",
      "OP_UNIQUE_CARRIER": "AA",
      "TAIL_NUM": "N102NN",
      "OP_CARRIER_FL_NUM": "179",
      "ORIGIN": "JFK",
      "DEST": "SFO",
      "CRS_DEP_TIME": "0829",
      "CRS_ARR_TIME": "1222",
      "CRS_ELAPSED_TIME": 413.0,
      "DISTANCE": 2586.0,
      ...
    }
  ]
}
```

### `GET /`
Health check — trả về trạng thái service và vị trí cursor hiện tại.

## Docker

```bash
docker build -t flight-simulator .
docker run -p 8000:8000 -v ./data:/app/data flight-simulator
```

## Ghi chú

- Dữ liệu được đọc **1 lần** khi khởi động, không đọc lại mỗi request.
- Cursor lưu trong bộ nhớ → reset về 0 khi restart service.
- Simulator **không tạo dữ liệu delay** và **không gọi ML model**.
- `fetched_at` là thời điểm thực tế gọi API (UTC), không phải giờ bay.
