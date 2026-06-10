from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

from technical_document_ml_service.domain.exceptions import NotFoundError
from technical_document_ml_service.storage import ObjectNotFoundError, get_object_storage

if TYPE_CHECKING:
    from technical_document_ml_service.services.dto import TaskResultBundle

logger = logging.getLogger(__name__)

MAX_MARKDOWN_PREVIEW_CHARS = 200_000


@dataclass(frozen=True, slots=True)
class ArtifactFileDescriptor:
    """ссылка на артефакт в object storage"""

    storage_key: str
    mime_type: str | None


def get_task_artifact_descriptor(
    bundle: "TaskResultBundle",
    artifact_name: str,
) -> ArtifactFileDescriptor:
    """найти артефакт задачи по имени и вернуть его S3-ключ (защита от traversal встроена)"""
    artifact = next((a for a in bundle.artifacts if a.name == artifact_name), None)
    if artifact is None:
        raise NotFoundError(f"Артефакт '{artifact_name}' не найден.")

    artifacts_prefix = bundle.result.artifacts_dir if bundle.result else None
    key = resolve_artifact_key(artifact.path, artifacts_prefix=artifacts_prefix)
    if key is None:
        raise NotFoundError(f"Файл артефакта '{artifact_name}' недоступен.")

    return ArtifactFileDescriptor(storage_key=key, mime_type=artifact.mime_type)


def looks_like_markdown_artifact(artifact: dict[str, Any]) -> bool:
    """проверить, является ли артефакт Markdown-файлом"""
    name = str(artifact.get("name") or "").lower()
    path = str(artifact.get("path") or "").lower()
    kind = str(artifact.get("kind") or "").lower()
    mime_type = str(artifact.get("mime_type") or "").lower()

    return (
        name.endswith(".md")
        or path.endswith(".md")
        or "markdown" in name
        or "markdown" in kind
        or mime_type in {"text/markdown", "text/x-markdown"}
    )


def resolve_artifact_key(
    raw_key: Any,
    *,
    artifacts_prefix: str | None,
) -> str | None:
    """валидировать S3-ключ артефакта (защита от path traversal и выхода за префикс задачи)"""
    if not raw_key:
        return None

    key = str(raw_key)

    # отвергаем абсолютные пути и обход каталога
    if key.startswith("/") or ".." in PurePosixPath(key).parts:
        return None

    if artifacts_prefix:
        prefix = artifacts_prefix.rstrip("/")
        if key != prefix and not key.startswith(prefix + "/"):
            return None

    return key


def read_markdown_artifact(
    artifacts: list[dict[str, Any]],
    *,
    result: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """найти первый Markdown-артефакт и вернуть его содержимое с метаданными

    Возвращает dict с ключами: name, path, content, is_truncated — или None.
    """
    artifacts_prefix = result.get("artifacts_dir") if result is not None else None
    storage = get_object_storage()

    for artifact in artifacts:
        if not looks_like_markdown_artifact(artifact):
            continue

        key = resolve_artifact_key(artifact.get("path"), artifacts_prefix=artifacts_prefix)
        if key is None:
            continue

        try:
            content = storage.get_bytes(key).decode("utf-8", errors="replace")
        except ObjectNotFoundError:
            continue
        except Exception:
            logger.exception("Failed to read markdown artifact: %s", key)
            continue

        is_truncated = len(content) > MAX_MARKDOWN_PREVIEW_CHARS
        if is_truncated:
            content = (
                content[:MAX_MARKDOWN_PREVIEW_CHARS]
                + "\n\n<!-- Markdown preview was truncated in Web UI. -->"
            )

        return {
            "name": str(artifact.get("name") or PurePosixPath(key).name),
            "path": key,
            "content": content,
            "is_truncated": is_truncated,
        }

    return None
