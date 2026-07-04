"""Загрузка корпуса: IR-документы и QA-пары.

IR лежит в `research/data/ir/<doc_id>.json`, QA — в `research/data/qa/qa.jsonl`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from technical_document_ml_service.chunking.ir import StructuredDocument

_DATA = Path(__file__).resolve().parents[1] / "data"
_IR_DIR = _DATA / "ir"
_QA_PATH = _DATA / "qa" / "qa.jsonl"


@dataclass
class QAPair:
    id: str
    doc_id: str
    question: str
    answer: str
    source_block_ids: list[str] = field(default_factory=list)
    section_path: list[str] = field(default_factory=list)
    validated: bool = False


def load_ir(ir_dir: Path = _IR_DIR) -> dict[str, StructuredDocument]:
    """doc_id → StructuredDocument для всего корпуса."""
    docs: dict[str, StructuredDocument] = {}
    for path in sorted(Path(ir_dir).glob("*.json")):
        doc = StructuredDocument.from_json(path.read_text(encoding="utf-8"))
        docs[doc.doc_id] = doc
    return docs


def load_qa(
    qa_path: Path = _QA_PATH, *, validated_only: bool = False
) -> list[QAPair]:
    """QA-пары из jsonl. `validated_only=True` — только вручную проверенные."""
    path = Path(qa_path)
    if not path.is_file():
        return []
    pairs: list[QAPair] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        pair = QAPair(
            id=rec["id"],
            doc_id=rec["doc_id"],
            question=rec.get("question", ""),
            answer=rec.get("answer", ""),
            source_block_ids=list(rec.get("source_block_ids", [])),
            section_path=list(rec.get("section_path", [])),
            validated=bool(rec.get("validated", False)),
        )
        if validated_only and not pair.validated:
            continue
        pairs.append(pair)
    return pairs
