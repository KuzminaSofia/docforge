"""Общие helpers сериализации/записи артефактов для backend-обработчиков.

Вынесены сюда, чтобы не дублировать одинаковую логику между конкретными
бэкендами (Docling, Datalab, ...). Бэкенды работают с локальной ФС; staging-слой
отвечает за выгрузку результата в object storage.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def to_jsonable(obj: Any) -> Any:
    """преобразовать произвольный объект в JSON-сериализуемый вид"""
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_jsonable(x) for x in obj]
    if callable(obj):
        return f"<callable:{getattr(obj, '__name__', type(obj).__name__)}>"
    return str(obj)


def save_json(path: Path, data: Any) -> None:
    """сохранить данные в JSON-файл"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(to_jsonable(data), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


_CYRILLIC_TO_LATIN_LOWER = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}
_TRANSLIT_MAP: dict[str, str] = {}
for _cyr, _lat in _CYRILLIC_TO_LATIN_LOWER.items():
    _TRANSLIT_MAP[_cyr] = _lat
    _TRANSLIT_MAP[_cyr.upper()] = _lat.capitalize() if _lat else ""


def _transliterate(text: str) -> str:
    """транслитерировать кириллицу в латиницу; прочие символы — без изменений"""
    return "".join(_TRANSLIT_MAP.get(ch, ch) for ch in text)


def sanitize_stem(filename: str) -> str:
    """безопасно нормализовать stem имени файла для каталога/артефактов

    Кириллица транслитерируется в латиницу (читаемость + ASCII-safe для HTTP-заголовков),
    остальные недопустимые символы заменяются на '_'.
    """
    raw_stem = Path(filename).stem or "document"
    normalized = re.sub(
        r"[^A-Za-z0-9._-]+", "_", _transliterate(raw_stem)
    ).strip("._-")
    return normalized or "document"
