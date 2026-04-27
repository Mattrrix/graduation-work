from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_dsn: str = "postgresql://etl:etl@postgres:5432/etl"
    kafka_bootstrap: str = "kafka:9092"
    kafka_topic_raw: str = "raw-docs"
    kafka_group_id: str = "transform-mvp"
    metrics_port: int = 8000


settings = Settings()
