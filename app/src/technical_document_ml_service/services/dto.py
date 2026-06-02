from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from technical_document_ml_service.domain.enums import (
    DocumentType,
    TaskStatus,
    TransactionType,
)


@dataclass(frozen=True, slots=True)
class ModelItem:
    """активная ML-модель, доступная для обработки документов"""

    id: UUID
    name: str
    description: str
    prediction_cost: Decimal
    backend_name: str
    model_kind: str


@dataclass(frozen=True, slots=True)
class TransactionHistoryItem:
    """элемент истории транзакций пользователя"""

    id: UUID
    user_id: UUID
    task_id: UUID | None
    transaction_type: TransactionType
    amount: Decimal
    created_at: datetime


@dataclass(frozen=True, slots=True)
class PredictionHistoryItem:
    """элемент истории ML-запросов / предсказаний пользователя"""

    id: UUID
    user_id: UUID
    task_id: UUID | None
    model_id: UUID
    result_id: UUID | None
    status: TaskStatus
    spent_credits: Decimal
    created_at: datetime
    completed_at: datetime | None


@dataclass(frozen=True, slots=True)
class TaskDocumentItem:
    """документ, прикрепленный к задаче"""

    id: UUID
    owner_id: UUID
    original_filename: str
    storage_path: str
    mime_type: str
    document_type: DocumentType
    size_bytes: int
    uploaded_at: datetime


@dataclass(frozen=True, slots=True)
class TaskListItem:
    """краткая информация по задаче для спискового отображения"""

    id: UUID
    model_id: UUID
    model_name: str
    backend_name: str
    target_schema: str | None
    status: TaskStatus
    error_message: str | None
    spent_credits: Decimal
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    result_id: UUID | None
    documents_count: int
    first_document_name: str | None


@dataclass(frozen=True, slots=True)
class TaskDetailsItem:
    """детальная информация по задаче"""

    id: UUID
    user_id: UUID
    model_id: UUID
    model_name: str
    backend_name: str
    target_schema: str | None
    status: TaskStatus
    error_message: str | None
    spent_credits: Decimal
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    result_id: UUID | None
    documents: list[TaskDocumentItem]


@dataclass(frozen=True, slots=True)
class ValidationIssueItem:
    """ошибка или замечание, найденное при валидации входных данных"""

    field_name: str
    message: str
    raw_value: Any | None


@dataclass(frozen=True, slots=True)
class ResultArtifactItem:
    """описание артефакта результата обработки"""

    name: str
    path: str
    kind: str
    mime_type: str | None
    description: str | None
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class PredictionResultDetailsItem:
    """детальная информация по результату обработки"""

    id: UUID
    task_id: UUID
    extracted_data: dict[str, Any]
    validation_issues: list[ValidationIssueItem]
    output_path: str | None
    artifacts_dir: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class TaskResultBundle:
    """объединенный ответ по задаче и ее результату"""

    task: TaskDetailsItem
    result: PredictionResultDetailsItem | None
    artifacts: list[ResultArtifactItem]