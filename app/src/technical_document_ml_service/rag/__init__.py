"""rag — эмбеддинги, индекс, retrieval и генерация ответа.

Один и тот же код используется оффлайн-бенчмарком (`research/`) и продуктом
(воркер, `POST /ask`). В неделю 1 появляется только `embeddings` — провайдер
эмбеддингов с дисковым кэшем, нужный eval-харнессу.
"""

from technical_document_ml_service.rag.embeddings import (
    EmbeddingProvider,
    EmbeddingConfig,
    get_embedding_provider,
)

__all__ = ["EmbeddingProvider", "EmbeddingConfig", "get_embedding_provider"]
