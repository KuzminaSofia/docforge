from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from technical_document_ml_service.db.models import UserORM
from technical_document_ml_service.domain.entities import User
from technical_document_ml_service.domain.enums import UserRole
from technical_document_ml_service.domain.exceptions import UserAlreadyExistsError
from technical_document_ml_service.services.mappers import orm_to_domain_user


def create_user(
    session: Session,
    *,
    email: str,
    password_hash: str,
    role: UserRole = UserRole.USER,
    balance_credits: Decimal = Decimal("0"),
    is_active: bool = True,
) -> User:
    """
    создать пользователя и сохранить его в БД
    raise UserAlreadyExistsError, если пользователь с таким email уже существует
    """
    existing_user = session.scalar(
        select(UserORM).where(UserORM.email == email)
    )
    if existing_user is not None:
        raise UserAlreadyExistsError("Пользователь с таким email уже существует.")

    user_orm = UserORM(
        email=email,
        password_hash=password_hash,
        role=role.value,
        balance_credits=balance_credits,
        is_active=is_active,
    )
    session.add(user_orm)
    session.flush()

    return orm_to_domain_user(user_orm)


def get_user_by_id(session: Session, user_id: UUID) -> User | None:
    """загрузить пользователя из БД по идентификатору"""
    user_orm = session.get(UserORM, user_id)
    if user_orm is None:
        return None
    return orm_to_domain_user(user_orm)


def get_user_by_email(session: Session, email: str) -> User | None:
    """загрузить пользователя из БД по email"""
    user_orm = session.scalar(
        select(UserORM).where(UserORM.email == email)
    )
    if user_orm is None:
        return None
    return orm_to_domain_user(user_orm)