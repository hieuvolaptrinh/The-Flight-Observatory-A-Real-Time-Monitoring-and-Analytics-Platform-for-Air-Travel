from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "ingestion"
    root_path: str = ""
    scheduler_enabled: bool = True
    job_interval_seconds: float = Field(default=300, gt=0, allow_inf_nan=False)
    simulator_base_url: str = "http://127.0.0.1:8000"
    ingestion_batch_size: int = Field(default=5, ge=1, le=1000)
    database_url: str = ""
