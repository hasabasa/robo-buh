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

    # Alem Plus (грант Астана Хаб) — OpenAI-совместимый шлюз, у КАЖДОЙ модели свой ключ.
    # Vision работает ТОЛЬКО через data:image/...;base64 (внешние URL → 403).
    alem_base_url: str = "https://llm.alem.ai/v1"
    # qwen3-6 (vision, thinking) — структурный разбор выписок + классификация назначения
    alem_vision_model: str = "qwen3-6"
    alem_vision_key: str = ""
    # deepseek-ocr — сырая транскрипция тяжёлых сканов (фолбэк/препроцесс)
    alem_ocr_model: str = "deepseek-ocr"
    alem_ocr_key: str = ""
    # text-1024 — эмбеддинги (1024-мерн., нормализованные) для RAG-базы знаний
    alem_embed_model: str = "text-1024"
    alem_embed_key: str = ""

    # База знаний (глоссарий + НК + КНП) — путь монтируется в контейнер
    kb_docs_path: str = "/app/docs/knowledge"

    app_secret_key: str = ""
    env: str = "dev"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
