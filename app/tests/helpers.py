from __future__ import annotations

from technical_document_ml_service.db.session import SessionLocal
from technical_document_ml_service.services.document_storage_service import (
    IncomingDocumentData,
)
from technical_document_ml_service.services.prediction_submission_service import (
    submit_document_prediction,
)


def submit_test_task(api_user, api_model, target_schema: str = "passport_fields"):
    """поставить тестовую задачу в очередь и вернуть результат подачи"""
    with SessionLocal() as session:
        return submit_document_prediction(
            session,
            user_id=api_user.id,
            model_name=api_model.name,
            target_schema=target_schema,
            documents=[
                IncomingDocumentData(
                    filename="sample.pdf",
                    content_type="application/pdf",
                    content=b"%PDF-1.4 test content",
                )
            ],
        )
