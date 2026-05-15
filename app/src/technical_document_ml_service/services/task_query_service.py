from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from technical_document_ml_service.db.models import MLTaskORM, PredictionResultORM
from technical_document_ml_service.domain.enums import TaskStatus
from technical_document_ml_service.domain.exceptions import AuthorizationError, NotFoundError
from technical_document_ml_service.services.dto import (
    PredictionResultDetailsItem,
    ResultArtifactItem,
    TaskDetailsItem,
    TaskDocumentItem,
    TaskListItem,
    TaskResultBundle,
    ValidationIssueItem,
)
from technical_document_ml_service.services.mappers import parse_document_type


def _load_task_with_related(
    session: Session,
    *,
    task_id: UUID,
) -> MLTaskORM | None:
    """загрузить задачу со связанными сущностями"""
    statement = (
        select(MLTaskORM)
        .where(MLTaskORM.id == task_id)
        .options(
            selectinload(MLTaskORM.model),
            selectinload(MLTaskORM.documents),
            selectinload(MLTaskORM.prediction_result),
        )
    )
    return session.execute(statement).scalar_one_or_none()


def _ensure_task_owner(
    *,
    task: MLTaskORM,
    user_id: UUID,
) -> None:
    """проверить, что задача принадлежит пользователю"""
    if task.user_id != user_id:
        raise AuthorizationError("Недостаточно прав для доступа к этой задаче.")


def _build_task_document_item(document) -> TaskDocumentItem:
    """собрать DTO документа задачи"""
    return TaskDocumentItem(
        id=document.id,
        owner_id=document.owner_id,
        original_filename=document.filename,
        storage_path=document.storage_path,
        mime_type=document.mime_type,
        document_type=parse_document_type(document.document_type),
        size_bytes=document.file_size,
        uploaded_at=document.uploaded_at,
    )


def _build_task_list_item(task: MLTaskORM) -> TaskListItem:
    """собрать краткий DTO задачи для списка"""
    result_id = task.prediction_result.id if task.prediction_result is not None else None
    first_document_name = task.documents[0].filename if task.documents else None

    return TaskListItem(
        id=task.id,
        model_id=task.model_id,
        model_name=task.model.name,
        backend_name=task.model.backend_name,
        target_schema=task.target_schema,
        status=TaskStatus(task.status),
        error_message=task.error_message,
        spent_credits=task.spent_credits,
        created_at=task.created_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
        result_id=result_id,
        documents_count=len(task.documents),
        first_document_name=first_document_name,
    )


def _build_task_details_item(task: MLTaskORM) -> TaskDetailsItem:
    """собрать DTO задачи"""
    result_id = task.prediction_result.id if task.prediction_result is not None else None

    return TaskDetailsItem(
        id=task.id,
        user_id=task.user_id,
        model_id=task.model_id,
        model_name=task.model.name,
        backend_name=task.model.backend_name,
        target_schema=task.target_schema,
        status=TaskStatus(task.status),
        error_message=task.error_message,
        spent_credits=task.spent_credits,
        created_at=task.created_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
        result_id=result_id,
        documents=[
            _build_task_document_item(document)
            for document in task.documents
        ],
    )


def _build_validation_issues(items: list[dict]) -> list[ValidationIssueItem]:
    """десериализовать validation issues из JSONB в DTO"""
    return [
        ValidationIssueItem(
            field_name=str(item.get("field_name", "")),
            message=str(item.get("message", "")),
            raw_value=item.get("raw_value"),
        )
        for item in items
    ]


def _build_artifact_items(result_orm: PredictionResultORM) -> list[ResultArtifactItem]:
    """преобразовать manifest артефактов в DTO"""
    artifacts: list[ResultArtifactItem] = []

    for artifact in result_orm.artifacts_manifest:
        artifacts.append(
            ResultArtifactItem(
                name=str(artifact.get("name", "")),
                path=str(artifact.get("path", "")),
                kind=str(artifact.get("kind", "")),
                mime_type=artifact.get("mime_type"),
                description=artifact.get("description"),
                metadata=dict(artifact.get("metadata") or {}),
            )
        )

    return artifacts


def _build_result_details_item(
    result_orm: PredictionResultORM,
) -> PredictionResultDetailsItem:
    """собрать DTO результата обработки"""
    return PredictionResultDetailsItem(
        id=result_orm.id,
        task_id=result_orm.task_id,
        extracted_data=dict(result_orm.extracted_data or {}),
        validation_issues=_build_validation_issues(result_orm.validation_issues or []),
        output_path=result_orm.output_file_path,
        artifacts_dir=result_orm.artifacts_dir,
        created_at=result_orm.created_at,
    )


def get_user_tasks(
    session: Session,
    *,
    user_id: UUID,
    limit: int = 50,
    offset: int = 0,
    status: TaskStatus | None = None,
) -> list[TaskListItem]:
    """получить список задач пользователя в обратном хронологическом порядке"""
    statement = (
        select(MLTaskORM)
        .where(MLTaskORM.user_id == user_id)
    )

    if status is not None:
        statement = statement.where(MLTaskORM.status == status.value)

    statement = (
        statement
        .options(
            selectinload(MLTaskORM.model),
            selectinload(MLTaskORM.documents),
            selectinload(MLTaskORM.prediction_result),
        )
        .order_by(MLTaskORM.created_at.desc())
        .offset(offset)
        .limit(limit)
    )

    tasks = session.execute(statement).scalars().all()
    return [_build_task_list_item(task) for task in tasks]


def get_user_task_details(
    session: Session,
    *,
    user_id: UUID,
    task_id: UUID,
) -> TaskDetailsItem:
    """получить детальную информацию по задаче пользователя"""
    task = _load_task_with_related(session, task_id=task_id)
    if task is None:
        raise NotFoundError("ML-задача не найдена.")

    _ensure_task_owner(task=task, user_id=user_id)
    return _build_task_details_item(task)


def get_user_task_status(
    session: Session,
    *,
    user_id: UUID,
    task_id: UUID,
) -> TaskDetailsItem:
    """получить только основные поля задачи без тяжелых связей — для поллинга статуса"""
    statement = (
        select(MLTaskORM)
        .where(MLTaskORM.id == task_id)
        .options(
            selectinload(MLTaskORM.model),
        )
    )
    task = session.execute(statement).scalar_one_or_none()
    if task is None:
        raise NotFoundError("ML-задача не найдена.")

    _ensure_task_owner(task=task, user_id=user_id)

    return TaskDetailsItem(
        id=task.id,
        user_id=task.user_id,
        model_id=task.model_id,
        model_name=task.model.name,
        backend_name=task.model.backend_name,
        target_schema=task.target_schema,
        status=TaskStatus(task.status),
        error_message=task.error_message,
        spent_credits=task.spent_credits,
        created_at=task.created_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
        result_id=None,
        documents=[],
    )


def get_user_task_result(
    session: Session,
    *,
    user_id: UUID,
    task_id: UUID,
) -> TaskResultBundle:
    """получить задачу пользователя вместе с результатом обработки"""
    task = _load_task_with_related(session, task_id=task_id)
    if task is None:
        raise NotFoundError("ML-задача не найдена.")

    _ensure_task_owner(task=task, user_id=user_id)

    task_item = _build_task_details_item(task)

    if task.prediction_result is None:
        return TaskResultBundle(
            task=task_item,
            result=None,
            artifacts=[],
        )

    result_item = _build_result_details_item(task.prediction_result)
    artifacts = _build_artifact_items(task.prediction_result)

    return TaskResultBundle(
        task=task_item,
        result=result_item,
        artifacts=artifacts,
    )