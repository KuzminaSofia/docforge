"""Провайдер эмбеддингов — единый и для eval, и для продукта.

Зафиксировано (architecture.md): Voyage `voyage-3-large`, 1024-dim, асимметрично
(`input_type=document` для чанков, `input_type=query` для вопросов). Fallback —
OpenAI `text-embedding-3-large` (3072-dim). Модель/размерность НЕ хардкодятся по
коду: они в `EmbeddingConfig`; при смене провайдера меняется только конфиг (и в
неделю 3 — размерность вектора в миграции pgvector).

Особенности:
- батч-эмбеддинг с дисковым кэшем (по умолчанию `research/data/embeddings/`),
  ключ = sha1(provider|model|input_type|text) — повторные прогоны бесплатны;
- сетевой вызов ленивый (через `requests`), чтобы импорт модуля не требовал ни
  ключа, ни пакета; тесты могут работать на кэше/стабе.
"""

from __future__ import annotations

import hashlib
import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

# repo_root/research/data/embeddings — дефолтный кэш (совпадает с architecture.md)
_DEFAULT_CACHE = (
    Path(__file__).resolve().parents[4] / "research" / "data" / "embeddings"
)

_VOYAGE_URL = "https://api.voyageai.com/v1/embeddings"
_OPENAI_URL = "https://api.openai.com/v1/embeddings"


@dataclass
class EmbeddingConfig:
    """Конфиг провайдера. Меняем здесь — не в коде чанкеров/retrieval."""

    provider: str = "voyage"  # "voyage" | "openai" | "local"
    model: str = "voyage-3-large"
    dim: int = 1024
    api_key_env: str = "APP_VOYAGE_API_KEY"
    batch_size: int = 128
    cache_dir: Path = field(default_factory=lambda: _DEFAULT_CACHE)
    timeout_s: int = 60

    @classmethod
    def voyage(cls) -> "EmbeddingConfig":
        return cls()

    @classmethod
    def openai(cls) -> "EmbeddingConfig":
        return cls(
            provider="openai",
            model="text-embedding-3-large",
            dim=3072,
            api_key_env="APP_OPENAI_API_KEY",
        )

    @classmethod
    def local(cls) -> "EmbeddingConfig":
        """Локальная модель через sentence-transformers — без API-ключа.

        multilingual-e5-large: 1024-dim (совпадает с зафиксированной размерностью,
        так что миграция pgvector не меняется), сильна на русском. Асимметрия — через
        префиксы `query:` / `passage:`, как и задумано для document/query.
        """
        return cls(
            provider="local",
            model="intfloat/multilingual-e5-large",
            dim=1024,
            api_key_env="",  # ключ не нужен
            batch_size=32,
        )


class EmbeddingProvider(ABC):
    """Асимметричный провайдер: документы и запросы кодируются разными input_type."""

    def __init__(self, config: EmbeddingConfig) -> None:
        self.config = config
        self._cache_dir = Path(config.cache_dir) / f"{config.provider}_{config.model}"

    @property
    def dim(self) -> int:
        return self.config.dim

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts, input_type="document")

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text], input_type="query")[0]

    # --- внутреннее -----------------------------------------------------------

    def _embed(self, texts: list[str], *, input_type: str) -> list[list[float]]:
        results: list[list[float] | None] = [None] * len(texts)
        misses: list[int] = []
        for i, text in enumerate(texts):
            cached = self._cache_get(text, input_type)
            if cached is not None:
                results[i] = cached
            else:
                misses.append(i)

        for start in range(0, len(misses), self.config.batch_size):
            batch_idx = misses[start : start + self.config.batch_size]
            batch_texts = [texts[i] for i in batch_idx]
            vectors = self._call_api(batch_texts, input_type=input_type)
            for i, vec in zip(batch_idx, vectors):
                results[i] = vec
                self._cache_put(texts[i], input_type, vec)

        return [v if v is not None else [0.0] * self.dim for v in results]

    def _cache_key(self, text: str, input_type: str) -> str:
        raw = f"{self.config.provider}|{self.config.model}|{input_type}|{text}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def _cache_path(self, text: str, input_type: str) -> Path:
        return self._cache_dir / input_type / f"{self._cache_key(text, input_type)}.json"

    def _cache_get(self, text: str, input_type: str) -> list[float] | None:
        path = self._cache_path(text, input_type)
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return None
        return None

    def _cache_put(self, text: str, input_type: str, vector: list[float]) -> None:
        path = self._cache_path(text, input_type)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.write_text(json.dumps(vector), encoding="utf-8")
        except OSError:
            pass  # кэш — оптимизация, не критично

    @abstractmethod
    def _call_api(self, texts: list[str], *, input_type: str) -> list[list[float]]:
        raise NotImplementedError

    def _require_key(self) -> str:
        key = os.environ.get(self.config.api_key_env)
        if not key:
            raise RuntimeError(
                f"нет ключа эмбеддингов: задай env {self.config.api_key_env}"
            )
        return key

    @staticmethod
    def _post_json(url: str, headers: dict, payload: dict, timeout_s: int) -> dict:
        import requests  # ленивый импорт — не тянем зависимость на уровне модуля

        resp = requests.post(url, headers=headers, json=payload, timeout=timeout_s)
        if resp.status_code >= 400:
            raise RuntimeError(
                f"embeddings API {resp.status_code}: {resp.text[:300]}"
            )
        return resp.json()


class VoyageProvider(EmbeddingProvider):
    def _call_api(self, texts: list[str], *, input_type: str) -> list[list[float]]:
        body = self._post_json(
            _VOYAGE_URL,
            headers={
                "Authorization": f"Bearer {self._require_key()}",
                "Content-Type": "application/json",
            },
            payload={
                "input": texts,
                "model": self.config.model,
                "input_type": input_type,  # document | query
            },
            timeout_s=self.config.timeout_s,
        )
        data = sorted(body.get("data", []), key=lambda d: d.get("index", 0))
        return [d["embedding"] for d in data]


class OpenAIProvider(EmbeddingProvider):
    # OpenAI не различает document/query — input_type игнорируется провайдером.
    def _call_api(self, texts: list[str], *, input_type: str) -> list[list[float]]:
        body = self._post_json(
            _OPENAI_URL,
            headers={
                "Authorization": f"Bearer {self._require_key()}",
                "Content-Type": "application/json",
            },
            payload={"input": texts, "model": self.config.model},
            timeout_s=self.config.timeout_s,
        )
        data = sorted(body.get("data", []), key=lambda d: d.get("index", 0))
        return [d["embedding"] for d in data]


class LocalProvider(EmbeddingProvider):
    """Локальные эмбеддинги через sentence-transformers (без API/сети на инференсе).

    Модель грузится один раз (ленивая). Для e5-семейства применяем префиксы
    `query:` / `passage:` — это и есть асимметрия document/query.
    """

    def __init__(self, config: EmbeddingConfig) -> None:
        super().__init__(config)
        self._model = None

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.config.model)
        return self._model

    def _prefix(self, text: str, input_type: str) -> str:
        # e5 требует префиксы; для не-e5 моделей они безвредны, но применяем
        # только к e5, чтобы не портить другие модели.
        if "e5" in self.config.model.lower():
            tag = "query: " if input_type == "query" else "passage: "
            return tag + text
        return text

    def _call_api(self, texts: list[str], *, input_type: str) -> list[list[float]]:
        model = self._get_model()
        prepared = [self._prefix(t, input_type) for t in texts]
        vectors = model.encode(
            prepared, normalize_embeddings=True, show_progress_bar=False
        )
        return [list(map(float, v)) for v in vectors]


_PROVIDERS = {
    "voyage": VoyageProvider,
    "openai": OpenAIProvider,
    "local": LocalProvider,
}


def get_embedding_provider(
    config: EmbeddingConfig | None = None,
) -> EmbeddingProvider:
    """Фабрика провайдера. По умолчанию Voyage; можно передать свой конфиг."""
    config = config or EmbeddingConfig.voyage()
    try:
        provider_cls = _PROVIDERS[config.provider]
    except KeyError:
        raise ValueError(
            f"unknown embedding provider {config.provider!r}; "
            f"available: {', '.join(sorted(_PROVIDERS))}"
        ) from None
    return provider_cls(config)
