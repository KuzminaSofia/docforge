"""Baseline: рекурсивный сплит по разделителям (RecursiveCharacterTextSplitter-стиль).

Текст режется по убывающей иерархии разделителей (абзац → строка → предложение →
слово), пока куски не влезут в hard-max, затем соседние куски жадно сливаются до
~target токенов. Структуру IR игнорирует (кроме отбрасывания колонтитулов).
"""

from __future__ import annotations

from technical_document_ml_service.chunking.chunk import Chunk
from technical_document_ml_service.chunking.chunkers.base import (
    Chunker,
    blocks_in_span,
    build_chunk,
    concat_with_spans,
    register_chunker,
)
from technical_document_ml_service.chunking.ir import StructuredDocument
from technical_document_ml_service.chunking.tokenization import (
    HARD_MAX_CHUNK_TOKENS,
    TARGET_CHUNK_TOKENS,
    count_tokens,
)

_SEPARATORS = ["\n\n", "\n", ". ", " "]


class RecursiveChunker(Chunker):
    name = "recursive"

    def __init__(
        self,
        target_tokens: int = TARGET_CHUNK_TOKENS,
        hard_max_tokens: int = HARD_MAX_CHUNK_TOKENS,
    ) -> None:
        self.target_tokens = target_tokens
        self.hard_max_tokens = hard_max_tokens

    def chunk(self, doc: StructuredDocument) -> list[Chunk]:
        content = [
            b
            for b in doc.blocks
            if b.text and b.type.value not in ("page_header", "page_footer")
        ]
        text, spans = concat_with_spans(content)
        if not text.strip():
            return []

        # 1) рекурсивно нарезать на атомы <= hard_max, сохраняя абсолютные offset'ы
        atoms = self._split(text, 0, _SEPARATORS)
        # 2) жадно слить соседние атомы до target
        merged = self._merge(text, atoms)

        chunks: list[Chunk] = []
        for idx, (start, end) in enumerate(merged):
            piece = text[start:end].strip()
            if not piece:
                continue
            src_blocks = blocks_in_span(spans, start, end)
            chunks.append(
                build_chunk(
                    doc_id=doc.doc_id,
                    index=idx,
                    text=piece,
                    chunker_name=self.name,
                    blocks=src_blocks,
                    section_path=src_blocks[0].section_path if src_blocks else [],
                )
            )
        return chunks

    def _split(
        self, segment: str, base_offset: int, separators: list[str]
    ) -> list[tuple[int, int]]:
        """Вернуть непересекающиеся [start,end) с абсолютными offset'ами, <= hard_max.

        `segment` — текст для нарезки, `base_offset` — его абсолютная позиция в
        исходном полном тексте (чтобы offset'ы были глобальными).
        """
        if count_tokens(segment) <= self.hard_max_tokens:
            return [(base_offset, base_offset + len(segment))]
        if not separators:
            # нечем резать — рубим по символам примерно по hard_max
            return self._hard_split_by_chars(segment, base_offset)

        sep = separators[0]
        rest = separators[1:]
        if sep not in segment:
            return self._split(segment, base_offset, rest)

        result: list[tuple[int, int]] = []
        cursor = 0
        pieces = segment.split(sep)
        for i, piece in enumerate(pieces):
            piece_start = base_offset + cursor
            piece_len = len(piece)
            if piece.strip():
                if count_tokens(piece) <= self.hard_max_tokens:
                    result.append((piece_start, piece_start + piece_len))
                else:
                    result.extend(self._split(piece, piece_start, rest))
            cursor += piece_len + len(sep)
        return result

    def _hard_split_by_chars(
        self, segment: str, base_offset: int
    ) -> list[tuple[int, int]]:
        approx_chars = max(1, self.hard_max_tokens * 4)
        out: list[tuple[int, int]] = []
        pos = 0
        while pos < len(segment):
            end = min(len(segment), pos + approx_chars)
            out.append((base_offset + pos, base_offset + end))
            pos = end
        return out

    def _merge(
        self, text: str, atoms: list[tuple[int, int]]
    ) -> list[tuple[int, int]]:
        if not atoms:
            return []
        merged: list[tuple[int, int]] = []
        cur_start, cur_end = atoms[0]
        for start, end in atoms[1:]:
            cand_tokens = count_tokens(text[cur_start:end])
            if cand_tokens <= self.target_tokens:
                cur_end = end
            else:
                merged.append((cur_start, cur_end))
                cur_start, cur_end = start, end
        merged.append((cur_start, cur_end))
        return merged


register_chunker(RecursiveChunker())
