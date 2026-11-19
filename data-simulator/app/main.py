"""
Flight Data Simulator (Raw DB + Chunked Queue Worker + Keyset Seek)
───────────────────────────────────────────────────────────────────
GET /flights

Sliding window: mỗi lần gọi trả về WINDOW_SIZE raw records từ bảng `raw_flights`
bằng Keyset Seek (`WHERE file_id = :fid AND row_number > :start AND row_number <= :end`),
cửa sổ tự trượt +SLIDE_STEP và lưu trạng thái bền vững vào bảng `raw_simulator_state`.
"""
import asyncio
from contextlib import asynccontextmanager, suppress
import logging
import sys

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import config
from app.loader import RawFlightStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("simulator")


class _RuntimeState:
    store: RawFlightStore | None = None
    worker_task: asyncio.Task | None = None


_runtime = _RuntimeState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        store = RawFlightStore(
            csv_path=config.CSV_PATH,
            database_url=config.DATABASE_URL,
            window_size=config.WINDOW_SIZE,
            slide_step=config.SLIDE_STEP,
            chunk_size=config.CHUNK_SIZE,
            queue_maxsize=config.QUEUE_MAXSIZE,
            max_seed_rows=config.MAX_SEED_ROWS,
        )
        initial_loaded = await asyncio.to_thread(store.seed_initial_chunk_sync)
        _runtime.store = store
        log.info(
            "✓ Simulator khởi tạo Raw DB (%s): loaded=%d/%d | window=%d | slide=%d",
            store.storage_type,
            initial_loaded,
            store.total_rows,
            config.WINDOW_SIZE,
            config.SLIDE_STEP,
        )
        _runtime.worker_task = asyncio.create_task(store.run_background_queue_worker())
    except Exception as e:
        log.critical("Không thể khởi tạo Raw DB Simulator: %s", e)
        raise SystemExit(1) from e

    try:
        yield
    finally:
        if _runtime.worker_task and not _runtime.worker_task.done():
            _runtime.worker_task.cancel()
            with suppress(asyncio.CancelledError):
                await _runtime.worker_task


app = FastAPI(
    title="Flight Data Simulator (Raw DB Engine)",
    version="2.0.0",
    description=(
        "Nạp dữ liệu CSV thô theo từng chunk qua `asyncio.Queue` vào Raw DB (`raw_source_files`, `raw_flights`, `raw_simulator_state`).\n\n"
        "Mỗi lần gọi `GET /flights`, truy vấn Keyset Seek $O(\\log N)$ trên `idx_raw_flights_seek` và trượt cửa sổ +`SLIDE_STEP`."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


class FlightsResponse(BaseModel):
    fetched_at: str       # thời điểm gọi API (UTC thực)
    window_start: int     # index đầu cửa sổ trong dataset
    window_end: int       # index cuối cửa sổ (exclusive)
    window_size: int      # số record trả về
    slide_step: int       # bước trượt mỗi lần gọi
    total: int            # tổng record hiện có trong raw_flights
    data: list[dict]


@app.get("/flights", response_model=FlightsResponse)
async def get_flights(
    window_size: int = Query(
        default=None, ge=1, le=1000,
        description="Kích thước cửa sổ (mặc định = WINDOW_SIZE env, default 100)",
    ),
    slide_step: int = Query(
        default=None, ge=0, le=500,
        description="Bước trượt mỗi lần gọi (mặc định = SLIDE_STEP env, default 20)",
    ),
    start: int | None = Query(
        default=None, ge=0,
        description="Vị trí đọc do client quản lý. Không dịch cửa sổ chung.",
    ),
):
    """
    Trả về cửa sổ trượt gồm `window_size` raw records từ bảng `raw_flights`.
    Sau mỗi lần gọi, cửa sổ tự dịch chuyển +`slide_step` trong bảng `raw_simulator_state`.
    Hết dataset → tự wrap về đầu (vòng lặp liên tục).
    """
    if _runtime.store is None:
        raise HTTPException(status_code=503, detail="Simulator store not initialized")
    try:
        payload = await asyncio.to_thread(
            _runtime.store.get_window,
            window_size=window_size,
            slide_step=slide_step,
            start=start,
        )
        return FlightsResponse(**payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/", include_in_schema=False)
async def health():
    if _runtime.store is None:
        raise HTTPException(status_code=503, detail="Simulator store not initialized")
    return await asyncio.to_thread(_runtime.store.get_status)
