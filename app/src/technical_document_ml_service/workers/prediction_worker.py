from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable
from typing import Any

import pika

from technical_document_ml_service.core.config import app_settings
from technical_document_ml_service.db.session import SessionLocal
from technical_document_ml_service.domain.exceptions import NotFoundError
from technical_document_ml_service.messaging.contracts import PredictionTaskMessage
from technical_document_ml_service.messaging.rabbitmq import (
    configure_consumer_qos,
    declare_prediction_queue,
    open_rabbitmq_connection,
)
from technical_document_ml_service.services.prediction_processing_service import (
    process_document_prediction_task,
)


LOGGER = logging.getLogger("technical_document_ml_service.prediction_worker")


def _configure_logging() -> None:
    """настроить базовое логирование воркера"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def _get_worker_id() -> str:
    """получить идентификатор воркера из окружения"""
    return os.getenv("WORKER_ID", "worker-unknown")


def _get_reconnect_delay_seconds() -> int:
    """получить интервал ожидания перед повторным подключением"""
    return int(os.getenv("WORKER_RECONNECT_DELAY_SECONDS", "5"))


def _ack_message(
    channel: pika.adapters.blocking_connection.BlockingChannel,
    delivery_tag: int,
) -> None:
    """подтвердить успешную обработку сообщения"""
    channel.basic_ack(delivery_tag=delivery_tag)


def _reject_message(
    channel: pika.adapters.blocking_connection.BlockingChannel,
    delivery_tag: int,
    *,
    requeue: bool,
) -> None:
    """отклонить сообщение"""
    channel.basic_nack(delivery_tag=delivery_tag, requeue=requeue)


def _handle_message(
    worker_id: str,
    channel: pika.adapters.blocking_connection.BlockingChannel,
    method: pika.spec.Basic.Deliver,
    _properties: pika.BasicProperties,
    body: bytes,
) -> None:
    """обработать одно сообщение из очереди

    ML-инференс запускается в отдельном потоке, чтобы главный поток мог
    продолжать качать heartbeat RabbitMQ. Иначе BlockingConnection теряет
    соединение при задачах длиннее 2×heartbeat (≈120 с).
    """
    delivery_tag = method.delivery_tag

    try:
        message = PredictionTaskMessage.from_bytes(body)
    except Exception as exc:
        LOGGER.exception(
            "worker_id=%s | Некорректное сообщение в очереди: %s",
            worker_id,
            exc,
        )
        _reject_message(channel, delivery_tag, requeue=False)
        return

    outcome: dict[str, Any] = {}

    def _run_in_thread() -> None:
        session = SessionLocal()
        try:
            result = process_document_prediction_task(
                session,
                task_id=message.task_id,
                redelivered=method.redelivered,
            )
            LOGGER.info(
                "worker_id=%s | task_id=%s | status=%s | was_processed=%s | message=%s",
                worker_id,
                result.task_id,
                result.status.value,
                result.was_processed,
                result.message,
            )
            outcome["ok"] = result
        except NotFoundError as exc:
            LOGGER.error(
                "worker_id=%s | task_id=%s | Задача не найдена: %s",
                worker_id,
                message.task_id,
                exc,
            )
            # задача не найдена — никаких коммитов не было, откатываем грязное состояние
            session.rollback()
            outcome["not_found"] = True
        except Exception as exc:
            LOGGER.exception(
                "worker_id=%s | task_id=%s | Ошибка обработки задачи: %s",
                worker_id,
                message.task_id,
                exc,
            )
            # сервис уже вызвал rollback и зафиксировал FAILED-статус самостоятельно;
            # только страховочный rollback на случай сбоя внутри _mark_task_as_failed
            session.rollback()
            outcome["error"] = True
        finally:
            session.close()

    thread = threading.Thread(target=_run_in_thread, daemon=True)
    thread.start()

    # Пока поток работает — качаем heartbeat, чтобы не потерять соединение
    try:
        while thread.is_alive():
            channel.connection.process_data_events(time_limit=1)
    except Exception:
        thread.join()
        raise

    thread.join()

    # Ack/nack вызываем из главного потока — канал жив, heartbeat поддержан
    if "ok" in outcome:
        _ack_message(channel, delivery_tag)
    elif "not_found" in outcome:
        _reject_message(channel, delivery_tag, requeue=False)
    elif method.redelivered:
        LOGGER.error(
            "worker_id=%s | task_id=%s | Повторная обработка снова завершилась ошибкой. "
            "Сообщение будет отклонено без requeue, чтобы избежать бесконечного цикла.",
            worker_id,
            message.task_id,
        )
        _reject_message(channel, delivery_tag, requeue=False)
    else:
        LOGGER.info(
            "worker_id=%s | task_id=%s | Сообщение будет возвращено в очередь для повторной попытки.",
            worker_id,
            message.task_id,
        )
        _reject_message(channel, delivery_tag, requeue=True)


def _build_message_handler(
    worker_id: str,
) -> Callable[
    [
        pika.adapters.blocking_connection.BlockingChannel,
        pika.spec.Basic.Deliver,
        pika.BasicProperties,
        bytes,
    ],
    None,
]:
    """построить callback обработки сообщений для конкретного воркера"""

    def callback(
        channel: pika.adapters.blocking_connection.BlockingChannel,
        method: pika.spec.Basic.Deliver,
        properties: pika.BasicProperties,
        body: bytes,
    ) -> None:
        _handle_message(
            worker_id=worker_id,
            channel=channel,
            method=method,
            _properties=properties,
            body=body,
        )

    return callback


def run_prediction_worker() -> None:
    """запустить worker для обработки задач предсказания"""
    _configure_logging()

    worker_id = _get_worker_id()
    reconnect_delay_seconds = _get_reconnect_delay_seconds()
    message_handler = _build_message_handler(worker_id)

    LOGGER.info(
        "worker_id=%s | Запуск worker-а обработки задач | queue=%s",
        worker_id,
        app_settings.rabbitmq_queue_name,
    )

    while True:
        try:
            with open_rabbitmq_connection() as connection:
                channel = connection.channel()

                declare_prediction_queue(channel)
                configure_consumer_qos(channel)

                channel.basic_consume(
                    queue=app_settings.rabbitmq_queue_name,
                    on_message_callback=message_handler,
                    auto_ack=False,
                )

                LOGGER.info(
                    "worker_id=%s | Подключение к RabbitMQ установлено. Ожидание сообщений...",
                    worker_id,
                )

                try:
                    channel.start_consuming()
                except KeyboardInterrupt:
                    LOGGER.info(
                        "worker_id=%s | Получен сигнал остановки. Завершаем worker.",
                        worker_id,
                    )
                    channel.stop_consuming()
                    break
                finally:
                    if channel.is_open:
                        channel.close()

        except KeyboardInterrupt:
            LOGGER.info(
                "worker_id=%s | Worker остановлен пользователем.",
                worker_id,
            )
            break
        except Exception as exc:
            LOGGER.exception(
                "worker_id=%s | Не удалось подключиться к RabbitMQ или соединение было потеряно: %s",
                worker_id,
                exc,
            )
            LOGGER.info(
                "worker_id=%s | Повторная попытка подключения через %s сек.",
                worker_id,
                reconnect_delay_seconds,
            )
            time.sleep(reconnect_delay_seconds)


if __name__ == "__main__":
    run_prediction_worker()