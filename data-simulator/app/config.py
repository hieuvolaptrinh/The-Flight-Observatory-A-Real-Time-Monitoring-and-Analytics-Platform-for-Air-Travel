import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

CSV_PATH: str = os.getenv("CSV_PATH", "./data")
BATCH_SIZE: int = int(os.getenv("BATCH_SIZE", "100"))
