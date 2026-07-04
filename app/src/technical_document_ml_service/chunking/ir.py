"""IR — нормализованное представление документа (`StructuredDocument`).

Это контракт, на который завязано всё: адаптеры парсеров пишут в него, чанкеры
читают из него. Схема зафиксирована в неделю 1 (`jmlc/architecture.md`) и меняется
только при веской причине.

Единицы bbox: нормализованные 0..1 относительно размера страницы (см. Конвенции
в architecture.md). Если у парсера нет размеров страницы — адаптер кладёт
`bbox = None`, а не сырые пиксели.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class BlockType(str, Enum):
    """Тип блока в IR. Строковый Enum — сериализуется как строка в json."""

    SECTION_HEADER = "section_header"
    TEXT = "text"
    TABLE = "table"
    CODE = "code"
    LIST_ITEM = "list_item"
    FIGURE = "figure"
    CAPTION = "caption"
    EQUATION = "equation"
    PAGE_HEADER = "page_header"  # колонтитул — при чанкинге выкидываем
    PAGE_FOOTER = "page_footer"
    TOC = "toc"
    OTHER = "other"

    @classmethod
    def coerce(cls, raw: str | None) -> "BlockType":
        """Мягкий парсинг: неизвестный/пустой тип → OTHER (адаптер не падает)."""
        if not raw:
            return cls.OTHER
        key = str(raw).strip().lower()
        try:
            return cls(key)
        except ValueError:
            return cls.OTHER


@dataclass(frozen=True)
class BBox:
    """Ограничивающий прямоугольник блока на странице.

    Координаты нормализованы в диапазон 0..1 относительно размера страницы:
    x — доля ширины, y — доля высоты. `page_no` — 0-based номер страницы.
    """

    page_no: int
    x1: float
    y1: float
    x2: float
    y2: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BBox":
        return cls(
            page_no=int(data["page_no"]),
            x1=float(data["x1"]),
            y1=float(data["y1"]),
            x2=float(data["x2"]),
            y2=float(data["y2"]),
        )


@dataclass
class Block:
    """Один блок документа (абзац, заголовок, таблица, элемент списка, ...).

    Дерево выражается через `parent_id` / `children_ids`; сам список блоков в
    `StructuredDocument.blocks` — плоский и в порядке чтения.
    """

    id: str
    type: BlockType
    text: str  # плоский текст блока
    page_no: int
    html: str | None = None  # исходный html блока (полезно для таблиц)
    bbox: BBox | None = None
    section_path: list[str] = field(default_factory=list)  # «хлебные крошки»
    parent_id: str | None = None
    children_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "text": self.text,
            "page_no": self.page_no,
            "html": self.html,
            "bbox": self.bbox.to_dict() if self.bbox is not None else None,
            "section_path": list(self.section_path),
            "parent_id": self.parent_id,
            "children_ids": list(self.children_ids),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Block":
        bbox = data.get("bbox")
        return cls(
            id=str(data["id"]),
            type=BlockType.coerce(data.get("type")),
            text=data.get("text", ""),
            page_no=int(data.get("page_no", 0)),
            html=data.get("html"),
            bbox=BBox.from_dict(bbox) if bbox else None,
            section_path=list(data.get("section_path", [])),
            parent_id=data.get("parent_id"),
            children_ids=list(data.get("children_ids", [])),
        )


@dataclass
class StructuredDocument:
    """Нормализованный документ: плоский список блоков + оглавление + метаданные."""

    doc_id: str
    source_filename: str
    blocks: list[Block] = field(default_factory=list)
    toc: list[dict] = field(default_factory=list)  # (title, level, page)
    metadata: dict = field(default_factory=dict)  # parser, mode, page_count и т.п.

    # --- удобные представления -------------------------------------------------

    def block_by_id(self, block_id: str) -> Block | None:
        for block in self.blocks:
            if block.id == block_id:
                return block
        return None

    def full_text(self, separator: str = "\n\n") -> str:
        """Плоский текст всего документа в порядке чтения (для fixed/recursive)."""
        return separator.join(b.text for b in self.blocks if b.text)

    # --- сериализация ----------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "source_filename": self.source_filename,
            "blocks": [b.to_dict() for b in self.blocks],
            "toc": list(self.toc),
            "metadata": dict(self.metadata),
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StructuredDocument":
        return cls(
            doc_id=str(data["doc_id"]),
            source_filename=str(data.get("source_filename", "")),
            blocks=[Block.from_dict(b) for b in data.get("blocks", [])],
            toc=list(data.get("toc", [])),
            metadata=dict(data.get("metadata", {})),
        )

    @classmethod
    def from_json(cls, raw: str) -> "StructuredDocument":
        return cls.from_dict(json.loads(raw))
