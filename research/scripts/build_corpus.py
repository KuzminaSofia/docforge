"""Реестр корпуса техдоков → `research/data/corpus/manifest.json`.

Сканирует папку с исходными документами (PDF/DOCX/DOC) и строит manifest:
для каждого документа — стабильный `doc_id`, путь, тип, источник. Дальше
`parse_corpus.py` берёт manifest и гонит каждый файл через парсер.

Использование:
    python -m research.scripts.build_corpus --src research/data/corpus/raw
    python -m research.scripts.build_corpus --src ~/docs --source "ГОСТ"
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import research  # noqa: F401  — bootstrap sys.path

_SUPPORTED = {".pdf", ".docx", ".doc"}
_DATA = Path(__file__).resolve().parents[1] / "data"
_DEFAULT_SRC = _DATA / "corpus" / "raw"
_DEFAULT_MANIFEST = _DATA / "corpus" / "manifest.json"


def _doc_id(path: Path) -> str:
    """Стабильный id: имя файла + короткий хэш пути (защита от коллизий имён)."""
    digest = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:8]
    slug = "".join(
        c if c.isalnum() or c in "-_" else "_" for c in path.stem
    ).strip("_")
    return f"{slug or 'doc'}-{digest}"


def build_manifest(src: Path, source_label: str | None) -> list[dict]:
    entries: list[dict] = []
    for path in sorted(src.rglob("*")):
        if path.is_file() and path.suffix.lower() in _SUPPORTED:
            entries.append(
                {
                    "doc_id": _doc_id(path),
                    "path": str(path),
                    "type": path.suffix.lower().lstrip("."),
                    "source": source_label or path.parent.name,
                    "size_bytes": path.stat().st_size,
                }
            )
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description="собрать реестр корпуса техдоков")
    parser.add_argument("--src", type=Path, default=_DEFAULT_SRC)
    parser.add_argument("--out", type=Path, default=_DEFAULT_MANIFEST)
    parser.add_argument(
        "--source", default=None, help="метка источника (напр. 'ГОСТ', 'datasheet')"
    )
    args = parser.parse_args()

    if not args.src.is_dir():
        print(f"нет папки с документами: {args.src}")
        print("положи 10–20 техдоков (мануалы, datasheet, ГОСТ, API-доки) туда.")
        return 1

    entries = build_manifest(args.src, args.source)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"документов в корпусе: {len(entries)} → {args.out}")
    if len(entries) < 10:
        print("предупреждение: цель недели 1 — 10–20 документов.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
