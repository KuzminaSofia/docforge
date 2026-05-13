from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from technical_document_ml_service.api.deps import CurrentReadUserDep, ReadSessionDep
from technical_document_ml_service.api.schemas.tasks import (
    TaskDetailsResponse,
    TaskListItemResponse,
    TaskListQueryParams,
    TaskResultResponse,
    TaskStatusResponse,
    TasksListResponse,
)
from technical_document_ml_service.services.artifact_service import get_task_artifact_file_path
from technical_document_ml_service.services.task_query_service import (
    get_user_task_details,
    get_user_task_result,
    get_user_tasks,
    get_user_task_status,
)


router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=TasksListResponse)
def get_tasks(
    session: ReadSessionDep,
    current_user: CurrentReadUserDep,
    query: Annotated[TaskListQueryParams, Depends()],
) -> TasksListResponse:
    """получить список задач пользователя"""
    items = get_user_tasks(
        session,
        user_id=current_user.id,
        limit=query.limit,
        offset=query.offset,
        status=query.status,
    )

    return TasksListResponse(
        items=[
            TaskListItemResponse.from_item(item)
            for item in items
        ],
        limit=query.limit,
        offset=query.offset,
        status=query.status,
    )


@router.get("/{task_id}", response_model=TaskDetailsResponse)
def get_task_details(
    task_id: UUID,
    session: ReadSessionDep,
    current_user: CurrentReadUserDep,
) -> TaskDetailsResponse:
    """получить детальную информацию по задаче пользователя"""
    item = get_user_task_details(
        session,
        user_id=current_user.id,
        task_id=task_id,
    )
    return TaskDetailsResponse.from_item(item)


@router.get("/{task_id}/status", response_model=TaskStatusResponse)
def get_task_status(
    task_id: UUID,
    session: ReadSessionDep,
    current_user: CurrentReadUserDep,
) -> TaskStatusResponse:
    """получить только статус задачи — легкий endpoint для поллинга"""
    item = get_user_task_status(
        session,
        user_id=current_user.id,
        task_id=task_id,
    )
    return TaskStatusResponse.from_item(item)


@router.get("/{task_id}/result", response_model=TaskResultResponse)
def get_task_result(
    task_id: UUID,
    session: ReadSessionDep,
    current_user: CurrentReadUserDep,
) -> TaskResultResponse:
    """получить задачу пользователя вместе с результатом обработки"""
    bundle = get_user_task_result(
        session,
        user_id=current_user.id,
        task_id=task_id,
    )
    return TaskResultResponse.from_bundle(bundle)


@router.get("/{task_id}/artifacts/{artifact_name}")
def download_task_artifact(
    task_id: UUID,
    artifact_name: str,
    session: ReadSessionDep,
    current_user: CurrentReadUserDep,
) -> FileResponse:
    """скачать артефакт задачи"""
    bundle = get_user_task_result(session, user_id=current_user.id, task_id=task_id)
    descriptor = get_task_artifact_file_path(bundle, artifact_name)

    return FileResponse(
        str(descriptor.file_path),
        filename=artifact_name,
        media_type=descriptor.mime_type or "application/octet-stream",
    )