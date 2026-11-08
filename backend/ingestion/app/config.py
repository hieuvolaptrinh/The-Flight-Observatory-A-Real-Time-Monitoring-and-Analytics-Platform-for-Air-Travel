import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic import BaseModel, Field

_SERVICE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(_SERVICE_DIR / ".env")
load_dotenv(_SERVICE_DIR.parent / ".env")

_DEFAULT_DB = f"sqlite:///{(_SERVICE_DIR / 'data' / 'flights.db').as_posix()}"
_DEFAULT_CSV = str((_SERVICE_DIR.parent.parent / "data-simulator" / "data" / "T_ONTIME_REPORTING_1.csv").resolve())


def _env_bool(key: str, default: bool = False) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


class Settings(BaseModel):
    service_name: str = Field(default_factory=lambda: os.getenv("SERVICE_NAME", "ingestion"))
    root_path: str = Field(default_factory=lambda: os.getenv("ROOT_PATH", ""))
    scheduler_enabled: bool = Field(default_factory=lambda: _env_bool("SCHEDULER_ENABLED", True))
    run_on_startup: bool = Field(default_factory=lambda: _env_bool("RUN_ON_STARTUP", True))
    job_interval_seconds: float = Field(
        default_factory=lambda: float(os.getenv("JOB_INTERVAL_SECONDS", "300")),
        gt=0,
        allow_inf_nan=False,
    )
    simulator_base_url: str = Field(
        default_factory=lambda: os.getenv("SIMULATOR_BASE_URL") or "http://127.0.0.1:8000"
    )
    simulator_window_size: int = Field(
        default_factory=lambda: int(os.getenv("SIMULATOR_WINDOW_SIZE", "100")),
        ge=1,
        le=1000,
    )
    ingestion_batch_size: int = Field(
        default_factory=lambda: int(os.getenv("INGESTION_BATCH_SIZE", "5")), ge=1, le=1000,
    )
    simulator_slide_step: int = Field(
        default_factory=lambda: int(os.getenv("SIMULATOR_SLIDE_STEP", "20")),
        ge=0,
        le=500,
    )
    database_url: str = Field(default_factory=lambda: os.getenv("DATABASE_URL") or _DEFAULT_DB)
    fallback_csv_path: str = Field(default_factory=lambda: os.getenv("FALLBACK_CSV_PATH") or _DEFAULT_CSV)
    trigger_downstream_urls: str = Field(
        default_factory=lambda: os.getenv("TRIGGER_DOWNSTREAM_URLS", "")
    )
