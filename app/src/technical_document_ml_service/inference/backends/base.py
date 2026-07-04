from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from technical_document_ml_service.inference.contracts import BackendRequest, BackendResult


class PredictionBackend(ABC):
    """базовый интерфейс backend-обработчика

    Бэкенды бывают двух типов:
    - синхронные (локальный счёт, напр. Docling): реализуют только `process()`;
    - удалённые/async (`is_remote=True`, напр. Datalab): дополнительно реализуют
      `submit()` + `fetch()`, чтобы воркер не блокировал слот на ожидании.
      `process()` у них = синхронная композиция submit+fetch (для sync-вызовов/тестов).
    """

    backend_name: str | None = None
    # удалённый backend: долгий счёт идёт на чужой стороне, обработка двухфазная
    is_remote: bool = False

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not getattr(cls, "backend_name", None):
            raise TypeError(
                f"{cls.__name__} must define non-empty 'backend_name'"
            )

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config: dict[str, Any] = dict(config or {})

    @property
    def name(self) -> str:
        """вернуть системное имя backend"""
        return str(self.backend_name)

    @property
    def config(self) -> dict[str, Any]:
        """вернуть конфигурацию backend"""
        return dict(self._config)

    @abstractmethod
    def process(self, request: BackendRequest) -> BackendResult:
        """выполнить обработку запроса (синхронно, до получения результата)"""
        raise NotImplementedError

    def submit(self, request: BackendRequest) -> dict[str, Any]:
        """фаза 1 (только remote): запустить удалённую задачу, вернуть handle (JSON)"""
        raise NotImplementedError(
            f"submit() поддерживается только remote-backend'ами (is_remote=True); "
            f"{type(self).__name__} синхронный."
        )

    def fetch(
        self, request: BackendRequest, handle: dict[str, Any]
    ) -> BackendResult | None:
        """фаза 2 (только remote): опросить результат по handle

        Возвращает BackendResult когда задача готова, либо None если ещё считается.
        """
        raise NotImplementedError(
            f"fetch() поддерживается только remote-backend'ами (is_remote=True); "
            f"{type(self).__name__} синхронный."
        )