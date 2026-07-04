"""Baseline: разбиение по заголовкам (markdown-header split).

IR — не markdown, но section-заголовки в нём есть. Этот бейзлайн группирует
подряд идущие блоки по секции (по `section_path` / встреченным SECTION_HEADER),
каждая секция → чанк; секции длиннее hard-max дорезаются по блокам/предложениям.
Это честный аналог MarkdownHeaderTextSplitter поверх нашего IR.
"""

from __future__ import annotations

from technical_document_ml_service.chunking.chunk import Chunk
from technical_document_ml_service.chunking.chunkers.base import (
    Chunker,
    build_chunk,
    register_chunker,
)
from technical_document_ml_service.chunking.ir import Block, StructuredDocument
from technical_document_ml_service.chunking.tokenization import (
    HARD_MAX_CHUNK_TOKENS,
    TARGET_CHUNK_TOKENS,
    count_tokens,
)


class MarkdownSplitChunker(Chunker):
    name = "markdown_split"

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
        groups = self._group_by_section(content)

        chunks: list[Chunk] = []
        idx = 0
        for section_path, blocks in groups:
            # блоки → «юниты» (текст, блоки) не крупнее hard_max (крупные режем),
            # затем жадно сливаем юниты до target.
            units = self._units(blocks)
            for text, piece_blocks in self._pack(units):
                text = text.strip()
                if not text:
                    continue
                chunks.append(
                    build_chunk(
                        doc_id=doc.doc_id,
                        index=idx,
                        text=text,
                        chunker_name=self.name,
                        blocks=piece_blocks,
                        section_path=section_path,
                    )
                )
                idx += 1
        return chunks

    def _group_by_section(
        self, blocks: list[Block]
    ) -> list[tuple[list[str], list[Block]]]:
        """Секция начинается на SECTION_HEADER или смене section_path."""
        groups: list[tuple[list[str], list[Block]]] = []
        current_path: list[str] | None = None
        current: list[Block] = []

        def flush():
            if current:
                groups.append((current_path or [], list(current)))

        for b in blocks:
            starts_section = b.type.value == "section_header"
            path_changed = b.section_path != current_path
            if current and (starts_section or path_changed):
                flush()
                current.clear()
            if not current:
                current_path = b.section_path
            current.append(b)
        flush()
        return groups

    def _units(self, blocks: list[Block]) -> list[tuple[str, Block]]:
        """(текст, блок)-юниты не крупнее hard_max: большие блоки режем по предложениям/словам."""
        units: list[tuple[str, Block]] = []
        for b in blocks:
            if count_tokens(b.text) <= self.hard_max_tokens:
                units.append((b.text, b))
            else:
                for piece in self._hard_split(b.text):
                    units.append((piece, b))
        return units

    def _hard_split(self, text: str) -> list[str]:
        """Нарезать длинный текст на куски <= hard_max по предложениям, затем словам."""
        for sep in (". ", " "):
            if sep in text:
                pieces: list[str] = []
                buf = ""
                for part in text.split(sep):
                    cand = (buf + sep + part) if buf else part
                    if buf and count_tokens(cand) > self.hard_max_tokens:
                        pieces.append(buf)
                        buf = part
                    else:
                        buf = cand
                if buf:
                    pieces.append(buf)
                # если хоть один кусок всё ещё велик — уходим на следующий разделитель
                if all(count_tokens(p) <= self.hard_max_tokens for p in pieces):
                    return pieces
        # крайний случай: режем по символам ~hard_max*4
        approx = max(1, self.hard_max_tokens * 4)
        return [text[i : i + approx] for i in range(0, len(text), approx)]

    def _pack(
        self, units: list[tuple[str, Block]]
    ) -> list[tuple[str, list[Block]]]:
        """Слить юниты жадно до target; каждый юнит уже <= hard_max."""
        out: list[tuple[str, list[Block]]] = []
        cur_text = ""
        cur_blocks: list[Block] = []
        for text, block in units:
            cand = (cur_text + "\n\n" + text) if cur_text else text
            if cur_text and count_tokens(cand) > self.target_tokens:
                out.append((cur_text, cur_blocks))
                cur_text, cur_blocks = text, [block]
            else:
                cur_text = cand
                if block not in cur_blocks:
                    cur_blocks.append(block)
        if cur_text:
            out.append((cur_text, cur_blocks))
        return out


register_chunker(MarkdownSplitChunker())
