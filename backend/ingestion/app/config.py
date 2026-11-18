import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic import BaseModel, Field, SecretStr

_SERVICE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(_SERVICE_DIR / ".env")
load_dotenv(_SERVICE_DIR.parent / ".env")

_DEFAULT_DB = f"sqlite:///{(_SERVICE_DIR / 'data' / 'flights.db').as_posix()}"


def _env_bool(key: str, default: bool = False) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


class Settings(BaseModel):
    airlabs_api_key: SecretStr = Field(default_factory=lambda: SecretStr(os.getenv("AIRLABS_API_KEY", "")))
    airlabs_accounts: SecretStr = Field(default_factory=lambda: SecretStr(os.getenv("AIRLABS_ACCOUNTS", "")))
    airlabs_airports: str = Field(default_factory=lambda: os.getenv("AIRLABS_AIRPORTS", "JFK"))
    airlabs_max_pages: int = Field(default_factory=lambda: int(os.getenv("AIRLABS_MAX_PAGES", "1")), ge=1, le=20)
    airlabs_monthly_budget: int = Field(default_factory=lambda: int(os.getenv("AIRLABS_MONTHLY_BUDGET", "800")), ge=1)
    airlabs_reset_day: int = Field(default_factory=lambda: int(os.getenv("AIRLABS_RESET_DAY", "1")), ge=1, le=28)
    openweather_api_key: SecretStr = Field(default_factory=lambda: SecretStr(os.getenv("OPENWEATHER_API_KEY", "")))
    openweather_monthly_budget: int = Field(default_factory=lambda: int(os.getenv("OPENWEATHER_MONTHLY_BUDGET", "10000")), ge=1)
    openweather_reset_day: int = Field(default_factory=lambda: int(os.getenv("OPENWEATHER_RESET_DAY", "1")), ge=1, le=28)
    weather_cache_seconds: int = Field(default_factory=lambda: int(os.getenv("WEATHER_CACHE_SECONDS", "900")), ge=60)
    service_name: str = Field(default_factory=lambda: os.getenv("SERVICE_NAME", "ingestion"))
    root_path: str = Field(default_factory=lambda: os.getenv("ROOT_PATH", ""))
    scheduler_enabled: bool = Field(default_factory=lambda: _env_bool("SCHEDULER_ENABLED", True))
    run_on_startup: bool = Field(default_factory=lambda: _env_bool("RUN_ON_STARTUP", True))
    job_interval_seconds: float = Field(
        default_factory=lambda: float(os.getenv("JOB_INTERVAL_SECONDS", "300")),
        ge=300,
        allow_inf_nan=False,
        validate_default=True,
    )
    database_url: str = Field(default_factory=lambda: os.getenv("DATABASE_URL") or _DEFAULT_DB)
    trigger_downstream_urls: str = Field(
        default_factory=lambda: os.getenv("TRIGGER_DOWNSTREAM_URLS", "")
    )
