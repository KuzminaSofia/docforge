from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, StreamingResponse

from technical_document_ml_service.api.deps import CurrentReadUserDep, ReadSessionDep, UserIdForSSEDep
from technical_document_ml_service.api.schemas.tasks import (
    TaskDetailsResponse,
    TaskListItemResponse,
    TaskListQueryParams,
    TaskResultResponse,
    TaskStatusResponse,
    TasksListResponse,
)
from technical_document_ml_service.db.session import SessionLocal
from technical_document_ml_service.domain.enums import TaskStatus
from technical_document_ml_service.domain.exceptions import AuthorizationError, NotFoundError
from technical_document_ml_service.services.artifact_service import get_task_artifact_file_path
from technical_document_ml_service.services.task_query_service import (
    get_user_task_details,
    get_user_task_result,
    get_user_tasks,
    get_user_task_status,
)

_TERMINAL_STATUSES = frozenset({TaskStatus.COMPLETED, TaskStatus.FAILED})
_SSE_POLL_INTERVAL_SECONDS = 5.0
_SSE_KEEPALIVE_EVERY_N_POLLS = 10


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


@router.get("/{task_id}/stream")
async def stream_task_status(
    task_id: UUID,
    request: Request,
    user_id: UserIdForSSEDep,
) -> StreamingResponse:
    """SSE-поток событий об изменении статуса задачи

    - ``event: status`` — очередной снапшот статуса (пока задача не завершена)
    - ``event: done``   — терминальный статус (completed / failed), стрим закрывается
    - ``event: stream_error`` — фатальная ошибка (задача не найдена, нет прав), стрим закрывается
    - ``: keep-alive``  — SSE-комментарий каждые ~15 с, предотвращает таймаут прокси
    """

    async def _event_generator() -> AsyncGenerator[str, None]:
        poll_count = 0

        while True:
            if await request.is_disconnected():
                break

            session = SessionLocal()
            try:
                item = await asyncio.to_thread(
                    get_user_task_status,
                    session,
                    user_id=user_id,
                    task_id=task_id,
                )
            except (NotFoundError, AuthorizationError) as exc:
                payload = json.dumps({"detail": str(exc)})
                yield f"event: stream_error\ndata: {payload}\n\n"
                break
            except Exception:
                break
            finally:
                session.rollback()
                session.close()

            is_terminal = item.status in _TERMINAL_STATUSES
            event_name = "done" if is_terminal else "status"
            event_data = TaskStatusResponse.from_item(item).model_dump_json()
            yield f"event: {event_name}\ndata: {event_data}\n\n"

            if is_terminal:
                break

            poll_count += 1
            if poll_count % _SSE_KEEPALIVE_EVERY_N_POLLS == 0:
                yield ": keep-alive\n\n"

            await asyncio.sleep(_SSE_POLL_INTERVAL_SECONDS)

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


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