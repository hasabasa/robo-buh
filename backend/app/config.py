"""Конфигурация robo-buh. Все секреты — из env, никаких значений в коде."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # PostgreSQL
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "robobuh"
    postgres_user: str = "robobuh"
    postgres_password: str = ""
    db_pool_min: int = 2
    db_pool_max: int = 10

    redis_url: str = "redis://redis:6379/0"

    # Верификация подписей (сервер НЕ подписывает — только проверяет)
    ncanode_url: str = "http://ncanode:14579"

    # Alem Plus (грант Астана Хаб) — OpenAI-совместимый шлюз.
    # Модели: qwen3-6 (vision, thinking), deepseek-ocr (vision), alemllm, kazllm.
    # Vision работает ТОЛЬКО через data:image/...;base64 (внешние URL → 403).
    alem_base_url: str = "https://llm.alem.ai/v1"
    alem_api_key: str = ""
    alem_ocr_model: str = "deepseek-ocr"     # OCR сканов выписок
    alem_vision_model: str = "qwen3-6"       # структурный разбор + fallback
    alem_text_model: str = "qwen3-6"         # классификация назначения платежа
    alem_kz_model: str = "kazllm"            # казахскоязычные документы

    app_secret_key: str = ""
    env: str = "dev"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
