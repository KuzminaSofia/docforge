from __future__ import annotations

from sqlalchemy.orm import Session

from technical_document_ml_service.db.models import MLModelORM


def get_active_models(session: Session) -> list[dict]:
    """получить список активных ML-моделей"""
    models = (
        session.query(MLModelORM)
        .filter(MLModelORM.is_active.is_(True))
        .order_by(MLModelORM.name.asc())
        .all()
    )
    return [
        {
            "id": str(model.id),
            "name": model.name,
            "description": model.description,
            "prediction_cost": str(model.prediction_cost),
            "backend_name": model.backend_name,
            "model_kind": model.model_kind,
        }
        for model in models
    ]
