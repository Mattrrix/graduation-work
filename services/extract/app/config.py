from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_dsn: str = "postgresql://etl:etl@postgres:5432/etl"
    kafka_bootstrap: str = "kafka:9092"
    kafka_topic_raw: str = "raw-docs"
    storage_dir: str = "/data/files"

    ocr_enabled: bool = True
    ocr_url: str = "http://host.docker.internal:8111"
    ocr_model: str = "PaddlePaddle/PaddleOCR-VL-1.5"
    ocr_timeout: float = 180.0
    ocr_dpi: int = 200
    ocr_max_pages: int = 10
    ocr_max_tokens_per_page: int = 1500


settings = Settings()
