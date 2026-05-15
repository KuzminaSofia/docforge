from __future__ import annotations

import base64
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from technical_document_ml_service.core.config import app_settings
from technical_document_ml_service.core.security import hash_password
from technical_document_ml_service.db.base import Base
from technical_document_ml_service.db.models import MLModelORM, UserORM
from technical_document_ml_service.db.session import SessionLocal, engine
from technical_document_ml_service.domain.enums import UserRole
from technical_document_ml_service.main import app


@pytest.fixture(scope="session", autouse=True)
def prepare_database() -> None:
    """
    гарантирует, что таблицы существуют перед запуском тестов
    """
    Base.metadata.create_all(bind=engine)


@pytest.fixture(autouse=True)
def clean_database() -> None:
    """
    очищает все таблицы до и после каждого теста
    """
    table_names = ", ".join(table.name for table in reversed(Base.metadata.sorted_tables))
    truncate_sql = text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE")

    with engine.begin() as connection:
        connection.execute(truncate_sql)

    yield

    with engine.begin() as connection:
        connection.execute(truncate_sql)


@pytest.fixture(autouse=True)
def isolated_storage_dir(tmp_path) -> None:
    """
    подменяет директории хранения файлов на временные
    для каждого теста
    """
    object.__setattr__(app_settings, "uploads_dir", str(tmp_path / "uploads"))
    object.__setattr__(app_settings, "artifacts_dir", str(tmp_path / "artifacts"))

@pytest.fixture
def client():
    """HTTP-клиент FastAPI для API-тестов"""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def session_factory():
    """фабрика сессий для тестов"""
    return SessionLocal


@pytest.fixture
def persisted_user(session_factory) -> UserORM:
    """
    создает и сохраняет пользователя через ORM для тестовых сценариев
    """
    with session_factory.begin() as session:
        user = UserORM(
            id=uuid4(),
            email="persisted.user@example.com",
            password_hash=hash_password("persisted-user-password"),
            role=UserRole.USER.value,
            balance_credits=Decimal("100.00"),
            is_active=True,
        )
        session.add(user)
        session.flush()
        user_id = user.id

    with session_factory() as session:
        return session.get(UserORM, user_id)


@pytest.fixture
def persisted_model(session_factory) -> MLModelORM:
    """
    создает и сохраняет ML-модель напрямую через ORM для тестовых сценариев
    """
    with session_factory.begin() as session:
        model = MLModelORM(
            id=uuid4(),
            name="test-model",
            description="Тестовая модель",
            prediction_cost=Decimal("10.00"),
            is_active=True,
            model_kind="technical_document_extraction",
            supported_document_types=["unknown"],
            backend_name="docling",
            backend_config={"allow_stub_fallback": True},
        )
        session.add(model)
        session.flush()
        model_id = model.id

    with session_factory() as session:
        return session.get(MLModelORM, model_id)


@pytest.fixture
def api_user(session_factory) -> UserORM:
    """
    пользователь для API-тестов с корректным password_hash
    и достаточным балансом
    """
    with session_factory.begin() as session:
        user = UserORM(
            id=uuid4(),
            email="api.user@example.com",
            password_hash=hash_password("test-password"),
            role=UserRole.USER.value,
            balance_credits=Decimal("100.00"),
            is_active=True,
        )
        session.add(user)
        session.flush()
        user_id = user.id

    with session_factory() as session:
        return session.get(UserORM, user_id)


@pytest.fixture
def low_balance_user(session_factory) -> UserORM:
    """
    пользователь для API-тестов с недостаточным балансом
    """
    with session_factory.begin() as session:
        user = UserORM(
            id=uuid4(),
            email="low.balance.user@example.com",
            password_hash=hash_password("low-balance-password"),
            role=UserRole.USER.value,
            balance_credits=Decimal("5.00"),
            is_active=True,
        )
        session.add(user)
        session.flush()
        user_id = user.id

    with session_factory() as session:
        return session.get(UserORM, user_id)
    

@pytest.fixture
def another_api_user(session_factory) -> UserORM:
    """
    второй пользователь для API-тестов с достаточным балансом
    """
    with session_factory.begin() as session:
        user = UserORM(
            id=uuid4(),
            email="another.api.user@example.com",
            password_hash=hash_password("another-test-password"),
            role=UserRole.USER.value,
            balance_credits=Decimal("100.00"),
            is_active=True,
        )
        session.add(user)
        session.flush()
        user_id = user.id

    with session_factory() as session:
        return session.get(UserORM, user_id)


@pytest.fixture
def api_model(session_factory) -> MLModelORM:
    """
    ML-модель для API-тестов
    """
    with session_factory.begin() as session:
        model = MLModelORM(
            id=uuid4(),
            name="test-model",
            description="Тестовая модель для API",
            prediction_cost=Decimal("10.00"),
            is_active=True,
            model_kind="technical_document_extraction",
            supported_document_types=["unknown"],
            backend_name="docling",
            backend_config={"allow_stub_fallback": True},
        )
        session.add(model)
        session.flush()
        model_id = model.id

    with session_factory() as session:
        return session.get(MLModelORM, model_id)


@pytest.fixture
def basic_auth_header_factory():
    """
    фабрика для генерации Basic Auth заголовка
    """
    def _build(email: str, password: str) -> dict[str, str]:
        raw = f"{email}:{password}".encode("utf-8")
        token = base64.b64encode(raw).decode("utf-8")
        return {"Authorization": f"Basic {token}"}

    return _build


@pytest.fixture
def auth_headers(basic_auth_header_factory) -> dict[str, str]:
    """
    Basic Auth заголовок для api_user
    """
    return basic_auth_header_factory("api.user@example.com", "test-password")


@pytest.fixture
def another_auth_headers(basic_auth_header_factory) -> dict[str, str]:
    """
    Basic Auth заголовок для another_api_user
    """
    return basic_auth_header_factory(
        "another.api.user@example.com",
        "another-test-password",
    )


@pytest.fixture
def low_balance_auth_headers(basic_auth_header_factory) -> dict[str, str]:
    """
    Basic Auth заголовок для low_balance_user
    """
    return basic_auth_header_factory(
        "low.balance.user@example.com",
        "low-balance-password",
    )


@pytest.fixture
def publish_task_spy(monkeypatch):
    """
    подменяет реальную публикацию в RabbitMQ на spy-функцию
    проверяет, что сообщение отправлено
    """
    published_messages = []

    def _fake_publish(message, *, queue_name=None) -> None:
        published_messages.append(
            {
                "message": message,
                "queue_name": queue_name,
            }
        )

    monkeypatch.setattr(
        "technical_document_ml_service.services.prediction_submission_service.publish_prediction_task",
        _fake_publish,
    )

    return published_messages
