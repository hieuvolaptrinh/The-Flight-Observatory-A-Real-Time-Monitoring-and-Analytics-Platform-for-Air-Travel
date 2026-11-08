from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "analytics"
    root_path: str = ""
    scheduler_enabled: bool = True
    job_interval_seconds: float = Field(default=300, gt=0, allow_inf_nan=False)
    database_url: str = ""
    gemini_api_key: SecretStr | None = None
    gemini_model: str = Field(default="gemini-3.5-flash-lite", pattern=r"^gemini-[a-zA-Z0-9.-]+$")
