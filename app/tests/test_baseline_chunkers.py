from __future__ import annotations

import pytest

from technical_document_ml_service.chunking.chunkers import (
    available_chunkers,
    get_chunker,
)
from technical_document_ml_service.chunking.chunkers.fixed_size import FixedSizeChunker
from technical_document_ml_service.chunking.chunkers.markdown_split import (
    MarkdownSplitChunker,
)
from technical_document_ml_service.chunking.chunkers.recursive import RecursiveChunker
from technical_document_ml_service.chunking.ir import (
    BBox,
    Block,
    BlockType,
    StructuredDocument,
)
from technical_document_ml_service.chunking.tokenization import count_tokens

_LOREM = (
    "Система должна обеспечивать обработку запросов в пределах установленного "
    "времени отклика при максимальной проектной нагрузке. "
)


def _doc() -> StructuredDocument:
    blocks = [
        Block("h1", BlockType.SECTION_HEADER, "1 Общие положения", 0,
              bbox=BBox(0, 0.1, 0.05, 0.9, 0.1), section_path=["1 Общие положения"]),
        Block("t1", BlockType.TEXT, _LOREM * 3, 0,
              bbox=BBox(0, 0.1, 0.12, 0.9, 0.3), section_path=["1 Общие положения"]),
        Block("h2", BlockType.SECTION_HEADER, "2 Требования", 1,
              bbox=BBox(1, 0.1, 0.05, 0.9, 0.1), section_path=["2 Требования"]),
        Block("t2", BlockType.TEXT, _LOREM * 4, 1,
              bbox=BBox(1, 0.1, 0.12, 0.9, 0.5), section_path=["2 Требования"]),
        Block("f1", BlockType.PAGE_FOOTER, "стр. 2 из 2", 1,
              section_path=[]),
    ]
    return StructuredDocument(doc_id="doc-1", source_filename="spec.pdf", blocks=blocks)


_CONTENT_IDS = {"h1", "t1", "h2", "t2"}  # без колонтитула f1


@pytest.mark.parametrize(
    "chunker",
    [
        FixedSizeChunker(target_tokens=20, overlap_tokens=4),
        RecursiveChunker(target_tokens=20, hard_max_tokens=40),
        MarkdownSplitChunker(target_tokens=20, hard_max_tokens=40),
    ],
    ids=["fixed_size", "recursive", "markdown_split"],
)
def test_chunker_produces_nonempty_chunks(chunker) -> None:
    chunks = chunker.chunk(_doc())
    assert chunks, "чанкер не должен возвращать пустой список на непустом документе"
    for c in chunks:
        assert c.text.strip()
        assert c.token_count == count_tokens(c.text)
        assert c.doc_id == "doc-1"


@pytest.mark.parametrize(
    "chunker",
    [
        FixedSizeChunker(target_tokens=20, overlap_tokens=4),
        RecursiveChunker(target_tokens=20, hard_max_tokens=40),
        MarkdownSplitChunker(target_tokens=20, hard_max_tokens=40),
    ],
    ids=["fixed_size", "recursive", "markdown_split"],
)
def test_chunker_respects_hard_max(chunker) -> None:
    for c in chunker.chunk(_doc()):
        assert c.token_count <= 40, f"чанк превысил hard-max: {c.token_count}"


@pytest.mark.parametrize(
    "chunker",
    [
        FixedSizeChunker(target_tokens=20, overlap_tokens=4),
        RecursiveChunker(target_tokens=20, hard_max_tokens=40),
        MarkdownSplitChunker(target_tokens=20, hard_max_tokens=40),
    ],
    ids=["fixed_size", "recursive", "markdown_split"],
)
def test_chunker_does_not_lose_content_blocks(chunker) -> None:
    # каждый контентный блок должен быть представлен хотя бы в одном чанке
    covered: set[str] = set()
    for c in chunker.chunk(_doc()):
        covered.update(c.block_ids)
    assert _CONTENT_IDS.issubset(covered), (
        f"потеряны блоки: {_CONTENT_IDS - covered}"
    )


def test_chunker_drops_page_footer() -> None:
    for name in ("fixed_size", "recursive", "markdown_split"):
        chunker = get_chunker(name)
        joined = " ".join(c.text for c in chunker.chunk(_doc()))
        assert "стр. 2 из 2" not in joined


def test_markdown_split_groups_by_section() -> None:
    chunks = MarkdownSplitChunker(target_tokens=512, hard_max_tokens=1024).chunk(_doc())
    paths = {tuple(c.section_path) for c in chunks}
    assert ("1 Общие положения",) in paths
    assert ("2 Требования",) in paths


def test_registry_exposes_three_baselines() -> None:
    for name in ("fixed_size", "recursive", "markdown_split"):
        assert name in available_chunkers()
        assert get_chunker(name).name == name
