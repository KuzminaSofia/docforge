from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from technical_document_ml_service.db.config import settings


engine = create_engine(
    settings.database_url,
    echo=settings.db_echo,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def get_db_session() -> Generator[Session, None, None]:
    """
    write-session для запросов, которые могут изменять состояние
    после успешного запроса выполняет commit, при ошибке rollback
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def read_session() -> Generator[Session, None, None]:
    """
    контекстный менеджер read-only сессии для использования вне DI-контейнера
    (SSE-генераторы, фоновые задачи и любой код без FastAPI Depends)
    не коммитит; всегда откатывает и закрывает соединение при выходе
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def get_read_session() -> Generator[Session, None, None]:
    """
    read-only FastAPI-зависимость; делегирует lifecycle в read_session()
    """
    with read_session() as session:
        yield session


def get_plain_session() -> Generator[Session, None, None]:
    """
    сессия без автоматического commit/rollback — логика управления
    транзакцией лежит на вызывающем сервисе
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
