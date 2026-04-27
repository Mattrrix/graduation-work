from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_dsn: str = "postgresql://etl:etl@postgres:5432/etl"
    jwt_secret: str = "please-change-me"
    jwt_expires_min: int = 60
    admin_username: str = "admin"
    admin_password: str = "admin"
    extract_url: str = "http://extract:8000"
    storage_dir: str = "/data/files"


settings = Settings()
