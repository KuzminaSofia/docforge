from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from technical_document_ml_service.db.models import MLRemoteInferenceJobORM, MLTaskORM
from technical_document_ml_service.domain.entities import (
    DebitTransaction,
    DocumentExtractionTask,
)
from technical_document_ml_service.domain.enums import RemoteJobStatus, TaskStatus
from technical_document_ml_service.domain.exceptions import (
    NotFoundError,
    TaskExecutionError,
)
from technical_document_ml_service.inference.contracts import BackendResult
from technical_document_ml_service.inference.selector import (
    BackendSelection,
    select_prediction_backend,
)
from technical_document_ml_service.services.billing_service import record_transaction
from technical_document_ml_service.services.history_service import (
    create_history_record_from_task,
)
from technical_document_ml_service.services.inference_mappers import (
    build_artifacts_prefix,
    build_backend_request,
    build_prediction_result_from_backend_result,
)
from technical_document_ml_service.services.inference_staging import (
    fetch_with_staging,
    run_backend_with_staging,
    submit_with_staging,
)
from technical_document_ml_service.services.mappers import (
    model_orm_to_domain,
    orm_to_domain_user,
    sync_task_orm_from_domain,
    sync_user_orm_from_domain,
    task_orm_to_domain,
)
from technical_document_ml_service.services.prediction_persistence import (
    ensure_prediction_can_start,
    persist_prediction_result,
)
from technical_document_ml_service.messaging.contracts import WebhookDeliveryMessage
from technical_document_ml_service.messaging.rabbitmq import publish_webhook_delivery


LOGGER = logging.getLogger("technical_document_ml_service.prediction_processing")

# после этого срока remote-задача считается зависшей и помечается FAILED по таймауту
_REMOTE_JOB_DEADLINE_SECONDS = 1800


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
            selectinload(MLTaskORM.remote_inference_job),
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


def _persist_status_transition(
    session: Session,
    *,
    task_orm: MLTaskORM,
    domain_task: DocumentExtractionTask,
) -> None:
    """зафиксировать промежуточный статус задачи в БД без сохранения финального результата"""
    sync_task_orm_from_domain(task_orm, domain_task)
    session.commit()


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


_SAFE_SKIP_STATUSES: frozenset[TaskStatus] = frozenset(
    {TaskStatus.COMPLETED, TaskStatus.FAILED}
)
_SAFE_SKIP_MESSAGES: dict[TaskStatus, str] = {
    TaskStatus.COMPLETED: "Задача уже была успешно обработана ранее.",
    TaskStatus.FAILED: "Задача ранее завершилась с ошибкой.",
}

# Задача застряла в промежуточном статусе — воркер упал в процессе обработки.
# При повторной доставке (redelivered=True) помечаем как FAILED вместо тихого skip+ack.
_ZOMBIE_STATUSES: frozenset[TaskStatus] = frozenset(
    {TaskStatus.PROCESSING, TaskStatus.VALIDATING}
)


def _schedule_webhook(
    *,
    callback_url: str,
    task_id: UUID,
    status: TaskStatus,
    model_name: str,
    result_id: UUID | None,
    spent_credits: Decimal,
    completed_at: datetime | None,
    error_message: str | None,
) -> None:
    """поставить webhook-уведомление в очередь; сбои публикации только логируются"""
    try:
        msg = WebhookDeliveryMessage(
            task_id=task_id,
            callback_url=callback_url,
            status=status.value,
            model_name=model_name,
            result_id=result_id,
            spent_credits=str(spent_credits),
            completed_at=completed_at.isoformat() if completed_at is not None else None,
            error_message=error_message,
        )
        publish_webhook_delivery(msg)
    except Exception:
        LOGGER.exception(
            "task_id=%s | Не удалось поставить webhook в очередь",
            task_id,
        )


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

    ensure_prediction_can_start(user=domain_user, model=domain_model)


def _build_request_and_select(domain_task: DocumentExtractionTask, domain_model):
    """собрать backend request и выбрать backend (общий шаг для sync и remote)"""
    backend_request = build_backend_request(
        task=domain_task,
        model_id=domain_model.id,
        model_name=domain_model.name,
        model_kind=domain_model.model_kind,
        backend_name=domain_model.backend_name,
        backend_config=domain_model.backend_config,
    )
    backend_selection = select_prediction_backend(
        requested_backend_name=domain_model.backend_name,
        backend_config=domain_model.backend_config,
    )
    return backend_selection, backend_request


def _log_backend_warnings(backend_result, *, task_id: UUID, backend_name: str) -> None:
    """залогировать предупреждения backend-результата"""
    for warning in backend_result.warnings:
        LOGGER.warning(
            "task_id=%s | backend=%s | warning=%s", task_id, backend_name, warning
        )


def _persist_remote_job(
    session: Session,
    *,
    task_id: UUID,
    backend_name: str,
    handle: dict[str, Any],
    deadline_at: datetime,
) -> None:
    """сохранить checkpoint удалённой задачи для последующего опроса reconciler'ом"""
    session.add(
        MLRemoteInferenceJobORM(
            task_id=task_id,
            backend_name=backend_name,
            handle=handle,
            status=RemoteJobStatus.PENDING.value,
            deadline_at=deadline_at,
        )
    )


def _persist_completion(
    session: Session,
    *,
    task_orm: MLTaskORM,
    domain_task: DocumentExtractionTask,
    domain_user,
    result,
    debit_transaction,
) -> None:
    """сохранить результат, транзакцию и запись истории, зафиксировать транзакцию"""
    sync_user_orm_from_domain(task_orm.user, domain_user)
    sync_task_orm_from_domain(task_orm, domain_task)

    persist_prediction_result(session, task_id=domain_task.id, result=result)
    record_transaction(session, transaction=debit_transaction)
    create_history_record_from_task(session, domain_task)

    session.commit()


def _execute_prediction(
    session: Session,
    *,
    task_orm: MLTaskORM,
    domain_task: DocumentExtractionTask,
    domain_user,
    domain_model,
) -> PredictionProcessingResult:
    """фаза старта: валидация -> sync (обработать сразу) | remote (submit + AWAITING)"""
    _ensure_processing_can_start(
        domain_task=domain_task,
        domain_user=domain_user,
        domain_model=domain_model,
    )

    domain_task.mark_as_validating()
    _persist_status_transition(session, task_orm=task_orm, domain_task=domain_task)

    domain_task.validate_input()
    if not domain_task.get_valid_documents():
        raise TaskExecutionError("Нет валидных документов для обработки.")

    domain_task.mark_as_processing()
    _persist_status_transition(session, task_orm=task_orm, domain_task=domain_task)

    backend_selection, backend_request = _build_request_and_select(domain_task, domain_model)

    if backend_selection.backend.is_remote:
        return _start_remote_prediction(
            session,
            task_orm=task_orm,
            domain_task=domain_task,
            backend_selection=backend_selection,
            backend_request=backend_request,
        )

    backend_result = run_backend_with_staging(backend_selection.backend, backend_request)
    _log_backend_warnings(
        backend_result,
        task_id=domain_task.id,
        backend_name=backend_selection.resolved_backend_name,
    )
    return finalize_prediction(
        session,
        task_id=domain_task.id,
        backend_result=backend_result,
        resolved_backend_name=backend_selection.resolved_backend_name,
    )


def _start_remote_prediction(
    session: Session,
    *,
    task_orm: MLTaskORM,
    domain_task: DocumentExtractionTask,
    backend_selection: BackendSelection,
    backend_request,
) -> PredictionProcessingResult:
    """remote-backend: отправить документы, сохранить checkpoint, перевести в AWAITING_BACKEND"""
    handle = submit_with_staging(backend_selection.backend, backend_request)

    _persist_remote_job(
        session,
        task_id=domain_task.id,
        backend_name=backend_selection.resolved_backend_name,
        handle=handle,
        deadline_at=datetime.now(UTC) + timedelta(seconds=_REMOTE_JOB_DEADLINE_SECONDS),
    )
    domain_task.mark_as_awaiting_backend()
    _persist_status_transition(session, task_orm=task_orm, domain_task=domain_task)

    return PredictionProcessingResult(
        task_id=domain_task.id,
        status=domain_task.status,
        result_id=None,
        created_at=domain_task.created_at,
        completed_at=None,
        spent_credits=Decimal("0"),
        was_processed=False,
        message=(
            f"Задача отправлена в remote backend "
            f"'{backend_selection.resolved_backend_name}', ожидается результат."
        ),
    )


def finalize_prediction(
    session: Session,
    *,
    task_id: UUID,
    backend_result: BackendResult,
    resolved_backend_name: str,
) -> PredictionProcessingResult:
    """завершить задачу по готовому backend-результату: списать баланс, сохранить, COMPLETED

    Идемпотентно: вызывается из sync-пути и из reconciler'а; повторный вызов на уже
    завершённой задаче — no-op (skip).
    """
    task_orm = _load_task_for_processing(session, task_id)
    if task_orm is None:
        raise NotFoundError(f"Задача с id={task_id} не найдена.")

    current_status = TaskStatus(task_orm.status)
    if current_status in _SAFE_SKIP_STATUSES:
        return _build_skipped_result(task_orm, message=_SAFE_SKIP_MESSAGES[current_status])

    domain_user = orm_to_domain_user(task_orm.user)
    domain_model = model_orm_to_domain(task_orm.model)
    domain_task = task_orm_to_domain(task_orm)

    validation_issues = domain_task.validate_input()

    result = build_prediction_result_from_backend_result(
        task_id=domain_task.id,
        backend_result=backend_result,
        artifacts_dir=build_artifacts_prefix(
            user_id=domain_task.user_id, task_id=domain_task.id
        ),
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

    if task_orm.remote_inference_job is not None:
        task_orm.remote_inference_job.status = RemoteJobStatus.SUCCEEDED.value

    _persist_completion(
        session,
        task_orm=task_orm,
        domain_task=domain_task,
        domain_user=domain_user,
        result=result,
        debit_transaction=debit_transaction,
    )

    return PredictionProcessingResult(
        task_id=domain_task.id,
        status=domain_task.status,
        result_id=domain_task.result_id,
        created_at=domain_task.created_at,
        completed_at=domain_task.finished_at,
        spent_credits=domain_task.spent_credits,
        was_processed=True,
        message=f"Задача успешно обработана через backend '{resolved_backend_name}'.",
    )


def _fail_awaiting_task(
    session: Session,
    *,
    task_orm: MLTaskORM,
    job: MLRemoteInferenceJobORM,
    error_message: str,
) -> None:
    """пометить зависшую/ошибочную remote-задачу как FAILED и закрыть job"""
    domain_task = task_orm_to_domain(task_orm)
    domain_task.fail(error_message)
    sync_task_orm_from_domain(task_orm, domain_task)
    job.status = RemoteJobStatus.FAILED.value
    session.commit()


def reconcile_remote_job(session: Session, *, job_id: UUID) -> None:
    """опросить одну remote-задачу off-slot и продвинуть её (готово/таймаут/ещё считается)

    Вызывается reconciler'ом. Блокирует строку job через SKIP LOCKED, чтобы reconciler'ы
    нескольких воркеров не дублировали опрос. Сетевой опрос — один быстрый запрос на
    документ (долгое ожидание происходит между тиками, а не внутри).
    """
    job = session.scalar(
        select(MLRemoteInferenceJobORM)
        .where(MLRemoteInferenceJobORM.id == job_id)
        .where(MLRemoteInferenceJobORM.status == RemoteJobStatus.PENDING.value)
        .with_for_update(skip_locked=True)
    )
    if job is None:
        return  # уже подобрана другим reconciler'ом или завершена

    task_orm = _load_task_for_processing(session, job.task_id)
    if task_orm is None:
        job.status = RemoteJobStatus.FAILED.value
        session.commit()
        return

    # задача уже не в ожидании (обработана/упала иным путём) — закрываем job
    if TaskStatus(task_orm.status) != TaskStatus.AWAITING_BACKEND:
        job.status = (
            RemoteJobStatus.SUCCEEDED.value
            if TaskStatus(task_orm.status) == TaskStatus.COMPLETED
            else RemoteJobStatus.FAILED.value
        )
        session.commit()
        return

    domain_model = model_orm_to_domain(task_orm.model)
    callback_url: str | None = task_orm.callback_url

    if job.deadline_at is not None and datetime.now(UTC) > job.deadline_at:
        error_msg = "Превышен дедлайн ожидания результата remote backend."
        _fail_awaiting_task(session, task_orm=task_orm, job=job, error_message=error_msg)
        _notify_remote_failure(callback_url, job.task_id, domain_model.name, error_msg)
        return

    domain_task = task_orm_to_domain(task_orm)
    backend_request = build_backend_request(
        task=domain_task,
        model_id=domain_model.id,
        model_name=domain_model.name,
        model_kind=domain_model.model_kind,
        backend_name=domain_model.backend_name,
        backend_config=domain_model.backend_config,
    )
    backend_selection = select_prediction_backend(
        requested_backend_name=domain_model.backend_name,
        backend_config=domain_model.backend_config,
    )

    try:
        backend_result = fetch_with_staging(
            backend_selection.backend, backend_request, job.handle
        )
    except Exception as exc:
        error_msg = f"Ошибка remote backend при опросе результата: {exc}"
        LOGGER.exception("task_id=%s | %s", job.task_id, error_msg)
        _fail_awaiting_task(session, task_orm=task_orm, job=job, error_message=error_msg)
        _notify_remote_failure(callback_url, job.task_id, domain_model.name, error_msg)
        return

    if backend_result is None:
        # ещё считается на стороне backend — обновим счётчик и подождём следующего тика
        job.attempts += 1
        session.commit()
        return

    _log_backend_warnings(
        backend_result,
        task_id=job.task_id,
        backend_name=backend_selection.resolved_backend_name,
    )
    processing_result = finalize_prediction(
        session,
        task_id=job.task_id,
        backend_result=backend_result,
        resolved_backend_name=backend_selection.resolved_backend_name,
    )

    if callback_url and processing_result.status in _SAFE_SKIP_STATUSES:
        _schedule_webhook(
            callback_url=callback_url,
            task_id=processing_result.task_id,
            status=processing_result.status,
            model_name=domain_model.name,
            result_id=processing_result.result_id,
            spent_credits=processing_result.spent_credits,
            completed_at=processing_result.completed_at,
            error_message=None,
        )


def _notify_remote_failure(
    callback_url: str | None,
    task_id: UUID,
    model_name: str,
    error_message: str,
) -> None:
    """отправить webhook о провале remote-задачи (если задан callback_url)"""
    if not callback_url:
        return
    _schedule_webhook(
        callback_url=callback_url,
        task_id=task_id,
        status=TaskStatus.FAILED,
        model_name=model_name,
        result_id=None,
        spent_credits=Decimal("0"),
        completed_at=datetime.now(UTC),
        error_message=error_message,
    )


def process_document_prediction_task(
    session: Session,
    *,
    task_id: UUID,
    redelivered: bool = False,
) -> PredictionProcessingResult:
    """обработать ранее поставленную в очередь задачу"""
    task_orm = _load_task_for_processing(session, task_id)
    if task_orm is None:
        raise NotFoundError(f"Задача с id={task_id} не найдена.")

    callback_url: str | None = task_orm.callback_url

    # domain_model через маппер — backend_name/config/kind доступны только через него
    domain_model = model_orm_to_domain(task_orm.model)

    current_status = TaskStatus(task_orm.status)

    if current_status in _SAFE_SKIP_STATUSES:
        return _build_skipped_result(task_orm, message=_SAFE_SKIP_MESSAGES[current_status])

    if current_status in _ZOMBIE_STATUSES:
        if redelivered:
            error_msg = (
                f"Задача застряла в статусе '{current_status.value}': "
                "воркер завершился в процессе обработки."
            )
            domain_task = task_orm_to_domain(task_orm)
            domain_task.fail(error_msg)
            sync_task_orm_from_domain(task_orm, domain_task)
            session.commit()

            if callback_url:
                _schedule_webhook(
                    callback_url=callback_url,
                    task_id=task_id,
                    status=TaskStatus.FAILED,
                    model_name=domain_model.name,
                    result_id=None,
                    spent_credits=Decimal("0"),
                    completed_at=domain_task.finished_at,
                    error_message=error_msg,
                )

            return PredictionProcessingResult(
                task_id=domain_task.id,
                status=domain_task.status,
                result_id=None,
                created_at=domain_task.created_at,
                completed_at=domain_task.finished_at,
                spent_credits=domain_task.spent_credits,
                was_processed=False,
                message=error_msg,
            )
        else:
            return _build_skipped_result(
                task_orm,
                message=f"Задача уже находится в обработке (статус: {current_status.value}).",
            )

    if current_status != TaskStatus.QUEUED:
        return _build_skipped_result(
            task_orm,
            message=f"Задача в статусе {current_status.value} не может быть обработана воркером.",
        )

    domain_user = orm_to_domain_user(task_orm.user)
    domain_task = task_orm_to_domain(task_orm)

    try:
        processing_result = _execute_prediction(
            session,
            task_orm=task_orm,
            domain_task=domain_task,
            domain_user=domain_user,
            domain_model=domain_model,
        )

        # remote-задача ещё не завершена (AWAITING_BACKEND) — webhook отправит
        # reconciler по факту завершения; здесь шлём только для терминального статуса
        if callback_url and processing_result.status in _SAFE_SKIP_STATUSES:
            _schedule_webhook(
                callback_url=callback_url,
                task_id=processing_result.task_id,
                status=processing_result.status,
                model_name=domain_model.name,
                result_id=processing_result.result_id,
                spent_credits=processing_result.spent_credits,
                completed_at=processing_result.completed_at,
                error_message=None,
            )

        return processing_result

    except Exception as exc:
        if session.in_transaction():
            session.rollback()

        error_text = str(exc)
        _mark_task_as_failed(session, task_id=task_id, error_message=error_text)

        if callback_url:
            _schedule_webhook(
                callback_url=callback_url,
                task_id=task_id,
                status=TaskStatus.FAILED,
                model_name=domain_model.name,
                result_id=None,
                spent_credits=Decimal("0"),
                completed_at=datetime.now(UTC),
                error_message=error_text,
            )

        raise