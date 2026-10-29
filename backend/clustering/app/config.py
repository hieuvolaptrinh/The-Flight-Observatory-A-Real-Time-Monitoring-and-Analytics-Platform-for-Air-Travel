from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "clustering"
    root_path: str = ""
    scheduler_enabled: bool = False
    job_interval_seconds: float = Field(default=86400, gt=0, allow_inf_nan=False)
