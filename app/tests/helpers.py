from __future__ import annotations

import os
import tempfile
from pathlib import Path

from technical_document_ml_service.core.config import app_settings
from technical_document_ml_service.db.session import SessionLocal
from technical_document_ml_service.services.document_storage_service import (
    IncomingDocumentData,
)
from technical_document_ml_service.services.prediction_submission_service import (
    submit_document_prediction,
)

_DEFAULT_PDF_CONTENT = b"%PDF-1.4 test content"


def make_incoming_document(
    *,
    filename: str = "sample.pdf",
    content_type: str = "application/pdf",
    content: bytes = _DEFAULT_PDF_CONTENT,
) -> IncomingDocumentData:
    """создать IncomingDocumentData из bytes-контента для тестов"""
    uploads_root = Path(app_settings.uploads_dir)
    uploads_root.mkdir(parents=True, exist_ok=True)
    fd, tmp_str = tempfile.mkstemp(dir=uploads_root)
    tmp_path = Path(tmp_str)
    os.write(fd, content)
    os.close(fd)
    return IncomingDocumentData(
        filename=filename,
        content_type=content_type,
        temp_path=tmp_path,
        size_bytes=len(content),
    )


def submit_test_task(api_user, api_model, target_schema: str = "passport_fields"):
    """поставить тестовую задачу в очередь и вернуть результат подачи"""
    with SessionLocal() as session:
        return submit_document_prediction(
            session,
            user_id=api_user.id,
            model_name=api_model.name,
            target_schema=target_schema,
            documents=[make_incoming_document()],
        )
