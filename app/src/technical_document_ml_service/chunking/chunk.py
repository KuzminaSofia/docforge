"""`Chunk` — единица выхода любого чанкера.

Один контракт для всех чанкеров (baseline и наших), чтобы eval-харнесс мог
прогонять их через одинаковый retrieval и честно сравнивать.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from technical_document_ml_service.chunking.ir import BBox


@dataclass
class Chunk:
    """Готовый фрагмент документа для эмбеддинга/LLM.

    `text` — то, что уйдёт в эмбеддинг (обычно с префиксом section_path-крошек).
    `bbox_union` — прямоугольники исходных блоков для подсветки источника в PDF.
    """

    id: str
    doc_id: str
    text: str
    token_count: int
    block_ids: list[str] = field(default_factory=list)
    section_path: list[str] = field(default_factory=list)
    page_range: tuple[int, int] = (0, 0)
    bbox_union: list[BBox] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["bbox_union"] = [b.to_dict() for b in self.bbox_union]
        data["page_range"] = list(self.page_range)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Chunk":
        page_range = data.get("page_range", (0, 0))
        return cls(
            id=str(data["id"]),
            doc_id=str(data["doc_id"]),
            text=data.get("text", ""),
            token_count=int(data.get("token_count", 0)),
            block_ids=list(data.get("block_ids", [])),
            section_path=list(data.get("section_path", [])),
            page_range=(int(page_range[0]), int(page_range[1])),
            bbox_union=[BBox.from_dict(b) for b in data.get("bbox_union", [])],
            metadata=dict(data.get("metadata", {})),
        )
