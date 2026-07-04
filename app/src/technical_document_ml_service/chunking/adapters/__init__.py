"""Адаптеры парсеров → IR.

Каждый адаптер превращает сырой ответ конкретного парсера (Datalab, Docling, ...)
в `StructuredDocument`. Чанкеры и retrieval про парсеры не знают — только про IR.
"""

from technical_document_ml_service.chunking.adapters.base import (
    StructureAdapter,
    get_adapter,
    register_adapter,
)

# Импорт ради регистрации в реестре (side-effect).
from technical_document_ml_service.chunking.adapters import datalab_adapter  # noqa: E402,F401

__all__ = ["StructureAdapter", "register_adapter", "get_adapter"]
