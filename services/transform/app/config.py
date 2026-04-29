from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_dsn: str = "postgresql://etl:etl@postgres:5432/etl"
    kafka_bootstrap: str = "kafka:9092"
    kafka_topic_raw: str = "raw-docs"
    kafka_group_id: str = "transform-mvp"
    metrics_port: int = 8000

    llm_enabled: bool = True
    llm_backend: str = "mlx"  # mlx | gigachat

    qwen_url: str = "http://host.docker.internal:8112"
    qwen_model: str = "mlx-community/Qwen3.5-9B-MLX-4bit"
    qwen_timeout: float = 180.0
    qwen_max_tokens: int = 1500
    qwen_max_input_chars: int = 96000

    gigachat_auth_key: str = ""
    gigachat_scope: str = "GIGACHAT_API_PERS"
    gigachat_model: str = "GigaChat"
    gigachat_oauth_url: str = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    gigachat_chat_base: str = "https://gigachat.devices.sberbank.ru"
    gigachat_timeout: float = 60.0
    gigachat_max_tokens: int = 1500
    gigachat_max_input_chars: int = 32000
    gigachat_verify_ssl: bool = False


settings = Settings()
