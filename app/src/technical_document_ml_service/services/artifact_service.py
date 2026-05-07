from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MAX_MARKDOWN_PREVIEW_CHARS = 200_000


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


def resolve_artifact_path(
    artifact: dict[str, Any],
    *,
    artifacts_dir: str | None,
) -> Path | None:
    """восстановить и валидировать путь к артефакту (защита от path traversal)"""
    raw_path = artifact.get("path")
    if not raw_path:
        return None

    root = Path(artifacts_dir).resolve() if artifacts_dir else None
    candidate = Path(str(raw_path))

    if not candidate.is_absolute():
        if root is None:
            return None
        candidate = root / candidate

    try:
        resolved = candidate.resolve()
    except OSError:
        return None

    if root is not None and not resolved.is_relative_to(root):
        return None

    if not resolved.is_file():
        return None

    return resolved


def read_markdown_artifact(
    artifacts: list[dict[str, Any]],
    *,
    result: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """найти первый Markdown-артефакт и вернуть его содержимое с метаданными

    Возвращает dict с ключами: name, path, content, is_truncated — или None.
    """
    artifacts_dir = result.get("artifacts_dir") if result is not None else None

    for artifact in artifacts:
        if not looks_like_markdown_artifact(artifact):
            continue

        artifact_path = resolve_artifact_path(artifact, artifacts_dir=artifacts_dir)
        if artifact_path is None:
            continue

        try:
            content = artifact_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            logger.exception("Failed to read markdown artifact: %s", artifact_path)
            continue

        is_truncated = len(content) > MAX_MARKDOWN_PREVIEW_CHARS
        if is_truncated:
            content = (
                content[:MAX_MARKDOWN_PREVIEW_CHARS]
                + "\n\n<!-- Markdown preview was truncated in Web UI. -->"
            )

        return {
            "name": str(artifact.get("name") or artifact_path.name),
            "path": str(artifact_path),
            "content": content,
            "is_truncated": is_truncated,
        }

    return None
