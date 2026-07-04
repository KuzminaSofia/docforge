"""Фоновый reconciler удалённых inference-задач.

Опрашивает off-slot задачи в статусе `pending` (таблица remote_inference_jobs):
сетевой опрос результата и продвижение задачи (готово / таймаут / ещё считается)
вынесены в `reconcile_remote_job`. Этот модуль — только планировщик-цикл, по образцу
`OutboxRelay`. Несколько инстансов безопасны: reconcile_remote_job берёт SKIP LOCKED.
"""

from __future__ import annotations

import logging
import threading
import uuid

from sqlalchemy import select

from technical_document_ml_service.db.models import MLRemoteInferenceJobORM
from technical_document_ml_service.db.session import SessionLocal, read_session
from technical_document_ml_service.domain.enums import RemoteJobStatus
from technical_document_ml_service.services.prediction_processing_service import (
    reconcile_remote_job,
)

LOGGER = logging.getLogger("technical_document_ml_service.remote_job_reconciler")


class RemoteJobReconciler:
    """фоновый поток, опрашивающий незавершённые remote-задачи и продвигающий их"""

    def __init__(self, *, poll_interval: int = 5, batch_size: int = 20) -> None:
        self._poll_interval = poll_interval
        self._batch_size = batch_size
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="remote-job-reconciler",
            daemon=True,
        )
        self._thread.start()
        LOGGER.info(
            "RemoteJobReconciler запущен (интервал=%ds, батч=%d)",
            self._poll_interval,
            self._batch_size,
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=15)
            self._thread = None
        LOGGER.info("RemoteJobReconciler остановлен")

    def _run(self) -> None:
        while not self._stop_event.wait(self._poll_interval):
            try:
                self._reconcile_pending()
            except Exception:
                LOGGER.exception("RemoteJobReconciler: необработанная ошибка в цикле опроса")

    def _reconcile_pending(self) -> None:
        # быстрый скан id'шек без блокировок
        with read_session() as session:
            pending_ids: list[uuid.UUID] = list(
                session.scalars(
                    select(MLRemoteInferenceJobORM.id)
                    .where(MLRemoteInferenceJobORM.status == RemoteJobStatus.PENDING.value)
                    .order_by(MLRemoteInferenceJobORM.created_at)
                    .limit(self._batch_size)
                )
            )

        for job_id in pending_ids:
            if self._stop_event.is_set():
                break
            self._reconcile_one(job_id)

    def _reconcile_one(self, job_id: uuid.UUID) -> None:
        session = SessionLocal()
        try:
            reconcile_remote_job(session, job_id=job_id)
        except Exception:
            LOGGER.exception(
                "RemoteJobReconciler: job_id=%s | ошибка, повтор на следующем цикле",
                job_id,
            )
            session.rollback()
        finally:
            session.close()
