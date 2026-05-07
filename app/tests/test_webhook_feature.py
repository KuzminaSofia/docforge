from __future__ import annotations

from decimal import Decimal
from unittest.mock import call, patch

from technical_document_ml_service.db.models import MLTaskORM
from technical_document_ml_service.db.session import SessionLocal
from technical_document_ml_service.domain.enums import TaskStatus
from technical_document_ml_service.services.document_storage_service import (
    IncomingDocumentData,
)
from technical_document_ml_service.services.prediction_processing_service import (
    process_document_prediction_task,
)
from technical_document_ml_service.services.prediction_submission_service import (
    submit_document_prediction,
)


def _submit(api_user, api_model, *, callback_url: str | None = None):
    with SessionLocal() as session:
        return submit_document_prediction(
            session,
            user_id=api_user.id,
            model_name=api_model.name,
            target_schema="passport_fields",
            documents=[
                IncomingDocumentData(
                    filename="sample.pdf",
                    content_type="application/pdf",
                    content=b"%PDF-1.4 test content",
                )
            ],
            callback_url=callback_url,
        )


def test_callback_url_stored_in_db_when_provided(api_user, api_model, publish_task_spy):
    url = "https://example.com/callback"
    submission = _submit(api_user, api_model, callback_url=url)

    with SessionLocal() as session:
        task = session.get(MLTaskORM, submission.task_id)
        assert task is not None
        assert task.callback_url == url


def test_callback_url_is_null_when_not_provided(api_user, api_model, publish_task_spy):
    submission = _submit(api_user, api_model)

    with SessionLocal() as session:
        task = session.get(MLTaskORM, submission.task_id)
        assert task is not None
        assert task.callback_url is None


def test_submission_result_includes_callback_url(api_user, api_model, publish_task_spy):
    url = "https://example.com/callback"
    submission = _submit(api_user, api_model, callback_url=url)
    assert submission.callback_url == url


def test_predict_api_stores_and_returns_callback_url(
    client, api_user, api_model, auth_headers, publish_task_spy
):
    url = "https://my-service.example.com/on-complete"
    response = client.post(
        "/predict",
        data={
            "model_name": api_model.name,
            "target_schema": "passport_fields",
            "callback_url": url,
        },
        files=[("documents", ("doc.pdf", b"%PDF-1.4", "application/pdf"))],
        headers=auth_headers,
    )

    assert response.status_code == 202
    body = response.json()
    assert body["callback_url"] == url

    with SessionLocal() as session:
        task = session.get(MLTaskORM, body["task_id"])
        assert task is not None
        assert task.callback_url == url


def test_predict_api_returns_null_callback_url_when_omitted(
    client, api_user, api_model, auth_headers, publish_task_spy
):
    response = client.post(
        "/predict",
        data={
            "model_name": api_model.name,
            "target_schema": "passport_fields",
        },
        files=[("documents", ("doc.pdf", b"%PDF-1.4", "application/pdf"))],
        headers=auth_headers,
    )

    assert response.status_code == 202
    assert response.json()["callback_url"] is None


def test_webhook_called_after_successful_processing(
    api_user, api_model, publish_task_spy
):
    url = "https://example.com/hook"
    submission = _submit(api_user, api_model, callback_url=url)

    with patch(
        "technical_document_ml_service.services.prediction_processing_service.send_task_webhook"
    ) as mock_webhook:
        with SessionLocal() as session:
            process_document_prediction_task(session, task_id=submission.task_id)

    mock_webhook.assert_called_once()
    kwargs = mock_webhook.call_args.kwargs
    assert kwargs["url"] == url
    assert kwargs["status"] == TaskStatus.COMPLETED
    assert kwargs["result_id"] is not None
    assert kwargs["spent_credits"] == Decimal("10.00")
    assert kwargs["error_message"] is None


def test_webhook_not_called_when_no_callback_url(
    api_user, api_model, publish_task_spy
):
    submission = _submit(api_user, api_model, callback_url=None)

    with patch(
        "technical_document_ml_service.services.prediction_processing_service.send_task_webhook"
    ) as mock_webhook:
        with SessionLocal() as session:
            process_document_prediction_task(session, task_id=submission.task_id)

    mock_webhook.assert_not_called()


def test_webhook_called_with_failed_status_on_processing_error(
    api_user, api_model, publish_task_spy
):
    url = "https://example.com/hook"
    submission = _submit(api_user, api_model, callback_url=url)

    with patch(
        "technical_document_ml_service.services.prediction_processing_service.send_task_webhook"
    ) as mock_webhook:
        with patch(
            "technical_document_ml_service.services.prediction_processing_service.select_prediction_backend",
            side_effect=RuntimeError("backend unavailable"),
        ):
            with SessionLocal() as session:
                try:
                    process_document_prediction_task(
                        session, task_id=submission.task_id
                    )
                except RuntimeError:
                    pass

    mock_webhook.assert_called_once()
    kwargs = mock_webhook.call_args.kwargs
    assert kwargs["url"] == url
    assert kwargs["status"] == TaskStatus.FAILED
    assert kwargs["result_id"] is None
    assert kwargs["error_message"] == "backend unavailable"
