from __future__ import annotations

import logging
import time
from datetime import datetime
from decimal import Decimal

import pika

from technical_document_ml_service.core.config import app_settings
from technical_document_ml_service.domain.enums import TaskStatus
from technical_document_ml_service.messaging.contracts import WebhookDeliveryMessage
from technical_document_ml_service.messaging.rabbitmq import open_rabbitmq_connection
from technical_document_ml_service.services.webhook_service import send_task_webhook

LOGGER = logging.getLogger("technical_document_ml_service.webhook_consumer")


def _handle_webhook_message(
    channel: pika.adapters.blocking_connection.BlockingChannel,
    method: pika.spec.Basic.Deliver,
    _properties: pika.BasicProperties,
    body: bytes,
) -> None:
    """обработать одно webhook-уведомление из очереди

    Webhook — best-effort: всегда ack после попытки доставки.
    send_task_webhook уже содержит внутренние retry (3 попытки).
    """
    try:
        msg = WebhookDeliveryMessage.from_bytes(body)
        send_task_webhook(
            url=msg.callback_url,
            task_id=msg.task_id,
            status=TaskStatus(msg.status),
            model_name=msg.model_name,
            result_id=msg.result_id,
            spent_credits=Decimal(msg.spent_credits),
            completed_at=datetime.fromisoformat(msg.completed_at) if msg.completed_at else None,
            error_message=msg.error_message,
        )
    except Exception:
        LOGGER.exception("webhook_consumer: необработанная ошибка при обработке сообщения")
    finally:
        try:
            channel.basic_ack(delivery_tag=method.delivery_tag)
        except Exception:
            LOGGER.warning(
                "webhook_consumer: не удалось подтвердить сообщение — канал закрыт, "
                "RabbitMQ вернёт сообщение в очередь"
            )


def run_webhook_consumer_loop() -> None:
    """цикл потребления webhook-событий с автоматическим реподключением"""
    worker_id = app_settings.worker_id
    queue_name = app_settings.rabbitmq_webhook_queue_name
    reconnect_delay = app_settings.worker_reconnect_delay_seconds

    LOGGER.info(
        "worker_id=%s | Запуск webhook consumer | queue=%s",
        worker_id,
        queue_name,
    )

    while True:
        try:
            with open_rabbitmq_connection() as connection:
                channel = connection.channel()
                channel.queue_declare(queue=queue_name, durable=True)
                channel.basic_qos(prefetch_count=1)
                channel.basic_consume(
                    queue=queue_name,
                    on_message_callback=_handle_webhook_message,
                    auto_ack=False,
                )

                LOGGER.info(
                    "worker_id=%s | Webhook consumer подключён к RabbitMQ. Ожидание сообщений...",
                    worker_id,
                )
                channel.start_consuming()

        except KeyboardInterrupt:
            LOGGER.info("worker_id=%s | Webhook consumer остановлен.", worker_id)
            break
        except Exception as exc:
            LOGGER.exception(
                "worker_id=%s | Webhook consumer: потеря соединения: %s. Переподключение через %ds.",
                worker_id,
                exc,
                reconnect_delay,
            )
            time.sleep(reconnect_delay)
