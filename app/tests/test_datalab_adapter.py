from __future__ import annotations

from technical_document_ml_service.chunking.adapters import get_adapter
from technical_document_ml_service.chunking.ir import BlockType


def _raw_datalab() -> dict:
    """Синтетический ответ Datalab (output_format=json), повторяющий РЕАЛЬНУЮ
    структуру: корень `json` без block_type (только children+metadata) → Page
    (polygon/bbox = размер страницы) → контентные блоки-листья, текст в `html`,
    у каждого `page`, `polygon`/`bbox`, `section_hierarchy` (level → id заголовка)."""
    header_id = "/page/0/SectionHeader/1"
    return {
        "status": "complete",
        "success": True,
        "output_format": "json",
        "page_count": 1,
        "json": {
            "children": [
                {
                    "id": "/page/0/Page/0",
                    "block_type": "Page",
                    "polygon": [[0, 0], [600, 0], [600, 800], [0, 800]],
                    "bbox": [0, 0, 600, 800],
                    "section_hierarchy": {},
                    "children": [
                        {
                            "id": header_id,
                            "block_type": "SectionHeader",
                            "page": 0,
                            "polygon": [[60, 40], [540, 40], [540, 80], [60, 80]],
                            "bbox": [60, 40, 540, 80],
                            "html": "<h1>3 Требования</h1>",
                            "section_hierarchy": {"1": header_id},
                            "children": None,
                        },
                        {
                            "id": "/page/0/Text/2",
                            "block_type": "Text",
                            "page": 0,
                            "polygon": [[60, 120], [540, 120], [540, 200], [60, 200]],
                            "bbox": [60, 120, 540, 200],
                            "html": "<p>Система выдерживает нагрузку.</p>",
                            "section_hierarchy": {"1": header_id},
                            "children": None,
                        },
                        {
                            "id": "/page/0/Table/3",
                            "block_type": "Table",
                            "page": 0,
                            "polygon": [[60, 240], [540, 240], [540, 400], [60, 400]],
                            "bbox": [60, 240, 540, 400],
                            "html": "<table><tr><td>Параметр</td><td>Знач</td></tr></table>",
                            "section_hierarchy": {"1": header_id},
                            "children": None,
                        },
                        {
                            "id": "/page/0/PageFooter/4",
                            "block_type": "PageFooter",
                            "page": 0,
                            "polygon": [[60, 760], [540, 760], [540, 790], [60, 790]],
                            "bbox": [60, 760, 540, 790],
                            "html": "<p>стр. 1</p>",
                            "section_hierarchy": {},
                            "children": None,
                        },
                    ],
                }
            ],
            "metadata": {"page_stats": [{"page_id": 0, "num_blocks": 4}]},
        },
        "metadata": {
            "table_of_contents": [
                {"title": "3 Требования", "heading_level": 1, "page_id": 0}
            ]
        },
    }


def _to_ir():
    adapter = get_adapter("datalab")
    return adapter.to_ir(_raw_datalab(), doc_id="doc-1", source_filename="spec.pdf")


def test_containers_are_flattened_only_content_blocks_emitted() -> None:
    doc = _to_ir()
    types = [b.type for b in doc.blocks]
    # Document / Page / Line / Span НЕ становятся блоками
    assert BlockType.SECTION_HEADER in types
    assert BlockType.TABLE in types
    assert BlockType.PAGE_FOOTER in types
    assert len(doc.blocks) == 4  # header, text, table, page_footer


def test_block_types_are_mapped() -> None:
    doc = _to_ir()
    by_text = {b.text: b for b in doc.blocks}
    assert by_text["3 Требования"].type is BlockType.SECTION_HEADER
    assert by_text["Система выдерживает нагрузку."].type is BlockType.TEXT
    table = next(b for b in doc.blocks if b.type is BlockType.TABLE)
    assert table.html and "Параметр" in table.html


def test_section_path_resolved_from_hierarchy() -> None:
    doc = _to_ir()
    text_block = next(b for b in doc.blocks if b.type is BlockType.TEXT)
    assert text_block.section_path == ["3 Требования"]


def test_bbox_is_normalized_0_1() -> None:
    doc = _to_ir()
    text_block = next(b for b in doc.blocks if b.type is BlockType.TEXT)
    bbox = text_block.bbox
    assert bbox is not None
    assert bbox.page_no == 0
    # x нормируется по ширине 600, y по высоте 800
    assert abs(bbox.x1 - 60 / 600) < 1e-6
    assert abs(bbox.y1 - 120 / 800) < 1e-6
    assert abs(bbox.x2 - 540 / 600) < 1e-6
    assert abs(bbox.y2 - 200 / 800) < 1e-6
    for v in (bbox.x1, bbox.y1, bbox.x2, bbox.y2):
        assert 0.0 <= v <= 1.0


def test_toc_extracted() -> None:
    doc = _to_ir()
    assert doc.toc == [{"title": "3 Требования", "level": 1, "page": 0}]
    assert doc.metadata["parser"] == "datalab"
    assert doc.metadata["bbox_units"] == "normalized_0_1"


def test_adapter_survives_missing_page_size() -> None:
    # Page без polygon и bbox → нет размеров → bbox блоков = None, но парсинг не падает
    raw = _raw_datalab()
    page = raw["json"]["children"][0]
    page.pop("polygon")
    page.pop("bbox")
    doc = get_adapter("datalab").to_ir(
        raw, doc_id="doc-2", source_filename="x.pdf"
    )
    assert len(doc.blocks) == 4
    assert all(b.bbox is None for b in doc.blocks)
