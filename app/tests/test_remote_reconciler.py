from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from helpers import submit_test_task

from technical_document_ml_service.db.models import MLModelORM, MLTaskORM, UserORM
from technical_document_ml_service.db.session import SessionLocal
from technical_document_ml_service.domain.enums import RemoteJobStatus, TaskStatus
from technical_document_ml_service.services.prediction_processing_service import (
    process_document_prediction_task,
    reconcile_remote_job,
)


@pytest.fixture
def datalab_model(session_factory) -> MLModelORM:
    """remote-модель (datalab) в stub-режиме для тестов без сети"""
    with session_factory.begin() as session:
        model = MLModelORM(
            id=uuid4(),
            name="test-datalab-model",
            description="Тестовая remote-модель",
            prediction_cost=Decimal("10.00"),
            is_active=True,
            model_kind="technical_document_extraction",
            supported_document_types=["unknown"],
            backend_name="datalab",
            backend_config={"allow_stub_fallback": True, "poll_interval_s": 0},
        )
        session.add(model)
        session.flush()
        model_id = model.id

    with session_factory() as session:
        return session.get(MLModelORM, model_id)


@pytest.fixture(autouse=True)
def _force_stub_and_no_publish(monkeypatch, publish_task_spy):
    """в тестах нет реального Datalab — гарантируем stub-режим; и не публикуем в очередь,
    чтобы запущенные воркеры не перехватили задачу (publish_task_spy)"""
    monkeypatch.delenv("APP_DATALAB_API_KEY", raising=False)


def test_remote_task_goes_awaiting_then_reconciler_completes(
    session_factory, api_user, datalab_model
) -> None:
    submission = submit_test_task(api_user, datalab_model)
    task_id = submission.task_id

    # фаза старта (воркер): remote backend → AWAITING_BACKEND, баланс ещё не списан
    with SessionLocal() as session:
        start_result = process_document_prediction_task(session, task_id=task_id)

    assert start_result.status == TaskStatus.AWAITING_BACKEND
    assert start_result.was_processed is False

    with session_factory() as session:
        task = session.get(MLTaskORM, task_id)
        assert task.status == TaskStatus.AWAITING_BACKEND.value
        assert task.remote_inference_job is not None
        assert task.remote_inference_job.status == RemoteJobStatus.PENDING.value
        assert task.prediction_result is None
        assert session.get(UserORM, api_user.id).balance_credits == Decimal("100.00")
        job_id = task.remote_inference_job.id

    # фаза reconciler: stub-fetch готов сразу → COMPLETED + списание
    with SessionLocal() as session:
        reconcile_remote_job(session, job_id=job_id)

    with session_factory() as session:
        task = session.get(MLTaskORM, task_id)
        assert task.status == TaskStatus.COMPLETED.value
        assert task.remote_inference_job.status == RemoteJobStatus.SUCCEEDED.value
        assert task.prediction_result is not None
        assert session.get(UserORM, api_user.id).balance_credits == Decimal("90.00")


def test_reconcile_is_idempotent(session_factory, api_user, datalab_model) -> None:
    submission = submit_test_task(api_user, datalab_model)
    task_id = submission.task_id

    with SessionLocal() as session:
        process_document_prediction_task(session, task_id=task_id)
    with session_factory() as session:
        job_id = session.get(MLTaskORM, task_id).remote_inference_job.id

    with SessionLocal() as session:
        reconcile_remote_job(session, job_id=job_id)
    # повторный вызов: job уже succeeded → no-op, без двойного списания
    with SessionLocal() as session:
        reconcile_remote_job(session, job_id=job_id)

    with session_factory() as session:
        assert session.get(UserORM, api_user.id).balance_credits == Decimal("90.00")


def test_remote_task_fails_on_deadline(session_factory, api_user, datalab_model) -> None:
    submission = submit_test_task(api_user, datalab_model)
    task_id = submission.task_id

    with SessionLocal() as session:
        process_document_prediction_task(session, task_id=task_id)

    # форсируем истёкший дедлайн → reconciler помечает задачу FAILED, баланс не трогает
    with session_factory.begin() as session:
        job = session.get(MLTaskORM, task_id).remote_inference_job
        job.deadline_at = datetime.now(UTC) - timedelta(seconds=1)
        job_id = job.id

    with SessionLocal() as session:
        reconcile_remote_job(session, job_id=job_id)

    with session_factory() as session:
        task = session.get(MLTaskORM, task_id)
        assert task.status == TaskStatus.FAILED.value
        assert task.remote_inference_job.status == RemoteJobStatus.FAILED.value
        assert session.get(UserORM, api_user.id).balance_credits == Decimal("100.00")
