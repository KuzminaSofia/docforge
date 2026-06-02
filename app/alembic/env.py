from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from technical_document_ml_service.db.base import Base
from technical_document_ml_service.db.config import settings
import technical_document_ml_service.db.models  # noqa: F401 — регистрирует все модели в Base.metadata

# логирование не конфигурируем здесь: при программном вызове через migrate.py
# владелец logging — сам скрипт; при вызове через alembic CLI — Python default
config = context.config
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Генерация SQL без подключения к БД (alembic upgrade --sql)."""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Применение миграций к живой БД."""
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = settings.database_url

    connectable = engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
