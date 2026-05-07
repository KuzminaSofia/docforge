from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile, status

from technical_document_ml_service.api.deps import CurrentUserDep, SessionDep
from technical_document_ml_service.api.schemas.predict import PredictAcceptedResponse
from technical_document_ml_service.core.config import app_settings
from technical_document_ml_service.domain.exceptions import FileSizeLimitError
from technical_document_ml_service.services.document_storage_service import (
    IncomingDocumentData,
)
from technical_document_ml_service.services.prediction_submission_service import (
    submit_document_prediction,
)


router = APIRouter(prefix="/predict", tags=["predict"])


@router.post(
    "",
    response_model=PredictAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def predict_documents(
    session: SessionDep,
    current_user: CurrentUserDep,
    model_name: Annotated[str, Form(min_length=1)],
    target_schema: Annotated[str, Form(min_length=1)],
    documents: Annotated[list[UploadFile], File(...)],
    callback_url: Annotated[str | None, Form()] = None,
) -> PredictAcceptedResponse:
    """принять документы и поставить задачу на ML-обработку в очередь"""
    max_file_bytes = app_settings.max_upload_file_size_mb * 1024 * 1024
    max_total_bytes = app_settings.max_task_total_size_mb * 1024 * 1024

    incoming_documents: list[IncomingDocumentData] = []
    total_bytes = 0

    try:
        for document in documents:
            content = document.file.read()
            file_size = len(content)

            if file_size > max_file_bytes:
                raise FileSizeLimitError(
                    f"Файл '{document.filename}' превышает допустимый размер "
                    f"{app_settings.max_upload_file_size_mb} МБ "
                    f"(получено {file_size / 1024 / 1024:.1f} МБ)."
                )

            total_bytes += file_size
            if total_bytes > max_total_bytes:
                raise FileSizeLimitError(
                    f"Суммарный размер файлов задачи превышает {app_settings.max_task_total_size_mb} МБ."
                )

            incoming_documents.append(
                IncomingDocumentData(
                    filename=document.filename or "document",
                    content_type=document.content_type,
                    content=content,
                )
            )
    finally:
        for document in documents:
            document.file.close()

    submission = submit_document_prediction(
        session,
        user_id=current_user.id,
        model_name=model_name,
        target_schema=target_schema,
        documents=incoming_documents,
        callback_url=callback_url or None,
    )

    return PredictAcceptedResponse.create(
        task_id=submission.task_id,
        model_id=submission.model_id,
        model_name=submission.model_name,
        created_at=submission.created_at,
        callback_url=submission.callback_url,
    )