from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

LOGGER = logging.getLogger("technical_document_ml_service.prediction_submission")

from technical_document_ml_service.domain.entities import DocumentExtractionTask
from technical_document_ml_service.domain.enums import TaskStatus
from technical_document_ml_service.messaging.contracts import PredictionTaskMessage
from technical_document_ml_service.messaging.rabbitmq import publish_prediction_task
from technical_document_ml_service.services.document_storage_service import (
    IncomingDocumentData,
    delete_stored_files,
    save_documents,
)
from technical_document_ml_service.services.mappers import (
    model_orm_to_domain,
    orm_to_domain_user,
)
from technical_document_ml_service.services.orm_queries import (
    get_model_orm_by_name_or_raise,
    get_user_orm_for_update,
)
from technical_document_ml_service.services.prediction_persistence import (
    build_domain_documents,
    ensure_prediction_can_start,
    mark_outbox_event_published,
    persist_outbox_event,
    persist_task,
    persist_uploaded_documents,
)


@dataclass(frozen=True, slots=True)
class PredictionSubmissionResult:
    """результат постановки задачи на асинхронную обработку"""

    task_id: UUID
    model_id: UUID
    model_name: str
    status: TaskStatus
    created_at: datetime
    callback_url: str | None


def submit_document_prediction(
    session: Session,
    *,
    user_id: UUID,
    model_name: str,
    target_schema: str,
    # TODO: рассмотреть батч-режим: принимать list[IncomingDocumentData] и создавать
    #       отдельную задачу на каждый документ (с единой транзакцией или по-одному)
    documents: list[IncomingDocumentData],
    callback_url: str | None = None,
) -> PredictionSubmissionResult:
    """
    поставить задачу обработки документа в очередь

    Phase 1 (атомарная): загрузить, проверить, сохранить файлы, зафиксировать
    задачу + outbox-событие в одной транзакции БД
    Phase 2 (best-effort): сразу опубликовать в RabbitMQ; если не удалось —
    OutboxRelay гарантирует доставку при следующем цикле опроса
    """
    saved_paths: list[str] = []

    try:
        user_orm = get_user_orm_for_update(session, user_id)
        model_orm = get_model_orm_by_name_or_raise(session, model_name)

        domain_user = orm_to_domain_user(user_orm)
        domain_model = model_orm_to_domain(model_orm)

        ensure_prediction_can_start(user=domain_user, model=domain_model)

        stored_documents = save_documents(owner_id=user_id, documents=documents)
        saved_paths = [doc.storage_path for doc in stored_documents]

        domain_documents = build_domain_documents(
            owner_id=user_id,
            stored_documents=stored_documents,
        )

        task = DocumentExtractionTask(
            user_id=user_id,
            model_id=domain_model.id,
            documents=domain_documents,
            target_schema=target_schema,
            callback_url=callback_url,
        )
        task.mark_as_queued()

        message = PredictionTaskMessage(
            task_id=task.id,
            user_id=user_id,
            model_name=domain_model.name,
            timestamp=datetime.now(UTC),
        )

        document_orms = persist_uploaded_documents(session, documents=domain_documents)
        persist_task(session, task=task, document_orms=document_orms)
        persist_outbox_event(session, task_id=task.id, message=message)

        session.commit()

    except Exception:
        if session.in_transaction():
            session.rollback()
        if saved_paths:
            delete_stored_files(saved_paths)
        raise

    # Phase 2: best-effort direct publish + mark delivered; relay только для crash-recovery
    try:
        publish_prediction_task(message)
        mark_outbox_event_published(session, task_id=task.id)
        session.commit()
    except Exception:
        if session.in_transaction():
            session.rollback()
        LOGGER.warning(
            "task_id=%s | прямая публикация не удалась; outbox relay доставит задачу позже",
            task.id,
        )

    return PredictionSubmissionResult(
        task_id=task.id,
        model_id=domain_model.id,
        model_name=domain_model.name,
        status=task.status,
        created_at=task.created_at,
        callback_url=callback_url,
    )