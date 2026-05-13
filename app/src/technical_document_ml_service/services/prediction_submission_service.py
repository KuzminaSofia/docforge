from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

LOGGER = logging.getLogger("technical_document_ml_service.prediction_submission")

from technical_document_ml_service.db.models import MLTaskORM
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
    sync_task_orm_from_domain,
)
from technical_document_ml_service.services.orm_queries import (
    get_model_orm_by_name_or_raise,
    get_user_orm_or_raise,
)
from technical_document_ml_service.services.prediction_persistence import (
    build_domain_documents,
    ensure_prediction_can_start,
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
    documents: list[IncomingDocumentData],
    callback_url: str | None = None,
) -> PredictionSubmissionResult:
    """
    поставить задачу обработки документов в очередь

    Сценарий:
    1. загрузить пользователя и модель;
    2. выполнить ранние проверки;
    3. сохранить документы в storage;
    4. создать задачу;
    5. сразу перевести ее в статус queued;
    6. сохранить задачу и документы в БД;
    7. зафиксировать транзакцию коммитом;
    8. опубликовать сообщение в RabbitMQ
    """
    saved_paths: list[str] = []
    task: DocumentExtractionTask | None = None
    task_persisted = False

    try:
        user_orm = get_user_orm_or_raise(session, user_id)
        model_orm = get_model_orm_by_name_or_raise(session, model_name)

        domain_user = orm_to_domain_user(user_orm)
        domain_model = model_orm_to_domain(model_orm)

        ensure_prediction_can_start(
            user=domain_user,
            model=domain_model,
        )

        stored_documents = save_documents(
            owner_id=user_id,
            documents=documents,
        )
        saved_paths = [document.storage_path for document in stored_documents]

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

        document_orms = persist_uploaded_documents(
            session,
            documents=domain_documents,
        )
        persist_task(
            session,
            task=task,
            document_orms=document_orms,
        )

        session.commit()
        task_persisted = True

        message = PredictionTaskMessage(
            task_id=task.id,
            user_id=user_id,
            model_name=domain_model.name,
            timestamp=datetime.now(UTC),
        )
        publish_prediction_task(message)

        return PredictionSubmissionResult(
            task_id=task.id,
            model_id=domain_model.id,
            model_name=domain_model.name,
            status=task.status,
            created_at=task.created_at,
            callback_url=callback_url,
        )

    except Exception:
        if session.in_transaction():
            session.rollback()

        if task is None or not task_persisted:
            # Задача не попала в БД — просто удаляем файлы и пробрасываем исключение
            if saved_paths:
                delete_stored_files(saved_paths)
            raise

        # Задача уже зафиксирована в БД, но публикация в RabbitMQ провалилась.
        # Отмечаем задачу как FAILED чтобы пользователь увидел ошибку.
        task.fail("Не удалось поставить задачу в очередь на обработку.")

        try:
            persisted_task_orm = session.get(MLTaskORM, task.id)
            if persisted_task_orm is not None:
                sync_task_orm_from_domain(persisted_task_orm, task)
                session.commit()
        except Exception:
            LOGGER.exception(
                "task_id=%s | Не удалось пометить задачу как FAILED после сбоя публикации",
                task.id,
            )

        raise