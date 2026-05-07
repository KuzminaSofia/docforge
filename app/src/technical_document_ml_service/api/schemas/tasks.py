from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from technical_document_ml_service.api.schemas.predict import ValidationIssueResponse
from technical_document_ml_service.domain.enums import DocumentType, TaskStatus
from technical_document_ml_service.services.dto import (
    PredictionResultDetailsItem,
    ResultArtifactItem,
    TaskDetailsItem,
    TaskDocumentItem,
    TaskListItem,
    TaskResultBundle,
)


class TaskListQueryParams(BaseModel):
    """параметры пагинации и фильтрации списка задач"""

    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    status: TaskStatus | None = Field(default=None)


class TaskDocumentResponse(BaseModel):
    """документ, прикрепленный к задаче"""

    id: UUID
    owner_id: UUID
    original_filename: str
    storage_path: str
    mime_type: str
    document_type: DocumentType
    size_bytes: int
    uploaded_at: datetime

    @classmethod
    def from_item(cls, item: TaskDocumentItem) -> "TaskDocumentResponse":
        return cls(
            id=item.id,
            owner_id=item.owner_id,
            original_filename=item.original_filename,
            storage_path=item.storage_path,
            mime_type=item.mime_type,
            document_type=item.document_type,
            size_bytes=item.size_bytes,
            uploaded_at=item.uploaded_at,
        )


class TaskListItemResponse(BaseModel):
    """краткая информация по задаче для списка"""

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

    @classmethod
    def from_item(cls, item: TaskListItem) -> "TaskListItemResponse":
        return cls(
            id=item.id,
            model_id=item.model_id,
            model_name=item.model_name,
            backend_name=item.backend_name,
            target_schema=item.target_schema,
            status=item.status,
            error_message=item.error_message,
            spent_credits=item.spent_credits,
            created_at=item.created_at,
            started_at=item.started_at,
            completed_at=item.completed_at,
            result_id=item.result_id,
            documents_count=item.documents_count,
            first_document_name=item.first_document_name,
        )


class TasksListResponse(BaseModel):
    """ответ со списком задач пользователя"""

    items: list[TaskListItemResponse]
    limit: int
    offset: int
    status: TaskStatus | None


class TaskDetailsResponse(BaseModel):
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
    documents: list[TaskDocumentResponse]

    @classmethod
    def from_item(cls, item: TaskDetailsItem) -> "TaskDetailsResponse":
        return cls(
            id=item.id,
            user_id=item.user_id,
            model_id=item.model_id,
            model_name=item.model_name,
            backend_name=item.backend_name,
            target_schema=item.target_schema,
            status=item.status,
            error_message=item.error_message,
            spent_credits=item.spent_credits,
            created_at=item.created_at,
            started_at=item.started_at,
            completed_at=item.completed_at,
            result_id=item.result_id,
            documents=[
                TaskDocumentResponse.from_item(document)
                for document in item.documents
            ],
        )


class ResultArtifactResponse(BaseModel):
    """артефакт результата обработки"""

    name: str
    path: str
    kind: str
    mime_type: str | None
    description: str | None
    metadata: dict[str, Any]

    @classmethod
    def from_item(cls, item: ResultArtifactItem) -> "ResultArtifactResponse":
        return cls(
            name=item.name,
            path=item.path,
            kind=item.kind,
            mime_type=item.mime_type,
            description=item.description,
            metadata=item.metadata,
        )


class PredictionResultDetailsResponse(BaseModel):
    """детальный результат обработки"""

    id: UUID
    task_id: UUID
    extracted_data: dict[str, Any]
    validation_issues: list[ValidationIssueResponse]
    output_path: str | None
    artifacts_dir: str | None
    created_at: datetime

    @classmethod
    def from_item(
        cls,
        item: PredictionResultDetailsItem,
    ) -> "PredictionResultDetailsResponse":
        return cls(
            id=item.id,
            task_id=item.task_id,
            extracted_data=item.extracted_data,
            validation_issues=[
                ValidationIssueResponse.from_item(issue)
                for issue in item.validation_issues
            ],
            output_path=item.output_path,
            artifacts_dir=item.artifacts_dir,
            created_at=item.created_at,
        )


class TaskResultResponse(BaseModel):
    """объединенный ответ по задаче и результату"""

    task: TaskDetailsResponse
    result: PredictionResultDetailsResponse | None
    artifacts: list[ResultArtifactResponse]
    has_result: bool

    @classmethod
    def from_bundle(cls, bundle: TaskResultBundle) -> "TaskResultResponse":
        return cls(
            task=TaskDetailsResponse.from_item(bundle.task),
            result=(
                PredictionResultDetailsResponse.from_item(bundle.result)
                if bundle.result is not None
                else None
            ),
            artifacts=[
                ResultArtifactResponse.from_item(artifact)
                for artifact in bundle.artifacts
            ],
            has_result=bundle.result is not None,
        )