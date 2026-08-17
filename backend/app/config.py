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

    # Qwen (alem.ai): классификация назначений платежей, vision для PDF-выписок
    qwen_api_url: str = ""
    qwen_api_key: str = ""

    app_secret_key: str = ""
    env: str = "dev"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
