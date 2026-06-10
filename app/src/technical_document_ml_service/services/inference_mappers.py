from __future__ import annotations

from typing import Any
from uuid import UUID

from technical_document_ml_service.core.config import app_settings
from technical_document_ml_service.domain.entities import (
    DocumentExtractionTask,
    PredictionResult,
)
from technical_document_ml_service.inference.contracts import (
    BackendDocument,
    BackendRequest,
    BackendResult,
)


def _build_backend_document(document) -> BackendDocument:
    """преобразовать доменный документ в backend DTO"""
    return BackendDocument(
        document_id=document.id,
        owner_id=document.owner_id,
        original_filename=document.original_filename,
        storage_path=document.storage_path,
        mime_type=document.mime_type,
        document_type=document.document_type.value,
        size_bytes=document.size_bytes,
    )


def build_backend_request(
    *,
    task: DocumentExtractionTask,
    model_id: UUID,
    model_name: str,
    model_kind: str,
    backend_name: str,
    backend_config: dict[str, Any],
) -> BackendRequest:
    """собрать унифицированный backend request для обработки задачи"""
    valid_documents = task.get_valid_documents()
    # S3-префикс ключей артефактов задачи (а не путь ФС); owner_id дает симметрию с
    # uploads/<owner_id>/... и позволяет per-user lifecycle/cleanup без похода в БД
    artifacts_dir = f"{app_settings.artifacts_dir}/{task.user_id}/{task.id}"

    return BackendRequest(
        task_id=task.id,
        user_id=task.user_id,
        model_id=model_id,
        model_name=model_name,
        model_kind=model_kind,
        backend_name=backend_name,
        backend_config=dict(backend_config or {}),
        target_schema=task.target_schema,
        documents=[_build_backend_document(document) for document in valid_documents],
        artifacts_dir=artifacts_dir,
        context={
            "task_status": task.status.value,
            "documents_count": len(task.documents),
            "valid_documents_count": len(valid_documents),
        },
    )


def build_prediction_result_from_backend_result(
    *,
    task_id: UUID,
    backend_result: BackendResult,
    artifacts_dir: str | None,
) -> PredictionResult:
    """преобразовать backend result в доменный результат предсказания"""
    manifest = backend_result.build_artifacts_manifest()

    effective_artifacts_dir = artifacts_dir
    if not manifest and backend_result.output_path is None:
        effective_artifacts_dir = None

    return PredictionResult(
        task_id=task_id,
        extracted_data=backend_result.extracted_data,
        validation_issues=[],
        output_path=backend_result.output_path,
        artifacts_dir=effective_artifacts_dir,
        artifacts_manifest=manifest,
    )