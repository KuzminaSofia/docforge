from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import quote_plus

from dotenv import load_dotenv


#для локальной разработки взять .env, если он найден
# В Docker Compose переменные уже приходят через окружение,
# поэтому override=False не перетирает существующие значения
load_dotenv(override=False)


def _get_env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None:
        raise ValueError(f"Не задана обязательная переменная окружения: {name}")
    return value


def _to_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """
    настройки подключения к базе данных
    можно задать DATABASE_URL целиком,
    либо использовать набор DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASSWORD
    """

    database_url_override: str | None = os.getenv("DATABASE_URL")

    db_host: str = _get_env("DB_HOST", default="database")
    db_port: int = int(_get_env("DB_PORT", default="5432"))
    db_name: str = _get_env("DB_NAME", default="technical_document_service")
    db_user: str = _get_env("DB_USER", default="postgres")
    db_password: str = _get_env("DB_PASSWORD", default="postgres")

    db_echo: bool = _to_bool(_get_env("DB_ECHO", default="false"))

    db_pool_size: int = int(_get_env("DB_POOL_SIZE", default="5"))
    db_max_overflow: int = int(_get_env("DB_MAX_OVERFLOW", default="10"))
    db_pool_timeout: int = int(_get_env("DB_POOL_TIMEOUT", default="30"))
    db_pool_recycle: int = int(_get_env("DB_POOL_RECYCLE", default="1800"))

    @property
    def database_url(self) -> str:
        """полный URL подключения к PostgreSQL"""
        if self.database_url_override:
            return self.database_url_override

        user = quote_plus(self.db_user)
        password = quote_plus(self.db_password)

        return (
            f"postgresql+psycopg://{user}:{password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


settings = Settings()