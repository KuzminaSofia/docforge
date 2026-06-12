"""Разрешение секретов (API-ключей) для backend-обработчиков.

Лучшая практика: секрет не хранится в БД. В `backend_config` модели кладется
либо имя env-переменной (`api_key_env`), либо — для тестов/инъекции — прямое
значение (`api_key`). Это generic-механизм: любой API-бэкенд переиспользует его,
передав лишь свой дефолт имени env-переменной.
"""

from __future__ import annotations

import os
from typing import Any

# поля backend_config, через которые задается ключ (единый контракт для всех бэкендов)
API_KEY_CONFIG_FIELD = "api_key"
API_KEY_ENV_CONFIG_FIELD = "api_key_env"


def resolve_api_key(
    config: dict[str, Any],
    *,
    default_env: str | None = None,
) -> str | None:
    """разрешить API key для бэкенда

    Приоритет:
    1. прямое значение `config["api_key"]` (удобно для тестов/инъекции);
    2. env-переменная с именем `config["api_key_env"]` или `default_env`.

    Возвращает None, если ключ не задан ни одним способом.
    """
    direct_value = config.get(API_KEY_CONFIG_FIELD)
    if direct_value:
        return str(direct_value)

    env_name = config.get(API_KEY_ENV_CONFIG_FIELD) or default_env
    if not env_name:
        return None

    return os.getenv(str(env_name)) or None
