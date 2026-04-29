from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_dsn: str = "postgresql://etl:etl@postgres:5432/etl"
    redis_url: str = "redis://redis:6379/0"
    jwt_secret: str = "please-change-me"
    jwt_expires_min: int = 15
    jwt_refresh_days: int = 30
    admin_username: str = "admin"
    admin_password: str = "admin"
    extract_url: str = "http://extract:8000"
    storage_dir: str = "/data/files"

    qwen_url: str = "http://host.docker.internal:8112"
    qwen_model: str = "mlx-community/Qwen3.5-9B-MLX-4bit"
    qwen_summary_timeout: float = 120.0
    qwen_summary_max_tokens: int = 600


settings = Settings()
