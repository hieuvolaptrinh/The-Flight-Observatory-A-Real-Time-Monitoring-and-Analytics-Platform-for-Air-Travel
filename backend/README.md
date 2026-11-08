# Flight Delay Backend

Bộ khung 5 service: gateway, analytics, clustering, prediction và ingestion.
Mỗi service có Dockerfile riêng. Gateway dùng Nginx; 4 service Python dùng FastAPI.
Data simulator nằm riêng tại `data-simulator/` ở gốc repository.

## Cấu trúc

```text
backend/
  gateway/
  analytics/
  clustering/
  prediction/
  ingestion/
  database/              # Compose chạy riêng PostgreSQL
  requirements.txt       # Dependencies runtime của cả 4 service Python
  docker-compose.yml
  .env.example
```

Mỗi service Python có `app/main.py` (API), `config.py` (cấu hình),
`pipeline.py` (nghiệp vụ), `jobs.py` (job và lịch chạy),
`schemas.py` (dữ liệu trả về), requirements.txt và .env.example.

Có hai cách chạy: dùng container để kiểm tra toàn bộ hệ thống qua gateway, hoặc dùng
Miniconda để sửa code và test các service Python mà không cần build image.

## Cách 1: Chạy bằng container (Docker Compose)

Mở Docker Desktop, chờ Engine sẵn sàng. Từ thư mục backend:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up --build -d
docker compose ps
```

Các lần sau, nếu code và cấu hình không đổi:

```powershell
docker compose up -d
```

Sau khi sửa source, build lại service tương ứng:

```powershell
docker compose up -d --build analytics
```

Compose backend dùng chung PostgreSQL với [Compose chạy riêng database](database/README.md). Các cổng mặc định sau chỉ bind vào `127.0.0.1` trên máy chủ. Có thể đổi trong `backend/.env`.

| Service | Cổng trên máy | Cổng trong container |
| --- | --- | --- |
| PostgreSQL | 2001 | 5432 |
| Gateway | 2002 | 8080 |
| Simulator | 2003 | 8000 |
| Ingestion | 2004 | 8000 |
| Analytics | 2005 | 8000 |
| Clustering | 2006 | 8000 |
| Prediction | 2007 | 8000 |

| Service | Swagger qua gateway | API kết quả |
| --- | --- | --- |
| Analytics | http://localhost:2002/api/analytics/docs | GET /api/analytics/summary |
| Clustering | http://localhost:2002/api/clustering/docs | GET /api/clustering/clusters |
| Prediction | http://localhost:2002/api/prediction/docs | GET /api/prediction/predictions |
| Ingestion | http://localhost:2002/api/ingestion/docs | GET /api/ingestion/flights |

Gateway healthcheck ở http://localhost:2002/health.

```powershell
docker compose logs -f analytics
docker compose down
```

## Cách 2: Chạy local bằng Python trong Miniconda

Dùng cách này khi viết code và test từng service. Python chạy bằng Conda, còn Analytics và Ingestion kết nối với PostgreSQL tại `127.0.0.1:2001`. Xem [lệnh khởi động riêng PostgreSQL](database/README.md).
Có thể dùng chung một Conda environment cho 4 service vì dependencies hiện giống nhau.

### Tạo environment và cài dependencies một lần

Cài Miniconda, mở **Anaconda PowerShell Prompt** hoặc PowerShell đã nhận lệnh conda.
Từ gốc repository:

```powershell
conda create -n flight-delay python=3.12 pip -y
conda activate flight-delay
Set-Location backend
python -m pip install -r requirements.txt
```

Nếu đã có environment Python 3.12 phù hợp, chỉ cần activate environment đó và cài
requirements.txt. Không cần tạo thêm .venv. Khi mở terminal mới, activate lại
environment; chỉ cài lại dependencies khi requirements thay đổi.

Nếu PowerShell chưa nhận conda activate, mở Anaconda PowerShell Prompt hoặc chạy
`conda init powershell` từ terminal đã nhận conda, sau đó đóng và mở lại PowerShell.

### Khởi động các service

Mỗi service chạy trong một terminal riêng. Mở từng terminal tại thư mục backend,
activate environment rồi chạy lệnh tương ứng. Chỉ cần mở các service đang muốn test.

Terminal Analytics:

```powershell
conda activate flight-delay
Set-Location analytics
$env:DATABASE_URL = "postgresql://analytics:analytics@127.0.0.1:2001/analytics_db"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --loop asyncio --reload
```

Terminal Clustering:

```powershell
conda activate flight-delay
Set-Location clustering
python -m uvicorn app.main:app --host 127.0.0.1 --port 8002 --reload
```

Terminal Prediction:

```powershell
conda activate flight-delay
Set-Location prediction
python -m uvicorn app.main:app --host 127.0.0.1 --port 8003 --reload
```

Terminal Ingestion:

```powershell
conda activate flight-delay
Set-Location ingestion
$env:DATABASE_URL = "postgresql://analytics:analytics@127.0.0.1:2001/analytics_db"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8004 --loop asyncio --reload
```

`--reload` tự khởi động lại service khi lưu thay đổi file Python. Không cần build
container hoặc cài lại requirements sau mỗi lần sửa code.
Thay đổi .env cần dừng bằng Ctrl+C và chạy lại lệnh.
Giữ scheduler tắt khi dùng --reload để tránh lượt chạy tự động trong lúc sửa code.
Khi cần test scheduler, bỏ --reload và chỉ chạy một instance của service.

| Service | Swagger local | Healthcheck |
| --- | --- | --- |
| Analytics | http://localhost:8001/docs | http://localhost:8001/health |
| Clustering | http://localhost:8002/docs | http://localhost:8002/health |
| Prediction | http://localhost:8003/docs | http://localhost:8003/health |
| Ingestion | http://localhost:8004/docs | http://localhost:8004/health |

Các giá trị mặc định cho phép chạy ngay, không cần tạo .env.
Muốn cấu hình riêng, copy .env.example thành .env trong thư mục service:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Khi chạy local, giữ ROOT_PATH rỗng và scheduler tắt:

```dotenv
ROOT_PATH=
SCHEDULER_ENABLED=false
```

backend/.env dùng cho Compose; mỗi service local đọc .env trong chính thư mục service.
Nhấn Ctrl+C để dừng server và `conda deactivate` để thoát environment.

Gateway Nginx hiện dùng tên service trong mạng Docker. Với cách local này, gọi trực
tiếp các cổng 8001–8004; gateway không chạy trong Conda. Dùng cách 1 khi cần kiểm tra
toàn bộ luồng qua gateway và CORS. Cấu hình hiện tại chỉ xử lý CORS tại gateway,
nên gọi API từ trình duyệt frontend khác origin khi chạy local cần thêm CORS cho
service hoặc proxy request qua Next.js; Swagger trên chính service dùng được ngay.

Tham khảo [quản lý Conda environment](https://docs.conda.io/projects/conda/en/stable/user-guide/tasks/manage-environments.html).

## Kiểm tra bằng Swagger hoặc PowerShell

Mỗi service Python có GET /health, GET /results, GET /jobs/latest và POST /run,
cùng endpoint kết quả riêng trong bảng. Trong Swagger, chọn endpoint rồi nhấn
Try it out và Execute.

Ví dụ gọi trực tiếp Analytics khi chạy local:

```powershell
Invoke-RestMethod http://localhost:8001/health
Invoke-RestMethod http://localhost:8001/summary
Invoke-RestMethod -Method Post http://localhost:8001/run
Invoke-RestMethod http://localhost:8001/jobs/latest
```

Với Docker, dùng base URL http://localhost:2002/api/analytics.
POST /run chờ job hoàn thành. Job chạy chồng trả HTTP 409;
lỗi pipeline trả HTTP 500 và giữ kết quả thành công trước đó.

## Ingestion và Analytics

Ingestion đọc Simulator và ghi chuyến bay vào PostgreSQL. Analytics đọc cùng DB, lưu snapshot và cung cấp [API biểu đồ và dự báo](analytics/README.md). Hai scheduler mặc định chạy mỗi 300 giây trong Compose. Có thể đổi chu kỳ hoặc tắt scheduler trong `backend/.env`.

## Kết nối frontend

Khi dùng gateway, cấu hình frontend:

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://localhost:2002/api
```

FRONTEND_ORIGIN trong backend/.env mặc định là http://localhost:3000,
dùng cho CORS tại gateway. API chạy job hiện chưa có authentication;
gateway mặc định chỉ publish trên loopback của máy chủ.
