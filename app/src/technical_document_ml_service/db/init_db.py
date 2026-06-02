from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from technical_document_ml_service.core.security import (
    PASSWORD_SCHEME_PBKDF2_SHA256,
    hash_password,
)
from technical_document_ml_service.domain.enums import DocumentType, UserRole
from technical_document_ml_service.inference.registry import (
    DOCLING_BACKEND_NAME,
    TECHNICAL_DOCUMENT_MODEL_KIND,
)

from technical_document_ml_service.db.models import MLModelORM, UserORM
from technical_document_ml_service.db.session import SessionLocal


def _is_pbkdf2_hash(password_hash: str) -> bool:
    """проверить, что хеш уже в правильном формате pbkdf2_sha256$..."""
    return password_hash.startswith(f"{PASSWORD_SCHEME_PBKDF2_SHA256}$")


def _ensure_user(
    session: Session,
    *,
    email: str,
    raw_password: str,
    role: str,
    balance_credits: Decimal,
    is_active: bool = True,
) -> None:
    existing_user = session.scalar(
        select(UserORM).where(UserORM.email == email)
    )

    if existing_user is None:
        session.add(
            UserORM(
                email=email,
                password_hash=hash_password(raw_password),
                role=role,
                balance_credits=balance_credits,
                is_active=is_active,
            )
        )
        return

    # пользователь уже существует — проверяем формат хеша.
    # если хеш не в формате pbkdf2_sha256 (например, старый SHA-256 hex) - обновить его
    if not _is_pbkdf2_hash(existing_user.password_hash):
        existing_user.password_hash = hash_password(raw_password)


def _ensure_model(
    session: Session,
    *,
    name: str,
    description: str,
    prediction_cost: Decimal,
    model_kind: str,
    supported_document_types: list[str],
    backend_name: str,
    backend_config: dict,
    is_active: bool = True,
) -> None:
    existing_model = session.scalar(
        select(MLModelORM).where(MLModelORM.name == name)
    )
    if existing_model is not None:
        return

    session.add(
        MLModelORM(
            name=name,
            description=description,
            prediction_cost=prediction_cost,
            model_kind=model_kind,
            supported_document_types=supported_document_types,
            backend_name=backend_name,
            backend_config=backend_config,
            is_active=is_active,
        )
    )


def seed_initial_data(session: Session) -> None:
    """заполняет БД начальными демо-данными"""
    _ensure_user(
        session,
        email="demo.user@example.com",
        raw_password="demo-user-password",
        role=UserRole.USER.value,
        balance_credits=Decimal("100.00"),
    )
    _ensure_user(
        session,
        email="demo.admin@example.com",
        raw_password="demo-admin-password",
        role=UserRole.ADMIN.value,
        balance_credits=Decimal("1000.00"),
    )

    _ensure_model(
        session,
        name="technical-document-extractor-basic",
        description="Базовая модель извлечения данных из технических документов",
        prediction_cost=Decimal("10.00"),
        model_kind=TECHNICAL_DOCUMENT_MODEL_KIND,
        supported_document_types=[DocumentType.UNKNOWN.value],
        backend_name=DOCLING_BACKEND_NAME,
        backend_config={},
    )
    _ensure_model(
        session,
        name="technical-document-extractor-advanced",
        description="Расширенная модель извлечения и структурирования данных",
        prediction_cost=Decimal("25.00"),
        model_kind=TECHNICAL_DOCUMENT_MODEL_KIND,
        supported_document_types=[DocumentType.UNKNOWN.value],
        backend_name=DOCLING_BACKEND_NAME,
        backend_config={},
    )


if __name__ == "__main__":
    with SessionLocal.begin() as session:
        seed_initial_data(session)