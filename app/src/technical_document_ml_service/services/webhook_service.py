from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from technical_document_ml_service.domain.enums import TaskStatus


LOGGER = logging.getLogger("technical_document_ml_service.webhook")

_MAX_ATTEMPTS = 3
_RETRY_DELAYS_SECONDS = (1, 3)
_REQUEST_TIMEOUT_SECONDS = 10


def _is_valid_webhook_url(url: str) -> bool:
    return url.startswith("http://") or url.startswith("https://")


def _build_payload(
    *,
    task_id: UUID,
    status: TaskStatus,
    model_name: str,
    result_id: UUID | None,
    spent_credits: Decimal,
    completed_at: datetime | None,
    error_message: str | None,
) -> bytes:
    return json.dumps(
        {
            "task_id": str(task_id),
            "status": status.value,
            "model_name": model_name,
            "result_id": str(result_id) if result_id else None,
            "spent_credits": str(spent_credits),
            "error_message": error_message,
            "completed_at": completed_at.isoformat() if completed_at else None,
        }
    ).encode("utf-8")


def send_task_webhook(
    *,
    url: str,
    task_id: UUID,
    status: TaskStatus,
    model_name: str,
    result_id: UUID | None,
    spent_credits: Decimal,
    completed_at: datetime | None,
    error_message: str | None,
) -> None:
    """
    отправить POST-уведомление на callback_url о завершении задачи
    до 3 попыток с задержкой 1s и 3s между ними
    cбой доставки логируется
    """
    if not _is_valid_webhook_url(url):
        LOGGER.warning(
            "task_id=%s | Некорректный callback_url, webhook пропущен: %s",
            task_id,
            url,
        )
        return

    payload = _build_payload(
        task_id=task_id,
        status=status,
        model_name=model_name,
        result_id=result_id,
        spent_credits=spent_credits,
        completed_at=completed_at,
        error_message=error_message,
    )
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    for attempt in range(_MAX_ATTEMPTS):
        try:
            with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT_SECONDS) as resp:
                LOGGER.info(
                    "task_id=%s | Webhook доставлен | url=%s | http_status=%s",
                    task_id,
                    url,
                    resp.status,
                )
                return
        except Exception as exc:
            if attempt < _MAX_ATTEMPTS - 1:
                delay = _RETRY_DELAYS_SECONDS[attempt]
                LOGGER.warning(
                    "task_id=%s | Webhook не доставлен (попытка %d/%d): %s. "
                    "Повтор через %ds.",
                    task_id,
                    attempt + 1,
                    _MAX_ATTEMPTS,
                    exc,
                    delay,
                )
                time.sleep(delay)
            else:
                LOGGER.error(
                    "task_id=%s | Webhook не доставлен после %d попыток: %s",
                    task_id,
                    _MAX_ATTEMPTS,
                    exc,
                )
