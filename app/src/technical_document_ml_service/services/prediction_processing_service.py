from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from technical_document_ml_service.db.models import MLTaskORM
from technical_document_ml_service.domain.entities import (
    DebitTransaction,
    DocumentExtractionTask,
)
from technical_document_ml_service.domain.enums import TaskStatus
from technical_document_ml_service.domain.exceptions import (
    InsufficientBalanceError,
    ModelUnavailableError,
    NotFoundError,
    TaskExecutionError,
)
from technical_document_ml_service.inference.selector import select_prediction_backend
from technical_document_ml_service.services.billing_service import record_transaction
from technical_document_ml_service.services.history_service import (
    create_history_record_from_task,
)
from technical_document_ml_service.services.inference_mappers import (
    build_backend_request,
    build_prediction_result_from_backend_result,
)
from technical_document_ml_service.services.mappers import (
    model_orm_to_domain,
    orm_to_domain_user,
    sync_task_orm_from_domain,
    sync_user_orm_from_domain,
    task_orm_to_domain,
)
from technical_document_ml_service.services.prediction_persistence import (
    persist_prediction_result,
)
from technical_document_ml_service.services.webhook_service import send_task_webhook


LOGGER = logging.getLogger("technical_document_ml_service.prediction_processing")


@dataclass(frozen=True, slots=True)
class PredictionProcessingResult:
    """результат обработки задачи воркером"""

    task_id: UUID
    status: TaskStatus
    result_id: UUID | None
    created_at: datetime
    completed_at: datetime | None
    spent_credits: Decimal
    was_processed: bool
    message: str


def _load_task_for_processing(session: Session, task_id: UUID) -> MLTaskORM | None:
    """загрузить задачу и все необходимые связи с блокировкой строки"""
    statement = (
        select(MLTaskORM)
        .where(MLTaskORM.id == task_id)
        .options(
            selectinload(MLTaskORM.user),
            selectinload(MLTaskORM.model),
            selectinload(MLTaskORM.documents),
            selectinload(MLTaskORM.prediction_result),
        )
        .with_for_update()
    )

    return session.execute(statement).scalar_one_or_none()


def _build_skipped_result(
    task_orm: MLTaskORM,
    *,
    message: str,
) -> PredictionProcessingResult:
    """сформировать результат, если повторная обработка не требуется"""
    result_id = None
    if task_orm.prediction_result is not None:
        result_id = task_orm.prediction_result.id

    return PredictionProcessingResult(
        task_id=task_orm.id,
        status=TaskStatus(task_orm.status),
        result_id=result_id,
        created_at=task_orm.created_at,
        completed_at=task_orm.completed_at,
        spent_credits=task_orm.spent_credits,
        was_processed=False,
        message=message,
    )


def _mark_task_as_failed(
    session: Session,
    *,
    task_id: UUID,
    error_message: str,
) -> None:
    """зафиксировать ошибку обработки задачи в БД"""
    persisted_task_orm = _load_task_for_processing(session, task_id)
    if persisted_task_orm is None:
        return

    domain_task = task_orm_to_domain(persisted_task_orm)
    domain_task.fail(error_message)
    sync_task_orm_from_domain(persisted_task_orm, domain_task)
    session.commit()


def _ensure_processing_can_start(
    *,
    domain_task: DocumentExtractionTask,
    domain_user,
    domain_model,
) -> None:
    """проверить доменные предусловия выполнения задачи"""
    if domain_user.id != domain_task.user_id:
        raise TaskExecutionError("Задача не принадлежит переданному пользователю.")

    if domain_model.id != domain_task.model_id:
        raise TaskExecutionError("Задача не соответствует переданной модели.")

    if not domain_model.is_active:
        raise ModelUnavailableError("Выбранная ML-модель недоступна.")

    if not domain_user.can_afford(domain_model.prediction_cost):
        raise InsufficientBalanceError("Недостаточно средств для выполнения задачи.")


def process_document_prediction_task(
    session: Session,
    *,
    task_id: UUID,
) -> PredictionProcessingResult:
    """
    обработать ранее поставленную в очередь задачу

    Сценарий:
    1. загрузить задачу и связанные данные;
    2. проверить, нужно ли ее реально обрабатывать;
    3. восстановить доменные объекты;
    4. провалидировать входные данные и выбрать backend;
    5. выполнить backend;
    6. сохранить результат, транзакцию и историю.
    """
    task_orm = _load_task_for_processing(session, task_id)
    if task_orm is None:
        raise NotFoundError(f"Задача с id={task_id} не найдена.")

    # извлекаем infrastructure-поля ORM до перехода на доменные объекты
    callback_url: str | None = task_orm.callback_url
    model_name_for_webhook: str = task_orm.model.name
    model_backend_name: str = task_orm.model.backend_name
    model_kind: str = task_orm.model.model_kind
    model_backend_config: dict = dict(task_orm.model.backend_config or {})

    current_status = TaskStatus(task_orm.status)

    if current_status == TaskStatus.COMPLETED:
        return _build_skipped_result(
            task_orm,
            message="Задача уже была успешно обработана ранее.",
        )

    if current_status == TaskStatus.PROCESSING:
        return _build_skipped_result(
            task_orm,
            message="Задача уже находится в обработке.",
        )

    if current_status == TaskStatus.VALIDATING:
        return _build_skipped_result(
            task_orm,
            message="Задача уже находится на этапе валидации.",
        )

    if current_status == TaskStatus.FAILED:
        return _build_skipped_result(
            task_orm,
            message="Задача ранее завершилась с ошибкой.",
        )

    if current_status != TaskStatus.QUEUED:
        return _build_skipped_result(
            task_orm,
            message=(
                f"Задача в статусе {current_status.value} "
                "не может быть обработана воркером."
            ),
        )

    domain_user = orm_to_domain_user(task_orm.user)
    domain_model = model_orm_to_domain(task_orm.model)
    domain_task = task_orm_to_domain(task_orm)

    try:
        _ensure_processing_can_start(
            domain_task=domain_task,
            domain_user=domain_user,
            domain_model=domain_model,
        )

        domain_task.mark_as_validating()
        validation_issues = domain_task.validate_input()

        if not domain_task.get_valid_documents():
            raise TaskExecutionError("Нет валидных документов для обработки.")

        backend_request = build_backend_request(
            task=domain_task,
            model_id=domain_model.id,
            model_name=domain_model.name,
            model_kind=model_kind,
            backend_name=model_backend_name,
            backend_config=model_backend_config,
        )

        backend_selection = select_prediction_backend(
            requested_backend_name=model_backend_name,
            backend_config=model_backend_config,
        )

        domain_task.mark_as_processing()

        backend_result = backend_selection.backend.process(backend_request)

        for warning in backend_result.warnings:
            LOGGER.warning(
                "task_id=%s | backend=%s | warning=%s",
                domain_task.id,
                backend_selection.resolved_backend_name,
                warning,
            )

        result = build_prediction_result_from_backend_result(
            task_id=domain_task.id,
            backend_result=backend_result,
            artifacts_dir=backend_request.artifacts_dir,
        )
        result.add_issues(validation_issues)

        debit_transaction = DebitTransaction(
            user_id=domain_user.id,
            amount=domain_model.prediction_cost,
            task_id=domain_task.id,
        )
        debit_transaction.apply(domain_user)

        domain_task.mark_as_completed(
            result_id=result.id,
            spent_credits=domain_model.prediction_cost,
        )

        sync_user_orm_from_domain(task_orm.user, domain_user)
        sync_task_orm_from_domain(task_orm, domain_task)

        persist_prediction_result(
            session,
            task_id=domain_task.id,
            result=result,
        )
        record_transaction(
            session,
            transaction=debit_transaction,
        )
        create_history_record_from_task(session, domain_task)

        session.commit()

        if callback_url:
            send_task_webhook(
                url=callback_url,
                task_id=domain_task.id,
                status=domain_task.status,
                model_name=model_name_for_webhook,
                result_id=domain_task.result_id,
                spent_credits=domain_task.spent_credits,
                completed_at=domain_task.finished_at,
                error_message=None,
            )

        return PredictionProcessingResult(
            task_id=domain_task.id,
            status=domain_task.status,
            result_id=domain_task.result_id,
            created_at=domain_task.created_at,
            completed_at=domain_task.finished_at,
            spent_credits=domain_task.spent_credits,
            was_processed=True,
            message=(
                f"Задача успешно обработана через backend "
                f"'{backend_selection.resolved_backend_name}'."
            ),
        )

    except Exception as exc:
        if session.in_transaction():
            session.rollback()

        error_text = str(exc)
        _mark_task_as_failed(
            session,
            task_id=task_id,
            error_message=error_text,
        )

        if callback_url:
            send_task_webhook(
                url=callback_url,
                task_id=task_id,
                status=TaskStatus.FAILED,
                model_name=model_name_for_webhook,
                result_id=None,
                spent_credits=Decimal("0"),
                completed_at=datetime.now(UTC),
                error_message=error_text,
            )

        raise