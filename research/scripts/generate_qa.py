"""LLM-генерация QA-пар с разметкой блока-источника → research/data/qa/qa.jsonl.

Для каждого документа берём «якорные» блоки (текст/таблицы достаточной длины),
просим LLM сгенерировать вопрос, ответ на который содержится ИМЕННО в этом блоке,
и записываем пару с `source_block_ids = [id блока]`. Это gold для retrieval-метрик.

⚠️ Критерий недели 1: ≥100 пар должны быть проверены ВРУЧНУЮ (правильный ли
блок-источник). Поле `validated` по умолчанию false — переключается при ревью
(напр. отдельным проходом или руками в jsonl).

LLM — OpenAI-совместимый chat endpoint: env `APP_LLM_API_KEY`, опц. `APP_LLM_BASE_URL`
(по умолчанию OpenAI) и `APP_LLM_MODEL`.

Использование:
    APP_LLM_API_KEY=... python -m research.scripts.generate_qa --per-doc 8
"""

from __future__ import annotations

import argparse
import json
import os
import uuid
from pathlib import Path

import research  # noqa: F401  — bootstrap sys.path

from technical_document_ml_service.chunking.ir import StructuredDocument
from technical_document_ml_service.chunking.tokenization import count_tokens

_DATA = Path(__file__).resolve().parents[1] / "data"
_IR_DIR = _DATA / "ir"
_QA_PATH = _DATA / "qa" / "qa.jsonl"

_ANCHOR_TYPES = {"text", "table", "list_item", "section_header", "code"}
_MIN_TOKENS = 40  # слишком короткие блоки не несут отвечаемого факта

_SYSTEM = (
    "Ты помогаешь строить датасет для оценки retrieval по технической "
    "документации. По фрагменту документа сформулируй ОДИН конкретный вопрос "
    "на русском, ответ на который содержится именно в этом фрагменте, и краткий "
    "ответ. Не выдумывай факты вне фрагмента. Верни строго JSON: "
    '{"question": "...", "answer": "..."}'
)


def _default_base_url() -> str:
    return os.environ.get("APP_LLM_BASE_URL", "https://api.openai.com/v1")


def _llm_qa(context: str) -> dict:
    import requests

    key = os.environ.get("APP_LLM_API_KEY")
    if not key:
        raise SystemExit("нет ключа: задай env APP_LLM_API_KEY")
    model = os.environ.get("APP_LLM_MODEL", "gpt-4o-mini")
    resp = requests.post(
        f"{_default_base_url()}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": context[:6000]},
            ],
            "temperature": 0.3,
            "response_format": {"type": "json_object"},
        },
        timeout=90,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    return _parse_json_lenient(content)


def _parse_json_lenient(content: str) -> dict:
    """Разобрать JSON из ответа LLM устойчиво: снять ```-ограждение, вырезать {...}."""
    try:
        return json.loads(content)
    except (json.JSONDecodeError, TypeError):
        pass
    text = content.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1] if "```" in text[3:] else text[3:]
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError(f"не удалось разобрать JSON из ответа LLM: {content[:120]!r}")


def _anchor_blocks(doc: StructuredDocument, per_doc: int) -> list:
    candidates = [
        b
        for b in doc.blocks
        if b.type.value in _ANCHOR_TYPES and count_tokens(b.text) >= _MIN_TOKENS
    ]
    # равномерно прореживаем, чтобы покрыть разные части документа
    if len(candidates) <= per_doc:
        return candidates
    step = len(candidates) / per_doc
    return [candidates[int(i * step)] for i in range(per_doc)]


def main() -> int:
    parser = argparse.ArgumentParser(description="LLM QA-генерация с source-разметкой")
    parser.add_argument("--ir-dir", type=Path, default=_IR_DIR)
    parser.add_argument("--out", type=Path, default=_QA_PATH)
    parser.add_argument("--per-doc", type=int, default=8, help="QA-пар на документ")
    parser.add_argument("--append", action="store_true", help="дописать, не перезаписывать")
    args = parser.parse_args()

    ir_files = sorted(args.ir_dir.glob("*.json"))
    if not ir_files:
        print(f"нет IR в {args.ir_dir}. Сначала parse_corpus.")
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if args.append else "w"
    written = 0
    with args.out.open(mode, encoding="utf-8") as fh:
        for ir_file in ir_files:
            doc = StructuredDocument.from_json(ir_file.read_text(encoding="utf-8"))
            for block in _anchor_blocks(doc, args.per_doc):
                context = (
                    " > ".join(block.section_path) + "\n\n" + block.text
                    if block.section_path
                    else block.text
                )
                try:
                    qa = _llm_qa(context)
                except Exception as exc:  # noqa: BLE001
                    print(f"  ✗ {doc.doc_id}/{block.id}: {exc}")
                    continue
                record = {
                    "id": uuid.uuid4().hex[:12],
                    "doc_id": doc.doc_id,
                    "question": qa.get("question", "").strip(),
                    "answer": qa.get("answer", "").strip(),
                    "source_block_ids": [block.id],
                    "section_path": block.section_path,
                    "validated": False,  # ⚠️ проверить вручную перед метриками
                }
                if record["question"]:
                    fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                    written += 1
            print(f"  ✓ {doc.doc_id}: сгенерировано пар")

    print(f"QA-пар записано: {written} → {args.out}")
    print("напоминание: вручную проверь ≥100 пар (validated=true) перед run_retrieval.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
