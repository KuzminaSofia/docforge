from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class PredictionTaskMessage:
    """
    сообщение о постановке ML-зачи в очередь
    тяжелые данные хранятся в БД и storage
    """

    task_id: UUID
    user_id: UUID
    model_name: str
    timestamp: datetime
    version: int = 1

    def to_payload(self) -> dict[str, str | int]:
        """преобразовать сообщение в сериализуемый словарь"""
        return {
            "version": self.version,
            "task_id": str(self.task_id),
            "user_id": str(self.user_id),
            "model_name": self.model_name,
            "timestamp": self.timestamp.astimezone(UTC).isoformat(),
        }

    def to_json(self) -> str:
        """сериализовать сообщение в JSON-строку"""
        return json.dumps(
            self.to_payload(),
            ensure_ascii=False,
            separators=(",", ":"),
        )

    def to_bytes(self) -> bytes:
        """сериализовать сообщение в байты для отправки в RabbitMQ"""
        return self.to_json().encode("utf-8")

    @classmethod
    def from_payload(cls, payload: dict[str, str | int]) -> "PredictionTaskMessage":
        """создать сообщение из словаря"""
        return cls(
            version=int(payload["version"]),
            task_id=UUID(str(payload["task_id"])),
            user_id=UUID(str(payload["user_id"])),
            model_name=str(payload["model_name"]),
            timestamp=datetime.fromisoformat(str(payload["timestamp"])),
        )

    @classmethod
    def from_json(cls, raw_json: str) -> "PredictionTaskMessage":
        """создать сообщение из JSON-строки"""
        payload = json.loads(raw_json)
        if not isinstance(payload, dict):
            raise ValueError("Некорректный формат сообщения очереди.")
        return cls.from_payload(payload)

    @classmethod
    def from_bytes(cls, raw_bytes: bytes) -> "PredictionTaskMessage":
        """создать сообщение из байтового представления"""
        return cls.from_json(raw_bytes.decode("utf-8"))


@dataclass(frozen=True, slots=True)
class WebhookDeliveryMessage:
    """сообщение для доставки webhook-уведомления через отдельную очередь"""

    task_id: UUID
    callback_url: str
    status: str           # TaskStatus.value
    model_name: str
    result_id: UUID | None
    spent_credits: str    # str(Decimal)
    completed_at: str | None  # ISO-8601 или None
    error_message: str | None
    version: int = 1

    def to_payload(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "task_id": str(self.task_id),
            "callback_url": self.callback_url,
            "status": self.status,
            "model_name": self.model_name,
            "result_id": str(self.result_id) if self.result_id is not None else None,
            "spent_credits": self.spent_credits,
            "completed_at": self.completed_at,
            "error_message": self.error_message,
        }

    def to_bytes(self) -> bytes:
        return json.dumps(
            self.to_payload(),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "WebhookDeliveryMessage":
        result_id_raw = payload.get("result_id")
        completed_at_raw = payload.get("completed_at")
        error_message_raw = payload.get("error_message")
        return cls(
            version=int(payload.get("version", 1)),
            task_id=UUID(str(payload["task_id"])),
            callback_url=str(payload["callback_url"]),
            status=str(payload["status"]),
            model_name=str(payload["model_name"]),
            result_id=UUID(result_id_raw) if result_id_raw else None,
            spent_credits=str(payload["spent_credits"]),
            completed_at=str(completed_at_raw) if completed_at_raw else None,
            error_message=str(error_message_raw) if error_message_raw else None,
        )

    @classmethod
    def from_bytes(cls, raw_bytes: bytes) -> "WebhookDeliveryMessage":
        payload = json.loads(raw_bytes.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Некорректный формат webhook-сообщения.")
        return cls.from_payload(payload)