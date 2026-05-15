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


def test_predict_accepts_task_and_enqueues_message(
    client,
    api_user,
    api_model,
    auth_headers,
    publish_task_spy,
) -> None:
    files = [
        ("document", ("sample.pdf", b"%PDF-1.4 test content", "application/pdf")),
    ]
    data = {
        "model_name": api_model.name,
        "target_schema": "passport_fields",
    }

    response = client.post(
        "/predict",
        data=data,
        files=files,
        headers=auth_headers,
    )

    assert response.status_code == 202
    body = response.json()

    assert body["task_id"] is not None
    assert body["model_id"] == str(api_model.id)
    assert body["model_name"] == api_model.name
    assert body["status"] == "queued"
    assert body["created_at"] is not None
    assert body["message"] == "Задача принята и поставлена в очередь на обработку."

    assert len(publish_task_spy) == 1
    published_message = publish_task_spy[0]["message"]

    assert str(published_message.task_id) == body["task_id"]
    assert str(published_message.user_id) == str(api_user.id)
    assert published_message.model_name == api_model.name

    with SessionLocal() as session:
        task = session.get(MLTaskORM, body["task_id"])
        assert task is not None
        assert task.status == "queued"
        assert task.target_schema == "passport_fields"
        assert len(task.documents) == 1

        user = session.get(UserORM, api_user.id)
        assert user is not None
        assert user.balance_credits == Decimal("100.00")

        prediction_results_count = session.scalar(
            select(func.count()).select_from(PredictionResultORM)
        )
        transactions_count = session.scalar(
            select(func.count()).select_from(TransactionORM)
        )
        history_count = session.scalar(
            select(func.count()).select_from(MLRequestHistoryORM)
        )

        assert prediction_results_count == 0
        assert transactions_count == 0
        assert history_count == 0


def test_predict_with_insufficient_balance_returns_409_and_does_not_publish(
    client,
    low_balance_user,
    api_model,
    low_balance_auth_headers,
    publish_task_spy,
) -> None:
    files = [
        ("document", ("sample.pdf", b"%PDF-1.4 test content", "application/pdf")),
    ]
    data = {
        "model_name": api_model.name,
        "target_schema": "passport_fields",
    }

    response = client.post(
        "/predict",
        data=data,
        files=files,
        headers=low_balance_auth_headers,
    )

    assert response.status_code == 409
    body = response.json()

    assert body["error"]["code"] == "insufficient_balance"
    assert len(publish_task_spy) == 0

    with SessionLocal() as session:
        tasks_count = session.scalar(select(func.count()).select_from(MLTaskORM))
        assert tasks_count == 0


def test_predict_with_missing_model_returns_404_and_does_not_publish(
    client,
    api_user,
    auth_headers,
    publish_task_spy,
) -> None:
    files = [
        ("document", ("sample.pdf", b"%PDF-1.4 test content", "application/pdf")),
    ]
    data = {
        "model_name": "missing-model",
        "target_schema": "passport_fields",
    }

    response = client.post(
        "/predict",
        data=data,
        files=files,
        headers=auth_headers,
    )

    assert response.status_code == 404
    body = response.json()

    assert body["error"]["code"] == "not_found"
    assert len(publish_task_spy) == 0

    with SessionLocal() as session:
        tasks_count = session.scalar(select(func.count()).select_from(MLTaskORM))
        assert tasks_count == 0