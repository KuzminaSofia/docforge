from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile, status

from technical_document_ml_service.api.deps import CurrentReadUserDep, CurrentUserDep, ReadSessionDep, SessionDep
from technical_document_ml_service.api.schemas.predict import MLModelResponse, PredictAcceptedResponse
from technical_document_ml_service.api.upload import collect_uploaded_documents
from technical_document_ml_service.services.model_query_service import get_active_models
from technical_document_ml_service.services.prediction_submission_service import (
    submit_document_prediction,
)


router = APIRouter(prefix="/predict", tags=["predict"])


@router.get("/models", response_model=list[MLModelResponse])
def get_prediction_models(
    session: ReadSessionDep,
    current_user: CurrentReadUserDep,
) -> list[MLModelResponse]:
    """получить список активных ML-моделей, доступных для обработки"""
    models = get_active_models(session)
    return [MLModelResponse(**m) for m in models]


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
    incoming_documents = collect_uploaded_documents(documents)

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