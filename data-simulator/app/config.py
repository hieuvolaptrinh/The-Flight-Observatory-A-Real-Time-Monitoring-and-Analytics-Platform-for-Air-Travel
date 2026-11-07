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
SLIDE_STEP:  int = int(os.getenv("SLIDE_STEP",  "20"))
