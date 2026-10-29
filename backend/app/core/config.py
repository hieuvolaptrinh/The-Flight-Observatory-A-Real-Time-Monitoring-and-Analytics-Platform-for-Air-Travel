import os
from pathlib import Path
from typing import ClassVar
from pydantic import model_validator
from pydantic_settings import BaseSettings
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"

load_dotenv(ENV_FILE)


class Configs(BaseSettings):
    # base
    ENV: str = os.getenv("ENV", "dev")
    API: str = "/api"
    API_V1_STR: str = "/api/v1"
    API_V2_STR: str = "/api/v2"
    PROJECT_NAME: str = "AI Invoice API"

    PROJECT_ROOT: ClassVar[Path] = PROJECT_ROOT

    # date
    DATETIME_FORMAT: str = "%Y-%m-%dT%H:%M:%S"
    DATE_FORMAT: str = "%Y-%m-%d"

    # auth
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = (
        60 * 24 * 180  # 60 minutes * 24 hours * 180 days = 30 days
    )

    # CORS
    BACKEND_CORS_ORIGINS: list[str] = ["*"]

    # database
    DB: str = os.getenv("DB", "postgresql")
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
    DB_NAME: str = os.getenv("DB_NAME", "ai-invoice")
    DB_USER: str = os.getenv("DB_USER", "root")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")

    # Sẽ được tính trong model_validator sau khi load đủ các field
    DATABASE_URI: str = ""

    # MinIO / S3-compatible storage
    MINIO_ENDPOINT: str = os.getenv("MINIO_ENDPOINT", "localhost:9000")
    MINIO_ACCESS_KEY: str = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    MINIO_SECRET_KEY: str = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    MINIO_BUCKET: str = os.getenv("MINIO_BUCKET", "ai-invoice")
    MINIO_PUBLIC_URL: str = os.getenv("MINIO_PUBLIC_URL", "http://localhost:9000")
    MINIO_SECURE: bool = os.getenv("MINIO_SECURE", "false").lower() == "true"

    # find query
    PAGE: ClassVar[int] = 1
    PAGE_SIZE: ClassVar[int] = 20
    ORDERING: ClassVar[str] = "-id"

    # Gemini
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI-KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL") or os.getenv(
        "GEMINI-MODEL", "gemini-1.5-flash"
    )

    model_config = {"case_sensitive": True}

    @model_validator(mode="after")
    def build_database_uri(self) -> "Configs":
        if self.DB != "postgresql":
            raise ValueError("DB must be 'postgresql'")

        self.DATABASE_URI = (
            "postgresql+psycopg2://"
            f"{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}"
            f"/{self.DB_NAME}"
        )

        return self


configs = Configs()
