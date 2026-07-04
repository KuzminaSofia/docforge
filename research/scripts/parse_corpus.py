"""Прогнать корпус через Datalab (output_format=json) → IR в research/data/ir/.

Для каждого документа из manifest.json:
  1. Отправляет файл в Datalab convert API с `output_format=json`.
  2. Опрашивает статус до готовности.
  3. Прогоняет сырой json через `datalab_adapter` → `StructuredDocument`.
  4. Сохраняет IR в `research/data/ir/<doc_id>.json`.

Ключ Datalab — env `APP_DATALAB_API_KEY`. Уже распарсенные документы пропускаются
(идемпотентно), если не задан `--force`.

Использование:
    APP_DATALAB_API_KEY=... python -m research.scripts.parse_corpus
    python -m research.scripts.parse_corpus --only doc-id-1,doc-id-2 --force
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import time
from pathlib import Path

import research  # noqa: F401  — bootstrap sys.path

from technical_document_ml_service.chunking.adapters import get_adapter

_DATA = Path(__file__).resolve().parents[1] / "data"
_MANIFEST = _DATA / "corpus" / "manifest.json"
_IR_DIR = _DATA / "ir"
_RAW_DIR = _DATA / "raw"  # сырой ответ Datalab (для отладки адаптера)

_API_BASE = "https://www.datalab.to/api/v1"
_SUBMIT_TIMEOUT_S = 120
_POLL_INTERVAL_S = 3
_POLL_TIMEOUT_S = 600


def _api_key() -> str:
    key = os.environ.get("APP_DATALAB_API_KEY")
    if not key:
        raise SystemExit("нет ключа: задай env APP_DATALAB_API_KEY")
    return key


def _submit(path: Path, key: str, mode: str) -> str:
    import requests

    options = {"mode": mode, "output_format": "json"}
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    with path.open("rb") as fh:
        resp = requests.post(
            f"{_API_BASE}/convert",
            headers={"X-API-Key": key},
            data=options,
            files={"file": (path.name, fh, content_type)},
            timeout=_SUBMIT_TIMEOUT_S,
        )
    resp.raise_for_status()
    body = resp.json()
    if not body.get("success"):
        raise RuntimeError(f"Datalab отклонил {path.name}: {body.get('error')}")
    return body["request_check_url"]


def _poll(check_url: str, key: str) -> dict:
    import requests

    deadline = time.monotonic() + _POLL_TIMEOUT_S
    while True:
        resp = requests.get(
            check_url, headers={"X-API-Key": key}, timeout=_SUBMIT_TIMEOUT_S
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get("status") == "complete":
            if not body.get("success"):
                raise RuntimeError(f"Datalab ошибка: {body.get('error')}")
            return body
        if time.monotonic() > deadline:
            raise RuntimeError(f"Datalab не успел за {_POLL_TIMEOUT_S}s")
        time.sleep(_POLL_INTERVAL_S)


def parse_one(entry: dict, key: str, mode: str) -> dict:
    """Вернуть сырой json-ответ Datalab для одного документа."""
    path = Path(entry["path"])
    if not path.is_file():
        raise FileNotFoundError(path)
    check_url = _submit(path, key, mode)
    return _poll(check_url, key)


def _readapt_from_raw(args) -> int:
    """Пересобрать IR из сохранённых сырых ответов Datalab (без вызова API)."""
    raw_files = sorted(args.raw_dir.glob("*.json"))
    if not raw_files:
        print(f"нет сырых ответов в {args.raw_dir}. Сначала прогони parse_corpus (сохранит raw).")
        return 1
    adapter = get_adapter("datalab")
    args.out.mkdir(parents=True, exist_ok=True)
    only = set(args.only.split(",")) if args.only else None
    done = failed = 0
    for raw_file in raw_files:
        doc_id = raw_file.stem
        if only and doc_id not in only:
            continue
        try:
            raw = json.loads(raw_file.read_text(encoding="utf-8"))
            ir = adapter.to_ir(raw, doc_id=doc_id, source_filename=doc_id)
            (args.out / f"{doc_id}.json").write_text(ir.to_json(), encoding="utf-8")
            done += 1
            print(f"  ✓ {doc_id}: {len(ir.blocks)} блоков (из raw)")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  ✗ {doc_id}: {exc}")
    print(f"пересобрано из raw: {done}, ошибок: {failed}")
    return 0 if failed == 0 else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Datalab → IR по корпусу")
    parser.add_argument("--manifest", type=Path, default=_MANIFEST)
    parser.add_argument("--out", type=Path, default=_IR_DIR)
    parser.add_argument("--mode", default="accurate", choices=["fast", "balanced", "accurate"])
    parser.add_argument("--only", default=None, help="csv doc_id для выборочного прогона")
    parser.add_argument("--force", action="store_true", help="перепарсить уже готовые")
    parser.add_argument("--raw-dir", type=Path, default=_RAW_DIR)
    parser.add_argument(
        "--no-raw", action="store_true", help="не сохранять сырой ответ Datalab"
    )
    parser.add_argument(
        "--from-raw",
        action="store_true",
        help="НЕ звать Datalab: пересобрать IR из сохранённых raw/ (для отладки адаптера, без затрат API)",
    )
    args = parser.parse_args()

    if args.from_raw:
        return _readapt_from_raw(args)

    if not args.manifest.is_file():
        print(f"нет manifest: {args.manifest}. Сначала build_corpus.")
        return 1

    entries = json.loads(args.manifest.read_text(encoding="utf-8"))
    only = set(args.only.split(",")) if args.only else None
    args.out.mkdir(parents=True, exist_ok=True)
    if not args.no_raw:
        args.raw_dir.mkdir(parents=True, exist_ok=True)
    adapter = get_adapter("datalab")
    key = _api_key()

    done = skipped = failed = 0
    for entry in entries:
        doc_id = entry["doc_id"]
        if only and doc_id not in only:
            continue
        out_path = args.out / f"{doc_id}.json"
        if out_path.exists() and not args.force:
            skipped += 1
            continue
        try:
            raw = parse_one(entry, key, args.mode)
            # сохраняем сырой ответ (без base64-картинок) — для отладки адаптера
            if not args.no_raw:
                slim = {k: v for k, v in raw.items() if k != "images"}
                (args.raw_dir / f"{doc_id}.json").write_text(
                    json.dumps(slim, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            ir = adapter.to_ir(
                raw, doc_id=doc_id, source_filename=Path(entry["path"]).name
            )
            out_path.write_text(ir.to_json(), encoding="utf-8")
            done += 1
            print(f"  ✓ {doc_id}: {len(ir.blocks)} блоков → {out_path.name}")
        except Exception as exc:  # noqa: BLE001 — логируем и идём дальше
            failed += 1
            print(f"  ✗ {doc_id}: {exc}")

    print(f"готово: {done}, пропущено: {skipped}, ошибок: {failed}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
