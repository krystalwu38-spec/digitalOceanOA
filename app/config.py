from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "secure-file-service"
    app_env: str = "dev"
    app_secret_key: str = "change-me-in-production"
    storage_dir: str = "uploads/private"
    database_path: str = "uploads/metadata.db"
    max_upload_size_bytes: int = 50 * 1024 * 1024
    min_ttl_seconds: int = 30
    max_ttl_seconds: int = 86400

    model_config = SettingsConfigDict(env_file=".env", env_prefix="SFS_")


@lru_cache
def get_settings() -> Settings:
    return Settings()
