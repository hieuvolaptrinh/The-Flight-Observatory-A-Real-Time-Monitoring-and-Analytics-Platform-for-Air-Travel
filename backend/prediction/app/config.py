import os
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_SERVICE_DIR = Path(__file__).resolve().parents[1]
_DATA_DIR = _SERVICE_DIR.parent.parent / "data-simulator" / "data"
_FOUND_CSVS = sorted(_DATA_DIR.glob("*.csv")) if _DATA_DIR.is_dir() else []
_DEFAULT_CSV = str(_FOUND_CSVS[0].resolve()) if _FOUND_CSVS else str((_DATA_DIR / "flight_weather_2025_01.csv").resolve())
_DEFAULT_MODEL = str((_SERVICE_DIR / "models" / "prediction_bundle.joblib").resolve())
_DEFAULT_DB = f"sqlite:///{(_SERVICE_DIR / 'data' / 'prediction.db').as_posix()}"
_DEFAULT_SOURCE_DB = f"sqlite:///{(_SERVICE_DIR.parent / 'ingestion' / 'data' / 'flights.db').as_posix()}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "prediction"
    root_path: str = ""
    scheduler_enabled: bool = True
    run_on_startup: bool = True
    job_interval_seconds: float = Field(default=300, gt=0, allow_inf_nan=False)
    database_url: str = Field(default_factory=lambda: os.getenv("DATABASE_URL") or _DEFAULT_DB)
    source_database_url: str = Field(
        default_factory=lambda: os.getenv("SOURCE_DATABASE_URL") or os.getenv("DATABASE_URL") or _DEFAULT_SOURCE_DB
    )
    fallback_csv_path: str = Field(default_factory=lambda: os.getenv("FALLBACK_CSV_PATH") or _DEFAULT_CSV)
    model_path: str = Field(default_factory=lambda: os.getenv("MODEL_PATH") or _DEFAULT_MODEL)
    max_sample_rows: int = Field(default_factory=lambda: int(os.getenv("MAX_SAMPLE_ROWS", "60000")), ge=500, le=500000)
