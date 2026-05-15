from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from technical_document_ml_service.domain.enums import TaskStatus
from technical_document_ml_service.services.dto import ValidationIssueItem


class MLModelResponse(BaseModel):
    """активная ML-модель, доступная для обработки документов"""

    id: str
    name: str
    description: str
    prediction_cost: Decimal
    backend_name: str
    model_kind: str


class ValidationIssueResponse(BaseModel):
    """ошибка или замечание, найденное при валидации входных данных"""

    field_name: str
    message: str
    raw_value: Any | None

    @classmethod
    def from_item(cls, item: ValidationIssueItem) -> "ValidationIssueResponse":
        return cls(
            field_name=item.field_name,
            message=item.message,
            raw_value=item.raw_value,
        )


class PredictAcceptedResponse(BaseModel):
    """
    ответ API при асинхронной постановке задачи:
    запрос принят, задача сохранена и отправлена в очередь
    """

    task_id: UUID
    model_id: UUID
    model_name: str
    status: TaskStatus
    created_at: datetime
    callback_url: str | None
    message: str

    @classmethod
    def create(
        cls,
        *,
        task_id: UUID,
        model_id: UUID,
        model_name: str,
        created_at: datetime,
        callback_url: str | None = None,
        message: str = "Задача принята и поставлена в очередь на обработку.",
    ) -> "PredictAcceptedResponse":
        return cls(
            task_id=task_id,
            model_id=model_id,
            model_name=model_name,
            status=TaskStatus.QUEUED,
            created_at=created_at,
            callback_url=callback_url,
            message=message,
        )
