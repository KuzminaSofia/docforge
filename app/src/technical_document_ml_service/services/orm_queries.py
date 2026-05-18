from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from technical_document_ml_service.db.models import MLModelORM, UserORM
from technical_document_ml_service.domain.exceptions import NotFoundError


def get_user_orm_or_raise(session: Session, user_id: UUID) -> UserORM:
    """загрузить ORM-пользователя по id или выбросить исключение"""
    user_orm = session.get(UserORM, user_id)
    if user_orm is None:
        raise NotFoundError("Пользователь не найден.")
    return user_orm


def get_user_orm_for_update(session: Session, user_id: UUID) -> UserORM:
    """загрузить ORM-пользователя с пессимистичной блокировкой строки (SELECT FOR UPDATE)
    используется там, где перед изменением баланса нужно исключить race condition:
    конкурентные транзакции будут ждать снятия блокировки
    """
    user_orm = session.scalar(
        select(UserORM).where(UserORM.id == user_id).with_for_update()
    )
    if user_orm is None:
        raise NotFoundError("Пользователь не найден.")
    return user_orm


def get_model_orm_by_name_or_raise(session: Session, model_name: str) -> MLModelORM:
    """загрузить ORM-модель по имени или выбросить исключение"""
    model_orm = session.scalar(
        select(MLModelORM).where(MLModelORM.name == model_name)
    )
    if model_orm is None:
        raise NotFoundError("ML-модель не найдена.")
    return model_orm