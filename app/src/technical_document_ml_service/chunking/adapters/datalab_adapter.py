"""Datalab (Marker) JSON → IR.

Реальная структура ответа Datalab convert API с `output_format=json`
(проверено на сканах ГОСТ/поверочных описаний):

    { ..., "json": {"children": [<Page>, ...], "metadata": {...}}, "page_count": N }

- Корневой узел (`raw["json"]`) НЕ имеет `block_type` — только `children` (страницы)
  и `metadata`. Трактуется как контейнер.
- `Page`: `block_type="Page"`, `polygon`+`bbox` (размер страницы в пикселях),
  `children` — контентные блоки страницы.
- Контентный блок (`SectionHeader`, `Text`, `Table`, `ListGroup`, `Figure`, ...):
  текст лежит в `html` (не в `text` и не в Line/Span), плюс `page` (номер страницы),
  `polygon`/`bbox` (пиксели), `section_hierarchy` (level → id блока-заголовка).
  `children` у листьев = None. `*Group`-блоки — тоже листья с готовым html.

Что делает адаптер:
- разворачивает дерево в плоский список контентных блоков в порядке чтения;
- текст блока = очищенный от тегов `html`;
- `polygon`/`bbox` → нормализованный `BBox` 0..1 (делим на размер страницы);
- `section_hierarchy` → `section_path` (резолвим id секций в их текст-заголовки);
- `table_of_contents` из метаданных (если есть) → `StructuredDocument.toc`.

Адаптер устойчив к отсутствию полей: нет polygon/размера страницы → `bbox=None`;
неизвестная обёртка ответа (строка/иные ключи) разбирается в `_root_node`.
"""

from __future__ import annotations

import json
import re
from typing import Any

from technical_document_ml_service.chunking.adapters.base import (
    StructureAdapter,
    register_adapter,
)
from technical_document_ml_service.chunking.ir import (
    BBox,
    Block,
    BlockType,
    StructuredDocument,
)

# Datalab block_type (строка) → BlockType IR.
_TYPE_MAP: dict[str, BlockType] = {
    "SectionHeader": BlockType.SECTION_HEADER,
    "Text": BlockType.TEXT,
    "TextInlineMath": BlockType.TEXT,
    "Footnote": BlockType.TEXT,
    "Reference": BlockType.TEXT,
    "Form": BlockType.TEXT,
    "Handwriting": BlockType.TEXT,
    "Table": BlockType.TABLE,
    "Code": BlockType.CODE,
    "ListItem": BlockType.LIST_ITEM,
    "Figure": BlockType.FIGURE,
    "Picture": BlockType.FIGURE,
    "Caption": BlockType.CAPTION,
    "Equation": BlockType.EQUATION,
    "PageHeader": BlockType.PAGE_HEADER,
    "PageFooter": BlockType.PAGE_FOOTER,
    "TableOfContents": BlockType.TOC,
    # *Group-блоки в json-выводе Datalab — листья с html (не контейнеры).
    "ListGroup": BlockType.LIST_ITEM,
    "TableGroup": BlockType.TABLE,
    "FigureGroup": BlockType.FIGURE,
    "PictureGroup": BlockType.FIGURE,
    "Line": BlockType.TEXT,
    "Span": BlockType.TEXT,
}

# Контейнеры-обёртки: не эмитим как блок, рекурсивно заходим внутрь.
# ВАЖНО: корневой узел json-вывода Datalab не имеет block_type (только children) —
# он тоже трактуется как контейнер (см. _walk). *Group сюда НЕ входят: в json-выводе
# они приходят листьями с готовым html, а не контейнерами с детьми.
_CONTAINER_TYPES = {"Document", "Page"}

# html сохраняем в Block.html для этих типов (таблицы полезно рендерить как есть).
_HTML_KEEP_TYPES = {"Table", "TableGroup"}

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _strip_html(html: str | None) -> str:
    if not html:
        return ""
    text = _TAG_RE.sub(" ", html)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
    )
    return _WS_RE.sub(" ", text).strip()


def _polygon_bounds(block: dict) -> tuple[float, float, float, float] | None:
    """(x1,y1,x2,y2) в пикселях из polygon (4 угла) или bbox; иначе None."""
    polygon = block.get("polygon")
    if polygon:
        xs = [float(p[0]) for p in polygon]
        ys = [float(p[1]) for p in polygon]
        return min(xs), min(ys), max(xs), max(ys)
    bbox = block.get("bbox")
    if bbox and len(bbox) == 4:
        x1, y1, x2, y2 = (float(v) for v in bbox)
        return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)
    return None


class DatalabAdapter(StructureAdapter):
    name = "datalab"

    def to_ir(
        self, raw: dict, *, doc_id: str, source_filename: str
    ) -> StructuredDocument:
        root = self._root_node(raw)

        # Проход 1: собрать текст всех section-header блоков по id (для section_path).
        header_text: dict[str, str] = {}
        self._collect_headers(root, header_text)

        blocks: list[Block] = []
        # page_no считаем по порядку встреченных Page-узлов (0-based).
        state = {"page_no": 0, "page_size": None}
        self._walk(
            root,
            blocks=blocks,
            header_text=header_text,
            state=state,
            parent_id=None,
        )

        toc = self._extract_toc(raw, root)
        metadata = {
            "parser": "datalab",
            "mode": raw.get("mode") or self._meta(raw).get("mode"),
            "page_count": raw.get("page_count") or self._page_count(root),
            "bbox_units": "normalized_0_1",
        }
        return StructuredDocument(
            doc_id=doc_id,
            source_filename=source_filename,
            blocks=blocks,
            toc=toc,
            metadata=metadata,
        )

    # --- helpers ---------------------------------------------------------------

    @staticmethod
    def _root_node(raw: dict) -> dict:
        """Достать корневой блок-узел независимо от обёртки ответа.

        Устойчив к тому, что дерево лежит под разными ключами и может прийти
        строкой (сериализованный json), а не dict.
        """
        node: Any = raw
        for key in ("json", "result", "output", "data"):
            if isinstance(node, dict) and key in node:
                candidate = node[key]
                if isinstance(candidate, str):
                    try:
                        candidate = json.loads(candidate)
                    except (json.JSONDecodeError, TypeError, ValueError):
                        candidate = None
                if isinstance(candidate, dict):
                    node = candidate
                    break
                if isinstance(candidate, list) and candidate:
                    # список верхнеуровневых блоков (напр. output_format="chunks")
                    return {"block_type": "Document", "children": candidate}
        if isinstance(node, dict) and isinstance(node.get("blocks"), list):
            return {"block_type": "Document", "children": node["blocks"]}
        if isinstance(node, dict) and isinstance(node.get("pages"), list):
            return {"block_type": "Document", "children": node["pages"]}
        return node if isinstance(node, dict) else {"block_type": "Document", "children": []}

    @staticmethod
    def _meta(raw: dict) -> dict:
        meta = raw.get("metadata")
        return meta if isinstance(meta, dict) else {}

    def _collect_headers(self, node: dict, out: dict[str, str]) -> None:
        if not isinstance(node, dict):
            return
        if node.get("block_type") == "SectionHeader":
            block_id = node.get("id")
            if block_id:
                out[block_id] = self._node_text(node)
        for child in node.get("children") or []:
            self._collect_headers(child, out)

    def _walk(
        self,
        node: dict,
        *,
        blocks: list[Block],
        header_text: dict[str, str],
        state: dict,
        parent_id: str | None,
    ) -> None:
        if not isinstance(node, dict):
            return
        btype = node.get("block_type")
        children = node.get("children")
        children = children if isinstance(children, list) else []

        if btype == "Page":
            state["page_no"] = self._page_index(node, state)
            state["page_size"] = self._page_size(node)

        # Контейнер (не эмитим): явный Document/Page ИЛИ корень json-вывода Datalab
        # (у него нет block_type, только children).
        if btype in _CONTAINER_TYPES or (btype is None and children):
            for child in children:
                self._walk(
                    child,
                    blocks=blocks,
                    header_text=header_text,
                    state=state,
                    parent_id=parent_id,
                )
            return

        text = self._node_text(node)
        # структурный узел без собственного текста, но с детьми → идём внутрь
        if not text and children:
            for child in children:
                self._walk(
                    child,
                    blocks=blocks,
                    header_text=header_text,
                    state=state,
                    parent_id=parent_id,
                )
            return

        # Лист-контентный блок.
        block_id = str(node.get("id") or f"block-{len(blocks)}")
        page_no = (
            int(node["page"]) if isinstance(node.get("page"), int) else state["page_no"]
        )
        html = node.get("html") if btype in _HTML_KEEP_TYPES else None
        bbox = self._make_bbox(node, state, page_no)
        section_path = self._section_path(node, header_text)

        blocks.append(
            Block(
                id=block_id,
                type=_TYPE_MAP.get(btype, BlockType.OTHER),
                text=text,
                page_no=page_no,
                html=html,
                bbox=bbox,
                section_path=section_path,
                parent_id=parent_id,
                children_ids=[],
            )
        )

    def _node_text(self, node: dict) -> str:
        """Текст блока: собственный `text`, иначе из Line/Span, иначе из html."""
        if node.get("text"):
            return str(node["text"]).strip()
        parts: list[str] = []
        self._gather_line_text(node, parts)
        if parts:
            return " ".join(p for p in parts if p).strip()
        return _strip_html(node.get("html"))

    def _gather_line_text(self, node: dict, parts: list[str]) -> None:
        for child in node.get("children") or []:
            if not isinstance(child, dict):
                continue
            ctype = child.get("block_type")
            if ctype in ("Line", "Span"):
                if child.get("text"):
                    parts.append(str(child["text"]))
                self._gather_line_text(child, parts)

    def _make_bbox(self, node: dict, state: dict, page_no: int) -> BBox | None:
        bounds = _polygon_bounds(node)
        size = state.get("page_size")
        if bounds is None or not size:
            return None
        width, height = size
        if width <= 0 or height <= 0:
            return None
        x1, y1, x2, y2 = bounds

        def clamp(v: float) -> float:
            return max(0.0, min(1.0, v))

        return BBox(
            page_no=page_no,
            x1=clamp(x1 / width),
            y1=clamp(y1 / height),
            x2=clamp(x2 / width),
            y2=clamp(y2 / height),
        )

    @staticmethod
    def _section_path(node: dict, header_text: dict[str, str]) -> list[str]:
        hierarchy = node.get("section_hierarchy")
        if not isinstance(hierarchy, dict) or not hierarchy:
            return []
        # ключи — уровни (строки/числа); сортируем по числовому уровню.
        def level_key(item: tuple[Any, Any]) -> int:
            try:
                return int(item[0])
            except (TypeError, ValueError):
                return 0

        path: list[str] = []
        for _level, ref in sorted(hierarchy.items(), key=level_key):
            title = header_text.get(ref)
            if title:
                path.append(title)
        return path

    @staticmethod
    def _page_size(node: dict) -> tuple[float, float] | None:
        bounds = _polygon_bounds(node)
        if bounds is None:
            return None
        x1, y1, x2, y2 = bounds
        w, h = x2 - x1, y2 - y1
        if w <= 0 or h <= 0:
            return None
        return w, h

    @staticmethod
    def _page_index(node: dict, state: dict) -> int:
        # Datalab часто кодирует страницу в id: "/page/3/...".
        block_id = str(node.get("id") or "")
        match = re.search(r"/page/(\d+)", block_id)
        if match:
            return int(match.group(1))
        page_id = node.get("page_id")
        if page_id is not None:
            try:
                return int(page_id)
            except (TypeError, ValueError):
                pass
        # иначе — инкремент от предыдущего.
        return state["page_no"] + 1 if state.get("page_size") is not None else 0

    def _page_count(self, root: dict) -> int:
        count = 0
        stack = [root]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                if node.get("block_type") == "Page":
                    count += 1
                stack.extend(node.get("children") or [])
        return count

    def _extract_toc(self, raw: dict, root: dict) -> list[dict]:
        candidates = (
            self._meta(raw).get("table_of_contents"),
            raw.get("table_of_contents"),
            (root.get("metadata") or {}).get("table_of_contents")
            if isinstance(root.get("metadata"), dict)
            else None,
        )
        for toc in candidates:
            if isinstance(toc, list) and toc:
                return [self._norm_toc_entry(e) for e in toc if isinstance(e, dict)]
        return []

    @staticmethod
    def _norm_toc_entry(entry: dict) -> dict:
        return {
            "title": entry.get("title") or entry.get("text") or "",
            "level": entry.get("level")
            or entry.get("heading_level")
            or entry.get("depth"),
            "page": entry.get("page")
            if entry.get("page") is not None
            else entry.get("page_id"),
        }


# Регистрация единственного экземпляра в реестре.
register_adapter(DatalabAdapter())
