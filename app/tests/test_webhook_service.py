from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from technical_document_ml_service.domain.enums import TaskStatus
from technical_document_ml_service.services.webhook_service import send_task_webhook


def _make_call(url: str = "https://example.com/hook", **overrides):
    defaults = dict(
        url=url,
        task_id=uuid4(),
        status=TaskStatus.COMPLETED,
        model_name="test-model",
        result_id=uuid4(),
        spent_credits=Decimal("10.00"),
        completed_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        error_message=None,
    )
    defaults.update(overrides)
    return send_task_webhook(**defaults)


class _FakeResponse:
    def __init__(self, status: int = 200):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def test_webhook_delivered_on_first_attempt():
    with patch("urllib.request.urlopen", return_value=_FakeResponse(200)) as mock_open:
        _make_call()

    assert mock_open.call_count == 1


def test_webhook_payload_is_correct_json():
    captured = []

    def _fake_urlopen(req, timeout):
        captured.append(req)
        return _FakeResponse(200)

    task_id = uuid4()
    result_id = uuid4()
    completed_at = datetime(2024, 6, 1, 10, 0, 0, tzinfo=UTC)

    with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
        send_task_webhook(
            url="https://example.com/hook",
            task_id=task_id,
            status=TaskStatus.COMPLETED,
            model_name="my-model",
            result_id=result_id,
            spent_credits=Decimal("25.50"),
            completed_at=completed_at,
            error_message=None,
        )

    assert len(captured) == 1
    req = captured[0]
    assert req.get_header("Content-type") == "application/json"

    payload = json.loads(req.data.decode("utf-8"))
    assert payload["task_id"] == str(task_id)
    assert payload["status"] == "completed"
    assert payload["model_name"] == "my-model"
    assert payload["result_id"] == str(result_id)
    assert payload["spent_credits"] == "25.50"
    assert payload["error_message"] is None
    assert payload["completed_at"] == completed_at.isoformat()


def test_webhook_retries_on_failure_then_succeeds():
    responses = [Exception("timeout"), _FakeResponse(200)]

    def _side_effect(req, timeout):
        resp = responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp

    with patch("urllib.request.urlopen", side_effect=_side_effect) as mock_open:
        with patch("time.sleep"):
            _make_call()

    assert mock_open.call_count == 2


def test_webhook_exhausts_all_retries_and_does_not_raise():
    with patch("urllib.request.urlopen", side_effect=Exception("connection refused")):
        with patch("time.sleep"):
            _make_call()


def test_webhook_skipped_for_invalid_scheme():
    with patch("urllib.request.urlopen") as mock_open:
        _make_call(url="ftp://not-http.example.com/hook")

    mock_open.assert_not_called()


def test_webhook_payload_for_failed_task():
    captured = []

    def _fake_urlopen(req, timeout):
        captured.append(json.loads(req.data.decode("utf-8")))
        return _FakeResponse(200)

    task_id = uuid4()
    with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
        send_task_webhook(
            url="https://example.com/hook",
            task_id=task_id,
            status=TaskStatus.FAILED,
            model_name="test-model",
            result_id=None,
            spent_credits=Decimal("0"),
            completed_at=None,
            error_message="Не удалось обработать документ.",
        )

    payload = captured[0]
    assert payload["status"] == "failed"
    assert payload["result_id"] is None
    assert payload["error_message"] == "Не удалось обработать документ."
    assert payload["completed_at"] is None
