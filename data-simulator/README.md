# Flight Data Simulator

Giả lập luồng dữ liệu chuyến bay động bằng **sliding window** trên file CSV.

## Cách hoạt động

```
Lần gọi 1: records[  0 .. 99]   (100 records)
Lần gọi 2: records[ 20 ..119]   (20 mới vào, 20 cũ ra)
Lần gọi 3: records[ 40 ..139]   (20 mới vào, 20 cũ ra)
...
```

- Chỉ load **file CSV đầu tiên** (theo alphabet) khi khởi động
- Dữ liệu đọc **1 lần** vào bộ nhớ, không đọc lại mỗi request
- Hết dataset → tự wrap về đầu (vòng lặp liên tục)

## Cấu trúc

```
data-simulator/
├── app/
│   ├── __init__.py
│   ├── config.py    ← biến môi trường
│   ├── loader.py    ← parse + chuẩn hóa CSV
│   └── main.py      ← FastAPI + GET /flights
├── data/            ← T_ONTIME_REPORTING_*.csv
├── .env.example
├── .env.local
├── requirements.txt
└── Dockerfile
```

## Cài đặt & Chạy

```bash
# Activate môi trường conda
conda activate KDLKP

# Cài thư viện (1 lần)
pip install -r requirements.txt

# Chạy server (từ thư mục data-simulator/)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
# HOẶC dùng --app-dir nếu chạy từ thư mục khác:
# python -m uvicorn app.main:app --app-dir d:\IT\Plant-Delay\data-simulator --port 8000
```

> ⏳ Lần đầu khởi động mất ~20-40 giây để load ~540k records vào RAM.

## Biến môi trường (`.env.local`)

| Biến | Mặc định | Mô tả |
|------|----------|-------|
| `CSV_PATH` | `./data` | Thư mục CSV (load file đầu tiên theo alphabet) |
| `WINDOW_SIZE` | `100` | Số record trả về mỗi lần gọi API |
| `SLIDE_STEP` | `20` | Bước trượt mỗi lần gọi (20 mới vào, 20 cũ ra) |

## API

### `GET /flights`

**Query params** (tùy chọn):
- `window_size` — override WINDOW_SIZE (1–1000)
- `slide_step` — override SLIDE_STEP (0–500)

**Response:**
```json
{
  "fetched_at": "2026-11-07T02:30:00Z",
  "window_start": 0,
  "window_end": 100,
  "window_size": 100,
  "slide_step": 20,
  "total": 539747,
  "data": [
    {
      "DAY_OF_WEEK": 1,
      "FL_DATE": "2025-01-06",
      "OP_UNIQUE_CARRIER": "AA",
      "TAIL_NUM": "N102NN",
      "OP_CARRIER_FL_NUM": "16",
      "ORIGIN": "SFO",
      "DEST": "JFK",
      "CRS_DEP_TIME": "1321",
      "CRS_ARR_TIME": "2159",
      "CRS_ELAPSED_TIME": 338.0,
      "DISTANCE": 2586.0,
      ...
    }
  ]
}
```

### `GET /`
Health check — trạng thái server và vị trí cursor hiện tại.

## Docker

```bash
docker build -t flight-simulator .
docker run -p 8000:8000 -v ./data:/app/data flight-simulator
```

## Ghi chú

- **Simulator không tạo dữ liệu delay** và **không gọi ML model**
- `fetched_at` là thời điểm thực tế gọi API (UTC), không phải giờ bay
- Cursor reset về 0 khi restart service
