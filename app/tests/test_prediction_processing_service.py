from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select

from technical_document_ml_service.db.models import (
    MLRequestHistoryORM,
    MLTaskORM,
    PredictionResultORM,
    TransactionORM,
    UserORM,
)
from technical_document_ml_service.db.session import SessionLocal
from technical_document_ml_service.services.prediction_processing_service import (
    process_document_prediction_task,
)
from helpers import submit_test_task


def test_process_document_prediction_task_completes_and_persists_result(
    api_user,
    api_model,
    publish_task_spy,
) -> None:
    submission = submit_test_task(api_user, api_model)

    with SessionLocal() as session:
        result = process_document_prediction_task(
            session,
            task_id=submission.task_id,
        )

    assert result.task_id == submission.task_id
    assert result.status.value == "completed"
    assert result.was_processed is True
    assert result.result_id is not None
    assert result.spent_credits == Decimal("10.00")
    assert result.completed_at is not None

    assert len(publish_task_spy) == 1

    with SessionLocal() as session:
        task = session.get(MLTaskORM, submission.task_id)
        assert task is not None
        assert task.status == "completed"
        assert task.spent_credits == Decimal("10.00")
        assert task.completed_at is not None

        user = session.get(UserORM, api_user.id)
        assert user is not None
        assert user.balance_credits == Decimal("90.00")

        prediction_results = session.scalars(
            select(PredictionResultORM)
        ).all()
        transactions_count = session.scalar(
            select(func.count()).select_from(TransactionORM)
        )
        history_count = session.scalar(
            select(func.count()).select_from(MLRequestHistoryORM)
        )

        assert len(prediction_results) == 1
        prediction_result = prediction_results[0]
        assert prediction_result.output_file_path is not None
        assert prediction_result.artifacts_dir is not None
        # ключи артефактов симметричны uploads: artifacts/<owner_id>/<task_id>/...
        assert prediction_result.artifacts_dir == f"artifacts/{api_user.id}/{submission.task_id}"
        assert prediction_result.artifacts_manifest[0]["path"].startswith(
            f"artifacts/{api_user.id}/{submission.task_id}/"
        )
        assert len(prediction_result.artifacts_manifest) >= 1

        assert transactions_count == 1
        assert history_count == 1


def test_process_document_prediction_task_is_idempotent_for_completed_task(
    api_user,
    api_model,
    publish_task_spy,
) -> None:
    submission = submit_test_task(api_user, api_model)

    with SessionLocal() as session:
        first_result = process_document_prediction_task(
            session,
            task_id=submission.task_id,
        )

    assert first_result.was_processed is True

    with SessionLocal() as session:
        second_result = process_document_prediction_task(
            session,
            task_id=submission.task_id,
        )

    assert second_result.task_id == submission.task_id
    assert second_result.status.value == "completed"
    assert second_result.was_processed is False
    assert second_result.message == "Задача уже была успешно обработана ранее."

    with SessionLocal() as session:
        prediction_results_count = session.scalar(
            select(func.count()).select_from(PredictionResultORM)
        )
        transactions_count = session.scalar(
            select(func.count()).select_from(TransactionORM)
        )
        history_count = session.scalar(
            select(func.count()).select_from(MLRequestHistoryORM)
        )

        assert prediction_results_count == 1
        assert transactions_count == 1
        assert history_count == 1