"""Чанкеры: IR → список `Chunk`.

Все реализуют один ABC и регистрируются по имени, чтобы eval-харнесс перебирал
их строкой. Baseline-чанкеры (fixed_size, recursive, markdown_split) — точка
отсчёта; наши structure-aware/semantic появятся в неделях 2–3.
"""

from technical_document_ml_service.chunking.chunkers.base import (
    Chunker,
    available_chunkers,
    get_chunker,
    register_chunker,
)

# Импорт ради регистрации бейзлайнов (side-effect).
from technical_document_ml_service.chunking.chunkers import (  # noqa: E402,F401
    fixed_size,
    markdown_split,
    recursive,
)

__all__ = ["Chunker", "register_chunker", "get_chunker", "available_chunkers"]
