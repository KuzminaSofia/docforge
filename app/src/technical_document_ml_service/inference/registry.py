from __future__ import annotations

from collections.abc import Callable
from typing import Any

from technical_document_ml_service.inference.backends.base import PredictionBackend
from technical_document_ml_service.inference.backends.datalab_backend import (
    create_datalab_backend,
)
from technical_document_ml_service.inference.backends.docling_backend import (
    create_docling_backend,
)
from technical_document_ml_service.inference.exceptions import BackendNotFoundError


BackendFactory = Callable[[dict[str, Any] | None], PredictionBackend]


class BackendRegistry:
    """реестр доступных backend-обработчиков"""

    def __init__(self) -> None:
        self._factories: dict[str, BackendFactory] = {}

    def register(
        self,
        *,
        name: str,
        factory: BackendFactory,
        overwrite: bool = False,
    ) -> None:
        """зарегистрировать фабрику backend-а"""
        normalized_name = name.strip().lower()

        if not overwrite and normalized_name in self._factories:
            raise ValueError(f"Backend '{normalized_name}' уже зарегистрирован.")

        self._factories[normalized_name] = factory

    def create(
        self,
        *,
        name: str,
        config: dict[str, Any] | None = None,
    ) -> PredictionBackend:
        """создать backend по зарегистрированному имени"""
        normalized_name = name.strip().lower()

        factory = self._factories.get(normalized_name)
        if factory is None:
            available = ", ".join(sorted(self._factories))
            raise BackendNotFoundError(
                f"Backend '{normalized_name}' не найден. "
                f"Доступные backend-ы: {available or 'none'}."
            )

        return factory(config)

    def names(self) -> tuple[str, ...]:
        """вернуть список имен зарегистрированных backend-ов"""
        return tuple(sorted(self._factories.keys()))


DOCLING_BACKEND_NAME = "docling"
DATALAB_BACKEND_NAME = "datalab"
TECHNICAL_DOCUMENT_MODEL_KIND = "technical_document_extraction"


def build_default_backend_registry() -> BackendRegistry:
    """создать реестр со стандартными backend-ами приложения"""
    registry = BackendRegistry()
    registry.register(name=DOCLING_BACKEND_NAME, factory=create_docling_backend)
    registry.register(name=DATALAB_BACKEND_NAME, factory=create_datalab_backend)
    return registry


DEFAULT_BACKEND_REGISTRY = build_default_backend_registry()