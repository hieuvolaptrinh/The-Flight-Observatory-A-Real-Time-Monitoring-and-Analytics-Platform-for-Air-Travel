import os
from pathlib import Path
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[1]  # thư mục data-simulator/

load_dotenv(_ROOT / ".env.local")
load_dotenv(_ROOT / ".env")

# Nếu CSV_PATH là relative → resolve từ thư mục dự án
_csv_raw = os.getenv("CSV_PATH", "data")
_csv_path = Path(_csv_raw)
if not _csv_path.is_absolute():
    _csv_path = _ROOT / _csv_path

CSV_PATH: str = str(_csv_path)

WINDOW_SIZE: int = int(os.getenv("WINDOW_SIZE", "100"))
SLIDE_STEP: int = int(os.getenv("SLIDE_STEP", "20"))

# Raw DB & Queue Worker Configuration
_DEFAULT_SQLITE_DB = f"sqlite:///{(_ROOT / 'data' / 'raw_flights.db').as_posix()}"
DATABASE_URL: str = os.getenv("DATABASE_URL") or _DEFAULT_SQLITE_DB
CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "5000"))
QUEUE_MAXSIZE: int = int(os.getenv("QUEUE_MAXSIZE", "4"))
MAX_SEED_ROWS: int = int(os.getenv("MAX_SEED_ROWS", "0"))
