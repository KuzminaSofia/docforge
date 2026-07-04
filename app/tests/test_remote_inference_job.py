from __future__ import annotations

from uuid import uuid4

import pytest
from helpers import submit_test_task

from technical_document_ml_service.db.models import MLRemoteInferenceJobORM, MLTaskORM
from technical_document_ml_service.domain.entities import DocumentExtractionTask
from technical_document_ml_service.domain.enums import RemoteJobStatus, TaskStatus
from technical_document_ml_service.domain.exceptions import TaskExecutionError


def _task_in_status(status: TaskStatus) -> DocumentExtractionTask:
    return DocumentExtractionTask(
        user_id=uuid4(),
        model_id=uuid4(),
        documents=[],
        target_schema="passport_fields",
        status=status,
    )


# ── domain lifecycle ─────────────────────────────────────────────────────────


def test_mark_as_awaiting_backend_from_processing() -> None:
    task = _task_in_status(TaskStatus.PROCESSING)
    task.mark_as_awaiting_backend()
    assert task.status == TaskStatus.AWAITING_BACKEND


def test_mark_as_awaiting_backend_rejects_non_processing() -> None:
    task = _task_in_status(TaskStatus.QUEUED)
    with pytest.raises(TaskExecutionError):
        task.mark_as_awaiting_backend()


def test_mark_as_completed_from_awaiting_backend() -> None:
    task = _task_in_status(TaskStatus.AWAITING_BACKEND)
    task.mark_as_completed(result_id=uuid4(), spent_credits=task.spent_credits)
    assert task.status == TaskStatus.COMPLETED


# ── ORM persistence ──────────────────────────────────────────────────────────


def test_remote_inference_job_round_trip(session_factory, api_user, api_model) -> None:
    submission = submit_test_task(api_user, api_model)

    with session_factory.begin() as session:
        session.add(
            MLRemoteInferenceJobORM(
                task_id=submission.task_id,
                backend_name="datalab",
                handle={"request_check_url": "https://check.url", "request_id": "abc"},
                status=RemoteJobStatus.PENDING.value,
            )
        )

    with session_factory() as session:
        task = session.get(MLTaskORM, submission.task_id)
        job = task.remote_inference_job

        assert job is not None
        assert job.backend_name == "datalab"
        assert job.status == "pending"
        assert job.attempts == 0
        assert job.handle["request_check_url"] == "https://check.url"
        assert job.task_id == submission.task_id


def test_remote_inference_job_is_unique_per_task(session_factory, api_user, api_model) -> None:
    submission = submit_test_task(api_user, api_model)

    def _add_job(session) -> None:
        session.add(
            MLRemoteInferenceJobORM(
                task_id=submission.task_id,
                backend_name="datalab",
                handle={},
                status=RemoteJobStatus.PENDING.value,
            )
        )

    with session_factory.begin() as session:
        _add_job(session)

    with pytest.raises(Exception):
        with session_factory.begin() as session:
            _add_job(session)
