"""`Chunker` ABC + реестр + общие помощники сборки `Chunk`.

Реестр по имени — чтобы `run_retrieval` перебирал чанкеры строкой (`--chunker`).
Помощники (`build_chunk`, `prefix_with_section_path`) держат единый формат текста
чанка и метаданных, чтобы сравнение было честным.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from technical_document_ml_service.chunking.chunk import Chunk
from technical_document_ml_service.chunking.ir import BBox, Block, StructuredDocument
from technical_document_ml_service.chunking.tokenization import count_tokens


class Chunker(ABC):
    """Разбивает `StructuredDocument` на список `Chunk`."""

    name: str

    @abstractmethod
    def chunk(self, doc: StructuredDocument) -> list[Chunk]:
        raise NotImplementedError


_REGISTRY: dict[str, Chunker] = {}


def register_chunker(chunker: Chunker) -> Chunker:
    if not getattr(chunker, "name", None):
        raise ValueError("chunker must define a non-empty `name`")
    _REGISTRY[chunker.name] = chunker
    return chunker


def get_chunker(name: str) -> Chunker:
    try:
        return _REGISTRY[name]
    except KeyError:
        available = ", ".join(sorted(_REGISTRY)) or "<none>"
        raise KeyError(
            f"unknown chunker {name!r}; registered: {available}"
        ) from None


def available_chunkers() -> list[str]:
    return sorted(_REGISTRY)


# --- общие помощники сборки чанка ---------------------------------------------


def prefix_with_section_path(text: str, section_path: Sequence[str]) -> str:
    """Префикс из «хлебных крошек» — контекст секции идёт в эмбеддинг.

    Одинаков для всех чанкеров, иначе тексты (а значит и эмбеддинги) несравнимы.
    """
    if not section_path:
        return text
    crumbs = " > ".join(s for s in section_path if s)
    return f"{crumbs}\n\n{text}" if crumbs else text


def concat_with_spans(
    blocks: Sequence[Block], separator: str = "\n\n"
) -> tuple[str, list[tuple[int, int, Block]]]:
    """Склеить текст блоков и вернуть (текст, [(start, end, block)]).

    Позволяет чанкерам, работающим на плоском тексте (fixed_size, recursive),
    восстановить, какие блоки попали в чанк по символьному диапазону.
    """
    parts: list[str] = []
    spans: list[tuple[int, int, Block]] = []
    cursor = 0
    for b in blocks:
        if not b.text:
            continue
        if parts:
            cursor += len(separator)
        start = cursor
        end = start + len(b.text)
        spans.append((start, end, b))
        parts.append(b.text)
        cursor = end
    return separator.join(parts), spans


def blocks_in_span(
    spans: Sequence[tuple[int, int, Block]], start: int, end: int
) -> list[Block]:
    """Блоки, чьи символьные диапазоны пересекаются с [start, end)."""
    hit: list[Block] = []
    for s, e, block in spans:
        if s < end and e > start:  # пересечение
            hit.append(block)
    return hit


def build_chunk(
    *,
    doc_id: str,
    index: int,
    text: str,
    chunker_name: str,
    block_ids: Sequence[str] | None = None,
    section_path: Sequence[str] | None = None,
    blocks: Sequence[Block] | None = None,
    extra_metadata: dict | None = None,
) -> Chunk:
    """Собрать `Chunk` c единым форматом текста/метаданных.

    Если переданы `blocks` — из них выводятся block_ids, page_range, bbox_union.
    `text` — «сырой» текст; префикс section_path добавляется здесь.
    """
    section_path = list(section_path or [])
    prefixed = prefix_with_section_path(text, section_path)

    ids = list(block_ids or [])
    pages: list[int] = []
    bboxes: list[BBox] = []
    if blocks:
        for b in blocks:
            if not ids:
                pass
            pages.append(b.page_no)
            if b.bbox is not None:
                bboxes.append(b.bbox)
        if not ids:
            ids = [b.id for b in blocks]
    page_range = (min(pages), max(pages)) if pages else (0, 0)

    metadata = {"chunker": chunker_name}
    if extra_metadata:
        metadata.update(extra_metadata)

    return Chunk(
        id=f"{doc_id}::{chunker_name}::{index}",
        doc_id=doc_id,
        text=prefixed,
        token_count=count_tokens(prefixed),
        block_ids=ids,
        section_path=section_path,
        page_range=page_range,
        bbox_union=bboxes,
        metadata=metadata,
    )
