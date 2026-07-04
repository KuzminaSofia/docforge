"""Baseline: fixed-size окна по токенам с overlap.

Структуру игнорирует намеренно — это точка отсчёта. Текст документа
склеивается в порядке чтения и режется на окна ~target токенов с перекрытием.
Работает и без tiktoken (через приблизительный счёт из tokenization).
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
    TARGET_CHUNK_TOKENS,
    count_tokens,
)

_WS = " \t\r\n"


def _word_spans(text: str) -> list[tuple[int, int]]:
    """Символьные диапазоны «слов» (разделённых пробелами) — атомы упаковки."""
    spans: list[tuple[int, int]] = []
    i, n = 0, len(text)
    while i < n:
        while i < n and text[i] in _WS:
            i += 1
        if i >= n:
            break
        start = i
        while i < n and text[i] not in _WS:
            i += 1
        spans.append((start, i))
    return spans


class FixedSizeChunker(Chunker):
    name = "fixed_size"

    def __init__(
        self,
        target_tokens: int = TARGET_CHUNK_TOKENS,
        overlap_tokens: int = 64,
    ) -> None:
        self.target_tokens = target_tokens
        self.overlap_tokens = max(0, min(overlap_tokens, target_tokens - 1))

    def chunk(self, doc: StructuredDocument) -> list[Chunk]:
        # исключаем колонтитулы — они шумят в retrieval
        content = [
            b
            for b in doc.blocks
            if b.text and b.type.value not in ("page_header", "page_footer")
        ]
        text, spans = concat_with_spans(content)
        words = _word_spans(text)
        if not words:
            return []

        chunks = []
        idx = 0
        i = 0
        while i < len(words):
            j = i
            cur_start = words[i][0]
            cur_end = words[i][1]
            token_count = count_tokens(text[cur_start:cur_end])
            # набираем слова, пока не достигли target
            while j + 1 < len(words):
                nxt_end = words[j + 1][1]
                cand = count_tokens(text[cur_start:nxt_end])
                if cand > self.target_tokens:
                    break
                j += 1
                cur_end = nxt_end
                token_count = cand

            piece = text[cur_start:cur_end].strip()
            if piece:
                src_blocks = blocks_in_span(spans, cur_start, cur_end)
                chunks.append(
                    build_chunk(
                        doc_id=doc.doc_id,
                        index=idx,
                        text=piece,
                        chunker_name=self.name,
                        blocks=src_blocks,
                        section_path=src_blocks[0].section_path
                        if src_blocks
                        else [],
                    )
                )
                idx += 1

            if j + 1 >= len(words):
                break
            # overlap: отступаем назад на ~overlap_tokens
            i = self._overlap_start(text, words, i, j)

        return chunks

    def _overlap_start(self, text, words, i, j):
        if self.overlap_tokens <= 0:
            return j + 1
        end_char = words[j][1]
        k = j
        while k > i:
            back_tokens = count_tokens(text[words[k][0] : end_char])
            if back_tokens >= self.overlap_tokens:
                break
            k -= 1
        # гарантируем прогресс
        return max(k, i + 1)


register_chunker(FixedSizeChunker())
