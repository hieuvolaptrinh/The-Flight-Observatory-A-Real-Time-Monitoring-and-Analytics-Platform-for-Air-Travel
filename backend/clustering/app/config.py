import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic import BaseModel, Field

_SERVICE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(_SERVICE_DIR / ".env")
load_dotenv(_SERVICE_DIR.parent / ".env")

_DEFAULT_DB = f"sqlite:///{(_SERVICE_DIR / 'data' / 'clustering.db').as_posix()}"
_DEFAULT_SOURCE_DB = f"sqlite:///{(_SERVICE_DIR.parent / 'ingestion' / 'data' / 'flights.db').as_posix()}"
_DEFAULT_CSV = str((_SERVICE_DIR.parent.parent / "data-simulator" / "data" / "T_ONTIME_REPORTING_1.csv").resolve())
_DEFAULT_MODEL = str((_SERVICE_DIR / "models" / "clustering_bundle.joblib").resolve())


def _env_bool(key: str, default: bool = False) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


class Settings(BaseModel):
    service_name: str = Field(default_factory=lambda: os.getenv("SERVICE_NAME", "clustering"))
    root_path: str = Field(default_factory=lambda: os.getenv("ROOT_PATH", ""))
    scheduler_enabled: bool = Field(default_factory=lambda: _env_bool("SCHEDULER_ENABLED", False))
    job_interval_seconds: float = Field(
        default_factory=lambda: float(os.getenv("JOB_INTERVAL_SECONDS", "86400")),
        gt=0,
        allow_inf_nan=False,
    )
    database_url: str = Field(default_factory=lambda: os.getenv("DATABASE_URL") or _DEFAULT_DB)
    source_database_url: str = Field(default_factory=lambda: os.getenv("SOURCE_DATABASE_URL") or os.getenv("DATABASE_URL") or _DEFAULT_SOURCE_DB)
    fallback_csv_path: str = Field(default_factory=lambda: os.getenv("FALLBACK_CSV_PATH") or _DEFAULT_CSV)
    model_path: str = Field(default_factory=lambda: os.getenv("MODEL_PATH") or _DEFAULT_MODEL)
    n_clusters: int = Field(default_factory=lambda: int(os.getenv("N_CLUSTERS", "4")), ge=2, le=10)
    max_sample_rows: int = Field(default_factory=lambda: int(os.getenv("MAX_SAMPLE_ROWS", "60000")), ge=500, le=500000)
