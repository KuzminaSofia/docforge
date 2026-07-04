"""`StructureAdapter` ABC + реестр адаптеров.

Реестр по имени нужен, чтобы `parse_corpus` и продукт выбирали адаптер строкой
(из конфига/CLI), а не хардкодили класс.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from technical_document_ml_service.chunking.ir import StructuredDocument


class StructureAdapter(ABC):
    """Превращает сырой ответ парсера в нормализованный IR."""

    name: str

    @abstractmethod
    def to_ir(
        self, raw: dict, *, doc_id: str, source_filename: str
    ) -> StructuredDocument:
        """Сырой словарь парсера → `StructuredDocument`."""
        raise NotImplementedError


_REGISTRY: dict[str, StructureAdapter] = {}


def register_adapter(adapter: StructureAdapter) -> StructureAdapter:
    """Зарегистрировать экземпляр адаптера под его `name`."""
    if not getattr(adapter, "name", None):
        raise ValueError("adapter must define a non-empty `name`")
    _REGISTRY[adapter.name] = adapter
    return adapter


def get_adapter(name: str) -> StructureAdapter:
    """Достать адаптер по имени; понятная ошибка, если не зарегистрирован."""
    try:
        return _REGISTRY[name]
    except KeyError:
        available = ", ".join(sorted(_REGISTRY)) or "<none>"
        raise KeyError(
            f"unknown structure adapter {name!r}; registered: {available}"
        ) from None


def available_adapters() -> list[str]:
    return sorted(_REGISTRY)
