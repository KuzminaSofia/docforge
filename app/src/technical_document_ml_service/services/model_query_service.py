from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from technical_document_ml_service.db.models import MLModelORM
from technical_document_ml_service.services.dto import ModelItem


def get_active_models(session: Session) -> list[ModelItem]:
    """получить список активных ML-моделей"""
    models = session.scalars(
        select(MLModelORM)
        .where(MLModelORM.is_active.is_(True))
        .order_by(MLModelORM.name.asc())
    ).all()

    return [
        ModelItem(
            id=model.id,
            name=model.name,
            description=model.description,
            prediction_cost=model.prediction_cost,
            backend_name=model.backend_name,
            model_kind=model.model_kind,
        )
        for model in models
    ]
