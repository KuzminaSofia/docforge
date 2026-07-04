from __future__ import annotations

from technical_document_ml_service.chunking.ir import (
    BBox,
    Block,
    BlockType,
    StructuredDocument,
)


def _sample_doc() -> StructuredDocument:
    return StructuredDocument(
        doc_id="doc-1",
        source_filename="spec.pdf",
        blocks=[
            Block(
                id="b0",
                type=BlockType.SECTION_HEADER,
                text="3 Требования",
                page_no=0,
                bbox=BBox(0, 0.1, 0.1, 0.9, 0.15),
                section_path=["3 Требования"],
            ),
            Block(
                id="b1",
                type=BlockType.TABLE,
                text="Параметр Значение",
                html="<table><tr><td>Параметр</td></tr></table>",
                page_no=0,
                bbox=BBox(0, 0.1, 0.2, 0.9, 0.4),
                section_path=["3 Требования"],
                parent_id="b0",
            ),
        ],
        toc=[{"title": "3 Требования", "level": 1, "page": 0}],
        metadata={"parser": "datalab", "page_count": 1},
    )


def test_blocktype_coerce_unknown_to_other() -> None:
    assert BlockType.coerce("section_header") is BlockType.SECTION_HEADER
    assert BlockType.coerce("totally-unknown") is BlockType.OTHER
    assert BlockType.coerce(None) is BlockType.OTHER
    assert BlockType.coerce("") is BlockType.OTHER


def test_document_json_roundtrip_is_stable() -> None:
    doc = _sample_doc()
    restored = StructuredDocument.from_json(doc.to_json())

    assert restored.doc_id == doc.doc_id
    assert restored.source_filename == doc.source_filename
    assert len(restored.blocks) == 2
    assert restored.toc == doc.toc
    assert restored.metadata == doc.metadata
    # повторная сериализация даёт тот же словарь — контракт стабилен
    assert restored.to_dict() == doc.to_dict()


def test_block_roundtrip_preserves_bbox_and_type() -> None:
    block = _sample_doc().blocks[1]
    restored = Block.from_dict(block.to_dict())

    assert restored.type is BlockType.TABLE
    assert restored.html == block.html
    assert restored.parent_id == "b0"
    assert restored.bbox == block.bbox
    assert isinstance(restored.bbox, BBox)


def test_bbox_is_frozen_and_serializes() -> None:
    bbox = BBox(page_no=2, x1=0.1, y1=0.2, x2=0.3, y2=0.4)
    assert bbox.to_dict() == {
        "page_no": 2,
        "x1": 0.1,
        "y1": 0.2,
        "x2": 0.3,
        "y2": 0.4,
    }
    assert BBox.from_dict(bbox.to_dict()) == bbox


def test_helpers_block_by_id_and_full_text() -> None:
    doc = _sample_doc()
    assert doc.block_by_id("b0").text == "3 Требования"
    assert doc.block_by_id("missing") is None
    assert "Требования" in doc.full_text()
    assert "Параметр" in doc.full_text()
