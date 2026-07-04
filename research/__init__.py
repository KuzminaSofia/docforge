"""research — оффлайн-бенчмарк чанкеров и RAG. НЕ деплоится, не в рантайме сервиса.

Импортирует `chunking/` и `rag/` из основного пакета (та же реализация, что и в
продукте), но живёт отдельно. Здесь — bootstrap: кладём `app/src` в sys.path,
чтобы `python -m research.*` работал из корня репозитория без editable-install.
"""

from __future__ import annotations

import sys
from pathlib import Path

_APP_SRC = Path(__file__).resolve().parents[1] / "app" / "src"
if _APP_SRC.is_dir() and str(_APP_SRC) not in sys.path:
    sys.path.insert(0, str(_APP_SRC))
