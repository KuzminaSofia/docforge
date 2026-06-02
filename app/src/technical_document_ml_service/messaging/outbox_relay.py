from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from technical_document_ml_service.db.models import OutboxEventORM
from technical_document_ml_service.db.session import SessionLocal, read_session
from technical_document_ml_service.messaging.contracts import PredictionTaskMessage
from technical_document_ml_service.messaging.rabbitmq import publish_prediction_task

LOGGER = logging.getLogger("technical_document_ml_service.messaging.outbox_relay")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class OutboxRelay:
    """фоновый поток, который доставляет неопубликованные outbox-события в RabbitMQ

    гарантирует at-least-once доставку: если приложение упало между commit и publish,
    relay подберет событие на следующем цикле опроса
    SELECT FOR UPDATE SKIP LOCKED обеспечивает безопасную работу нескольких инстансов
    worker идемпотентен (_SAFE_SKIP_STATUSES)
    """

    def __init__(self, *, poll_interval: int = 60, batch_size: int = 10) -> None:
        self._poll_interval = poll_interval
        self._batch_size = batch_size
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="outbox-relay",
            daemon=True,
        )
        self._thread.start()
        LOGGER.info(
            "OutboxRelay запущен (интервал=%ds, батч=%d)",
            self._poll_interval,
            self._batch_size,
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=15)
            self._thread = None
        LOGGER.info("OutboxRelay остановлен")

    def _run(self) -> None:
        while not self._stop_event.wait(self._poll_interval):
            try:
                self._flush_pending()
            except Exception:
                LOGGER.exception("OutboxRelay: необработанная ошибка в цикле опроса")

    def _flush_pending(self) -> None:
        # Сначала собираем ID без блокировок (быстрый скан)
        with read_session() as session:
            pending_ids: list[uuid.UUID] = list(
                session.scalars(
                    select(OutboxEventORM.id)
                    .where(OutboxEventORM.published_at.is_(None))
                    .order_by(OutboxEventORM.created_at)
                    .limit(self._batch_size)
                )
            )

        for event_id in pending_ids:
            if self._stop_event.is_set():
                break
            self._publish_one(event_id)

    def _publish_one(self, event_id: uuid.UUID) -> None:
        """опубликовать одно событие в отдельной транзакции с SELECT FOR UPDATE SKIP LOCKED"""
        try:
            with SessionLocal.begin() as session:
                event = session.scalar(
                    select(OutboxEventORM)
                    .where(OutboxEventORM.id == event_id)
                    .where(OutboxEventORM.published_at.is_(None))
                    .with_for_update(skip_locked=True)
                )
                if event is None:
                    # уже опубликовано другим инстансом relay или прямой публикацией
                    return

                message = PredictionTaskMessage.from_payload(event.payload)
                publish_prediction_task(message)
                event.published_at = _utc_now()
                # SessionLocal.begin() auto-commits при успешном выходе
        except Exception:
            LOGGER.exception(
                "OutboxRelay: event_id=%s | ошибка публикации, попробуем в следующем цикле",
                event_id,
            )
