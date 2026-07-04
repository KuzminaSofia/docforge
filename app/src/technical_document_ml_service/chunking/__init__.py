"""chunking — нормализованный IR документа, адаптеры парсеров и чанкеры.

Слой между парсером (Datalab/Docling) и retrieval. Продукт и оффлайн-бенчмарк
(`research/`) используют один и тот же код отсюда — «двух реализаций» нет.

Публичный контракт:
- `ir` — `BBox`, `BlockType`, `Block`, `StructuredDocument` (стабильная схема).
- `chunk` — `Chunk` (единица выхода любого чанкера).
- `tokenization` — единый `count_tokens` + константы размера чанка.
"""

from technical_document_ml_service.chunking.chunk import Chunk
from technical_document_ml_service.chunking.ir import (
    BBox,
    Block,
    BlockType,
    StructuredDocument,
)
from technical_document_ml_service.chunking.tokenization import (
    HARD_MAX_CHUNK_TOKENS,
    TARGET_CHUNK_TOKENS,
    count_tokens,
)

__all__ = [
    "BBox",
    "Block",
    "BlockType",
    "StructuredDocument",
    "Chunk",
    "count_tokens",
    "TARGET_CHUNK_TOKENS",
    "HARD_MAX_CHUNK_TOKENS",
]
