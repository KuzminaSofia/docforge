from __future__ import annotations

import os
from dataclasses import dataclass


def _get_bool_env(name: str, default: bool) -> bool:
    """прочитать булево значение из env"""
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class AppSettings:
    """основные настройки приложения"""

    uploads_dir: str
    artifacts_dir: str
    default_prediction_backend: str

    storage_backend: str
    storage_filesystem_root: str
    s3_endpoint_url: str
    s3_bucket: str
    s3_access_key: str
    s3_secret_key: str
    s3_region: str
    s3_use_ssl: bool

    rabbitmq_host: str
    rabbitmq_port: int
    rabbitmq_user: str
    rabbitmq_password: str
    rabbitmq_virtual_host: str
    rabbitmq_queue_name: str
    rabbitmq_webhook_queue_name: str
    rabbitmq_heartbeat: int
    rabbitmq_blocked_connection_timeout: int
    rabbitmq_prefetch_count: int
    rabbitmq_ssl_enabled: bool

    max_upload_file_size_mb: int
    max_task_total_size_mb: int

    worker_id: str
    worker_reconnect_delay_seconds: int
    worker_task_timeout_seconds: int

    outbox_poll_interval_seconds: int


def load_app_settings() -> AppSettings:
    """загрузить настройки приложения из переменных окружения"""
    # трактуются как префиксы ключей object storage (а не пути ФС)
    return AppSettings(
        uploads_dir=os.getenv("APP_UPLOADS_DIR", "uploads"),
        artifacts_dir=os.getenv("APP_ARTIFACTS_DIR", "artifacts"),
        default_prediction_backend=os.getenv(
            "APP_DEFAULT_PREDICTION_BACKEND",
            "docling",
        ),
        storage_backend=os.getenv("APP_STORAGE_BACKEND", "s3"),
        storage_filesystem_root=os.getenv("APP_STORAGE_FS_ROOT", "storage"),
        s3_endpoint_url=os.getenv("APP_S3_ENDPOINT_URL", "http://minio:9000"),
        s3_bucket=os.getenv("APP_S3_BUCKET", "technical-documents"),
        s3_access_key=os.getenv("APP_S3_ACCESS_KEY", "minioadmin"),
        s3_secret_key=os.getenv("APP_S3_SECRET_KEY", "minioadmin"),
        s3_region=os.getenv("APP_S3_REGION", "us-east-1"),
        s3_use_ssl=_get_bool_env("APP_S3_USE_SSL", False),
        rabbitmq_host=os.getenv("RABBITMQ_HOST", "rabbitmq"),
        rabbitmq_port=int(os.getenv("RABBITMQ_PORT", "5672")),
        rabbitmq_user=os.getenv("RABBITMQ_USER", "guest"),
        rabbitmq_password=os.getenv("RABBITMQ_PASSWORD", "guest"),
        rabbitmq_virtual_host=os.getenv("RABBITMQ_VHOST", "/"),
        rabbitmq_queue_name=os.getenv(
            "RABBITMQ_PREDICTION_QUEUE",
            "technical_document_prediction_tasks",
        ),
        rabbitmq_webhook_queue_name=os.getenv(
            "RABBITMQ_WEBHOOK_QUEUE",
            "technical_document_webhook_delivery",
        ),
        rabbitmq_heartbeat=int(os.getenv("RABBITMQ_HEARTBEAT", "60")),
        rabbitmq_blocked_connection_timeout=int(
            os.getenv("RABBITMQ_BLOCKED_CONNECTION_TIMEOUT", "30")
        ),
        rabbitmq_prefetch_count=int(os.getenv("RABBITMQ_PREFETCH_COUNT", "1")),
        rabbitmq_ssl_enabled=_get_bool_env("RABBITMQ_SSL_ENABLED", False),
        max_upload_file_size_mb=int(os.getenv("APP_MAX_UPLOAD_FILE_SIZE_MB", "50")),
        max_task_total_size_mb=int(os.getenv("APP_MAX_TASK_TOTAL_SIZE_MB", "200")),
        worker_id=os.getenv("WORKER_ID", "worker-unknown"),
        worker_reconnect_delay_seconds=int(os.getenv("WORKER_RECONNECT_DELAY_SECONDS", "5")),
        worker_task_timeout_seconds=int(os.getenv("WORKER_TASK_TIMEOUT_SECONDS", "600")),
        outbox_poll_interval_seconds=int(os.getenv("APP_OUTBOX_POLL_INTERVAL_SECONDS", "60")),
    )


app_settings = load_app_settings()