"""
Flight Data Simulator
─────────────────────
GET /flights

Sliding window: mỗi lần gọi trả về WINDOW_SIZE records,
cửa sổ tự trượt +SLIDE_STEP — giả lập dữ liệu động.
Chỉ load file CSV đầu tiên khi khởi động.
"""
import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import config
from app.loader import load_records

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("simulator")


# ── State (in-memory) ───────────────────────────────────────────────────
class _State:
    records: list[dict] = []
    window_start: int = 0   # vị trí đầu cửa sổ hiện tại


_state = _State()


def _first_csv(csv_path: str) -> str:
    """Trả về đường dẫn file CSV đầu tiên trong thư mục (hoặc chính file đó)."""
    p = Path(csv_path)
    if p.is_file():
        return str(p)
    files = sorted(p.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"Không tìm thấy *.csv trong: {csv_path}")
    log.info("Tìm thấy %d file CSV, chỉ load file đầu: %s", len(files), files[0].name)
    return str(files[0])


# ── Lifespan: đọc CSV 1 lần ────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        csv_file = _first_csv(config.CSV_PATH)
        log.info("Đang tải: %s …", csv_file)
        _state.records = load_records(csv_file)
        _state.window_start = 0
        log.info(
            "✓ Tải xong: %d records | window=%d | slide=%d",
            len(_state.records), config.WINDOW_SIZE, config.SLIDE_STEP,
        )
    except Exception as e:
        log.critical("Không thể tải dữ liệu: %s", e)
        raise SystemExit(1) from e
    yield


# ── App ─────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Flight Data Simulator",
    version="1.0.0",
    description=(
        "Trả về cửa sổ trượt dữ liệu chuyến bay, giả lập luồng data động.\n\n"
        "Mỗi lần gọi `GET /flights`, cửa sổ tự trượt +`SLIDE_STEP` records:\n"
        "- 20 record mới xuất hiện ở cuối\n"
        "- 20 record cũ biến mất ở đầu\n\n"
        "**Simulator không tạo dữ liệu delay và không gọi ML model.**"
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ── Schema ──────────────────────────────────────────────────────────────
class FlightsResponse(BaseModel):
    fetched_at: str       # thời điểm gọi API (UTC thực)
    window_start: int     # index đầu cửa sổ trong dataset
    window_end: int       # index cuối cửa sổ (exclusive)
    window_size: int      # số record trả về
    slide_step: int       # bước trượt mỗi lần gọi
    total: int            # tổng record trong dataset
    data: list[dict]


# ── Endpoint ─────────────────────────────────────────────────────────────
@app.get("/flights", response_model=FlightsResponse)
def get_flights(
    window_size: int = Query(
        default=None, ge=1, le=1000,
        description="Kích thước cửa sổ (mặc định = WINDOW_SIZE env, default 100)"
    ),
    slide_step: int = Query(
        default=None, ge=0, le=500,
        description="Bước trượt mỗi lần gọi (mặc định = SLIDE_STEP env, default 20)"
    ),
):
    """
    Trả về cửa sổ trượt gồm `window_size` records.
    Sau mỗi lần gọi, cửa sổ tự dịch chuyển +`slide_step` về phía sau:
    - `slide_step` record mới xuất hiện ở cuối window
    - `slide_step` record cũ biến mất ở đầu window

    Hết dataset → tự wrap về đầu (vòng lặp liên tục).
    """
    size  = window_size or config.WINDOW_SIZE
    step  = slide_step  if slide_step is not None else config.SLIDE_STEP
    total = len(_state.records)

    start = _state.window_start % total
    end   = start + size

    # Lấy dữ liệu (wrap nếu cần)
    if end <= total:
        batch = _state.records[start:end]
    else:
        batch = _state.records[start:] + _state.records[: end - total]

    # Trượt cửa sổ cho lần gọi tiếp theo
    _state.window_start = (start + step) % total

    return FlightsResponse(
        fetched_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        window_start=start,
        window_end=end % total if end > total else end,
        window_size=len(batch),
        slide_step=step,
        total=total,
        data=batch,
    )


@app.get("/", include_in_schema=False)
def health():
    total = len(_state.records)
    return {
        "status": "ok",
        "total_records": total,
        "window_start": _state.window_start,
        "window_size": config.WINDOW_SIZE,
        "slide_step": config.SLIDE_STEP,
    }
