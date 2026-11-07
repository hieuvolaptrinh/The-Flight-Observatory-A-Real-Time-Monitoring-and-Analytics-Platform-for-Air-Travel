"""
Flight Data Simulator
─────────────────────
GET /flights  →  trả về batch tiếp theo từ CSV, giả lập data động.
Mỗi lần gọi, cursor phía server tự tiến; hết data thì wrap về đầu.
"""
import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone

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


# ── State (in-memory, reset khi restart) ───────────────────────────────
class _State:
    records: list[dict] = []
    cursor: int = 0


_state = _State()


# ── Lifespan: đọc CSV 1 lần ────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Đang tải dữ liệu từ %s …", config.CSV_PATH)
    try:
        _state.records = load_records(config.CSV_PATH)
        _state.cursor = 0
        log.info("Tải xong: %d bản ghi.", len(_state.records))
    except Exception as e:
        log.critical("Không thể tải dữ liệu: %s", e)
        raise SystemExit(1) from e
    yield


# ── App ─────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Flight Data Simulator",
    version="1.0.0",
    description="Trả về dữ liệu chuyến bay theo từng batch, giả lập luồng data động.",
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
    fetched_at: str          # thời điểm gọi API (UTC)
    cursor: int              # vị trí bắt đầu của batch này
    next_cursor: int         # vị trí batch tiếp theo
    batch_size: int          # số bản ghi thực tế trả về
    total: int               # tổng số bản ghi trong dataset
    wrapped: bool            # True nếu batch này đã wrap về đầu
    data: list[dict]


# ── Endpoint ─────────────────────────────────────────────────────────────
@app.get("/flights", response_model=FlightsResponse)
def get_flights(
    batch_size: int = Query(default=None, ge=1, le=1000, description="Số bản ghi mỗi batch (mặc định dùng BATCH_SIZE env)")
):
    """
    Mỗi lần gọi trả về batch kế tiếp từ dataset CSV.
    Cursor phía server tự động tiến; hết data thì wrap về đầu.
    """
    size = batch_size or config.BATCH_SIZE
    records = _state.records
    total = len(records)
    start = _state.cursor

    # Lấy batch, wrap nếu cần
    end = start + size
    if end <= total:
        batch = records[start:end]
        wrapped = False
        _state.cursor = end % total  # wrap về 0 nếu đúng cuối
    else:
        # Lấy phần cuối + phần đầu (wrap)
        batch = records[start:] + records[: end - total]
        wrapped = True
        _state.cursor = end - total

    return FlightsResponse(
        fetched_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        cursor=start,
        next_cursor=_state.cursor,
        batch_size=len(batch),
        total=total,
        wrapped=wrapped,
        data=batch,
    )


@app.get("/", include_in_schema=False)
def health():
    return {
        "status": "ok",
        "total_records": len(_state.records),
        "current_cursor": _state.cursor,
    }
