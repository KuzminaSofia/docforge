"""Единый подсчёт токенов на весь проект.

Все чанкеры и метрики считают токены ОДНИМ способом — иначе размеры чанков и
метрики несравнимы между чанкерами. Зафиксировано (нед.1): tiktoken `cl100k_base`.
Если tiktoken не установлен — детерминированный приблизительный fallback
(≈ 4 символа/токен), чтобы бенчмарк работал и в окружении без пакета.
"""

from __future__ import annotations

import math

# --- Зафиксированные константы размера чанка (architecture.md → Конвенции) -----
# Одинаковы для всех чанкеров, чтобы сравнение бейзлайнов было честным.
TARGET_CHUNK_TOKENS = 512
HARD_MAX_CHUNK_TOKENS = 1024

_ENCODING_NAME = "cl100k_base"
_APPROX_CHARS_PER_TOKEN = 4  # грубая, но детерминированная оценка для fallback

# Ленивая инициализация энкодера: платим за импорт tiktoken один раз.
_encoder = None
_encoder_ready = False


def _get_encoder():
    global _encoder, _encoder_ready
    if _encoder_ready:
        return _encoder
    try:
        import tiktoken

        _encoder = tiktoken.get_encoding(_ENCODING_NAME)
    except Exception:
        _encoder = None  # fallback на приблизительный счёт
    _encoder_ready = True
    return _encoder


def count_tokens(text: str) -> int:
    """Число токенов в тексте. tiktoken если доступен, иначе приближение."""
    if not text:
        return 0
    encoder = _get_encoder()
    if encoder is not None:
        return len(encoder.encode(text))
    # Fallback: длина в символах / средняя длина токена, минимум 1 для непустого.
    return max(1, math.ceil(len(text) / _APPROX_CHARS_PER_TOKEN))


def using_tiktoken() -> bool:
    """True, если реально используется tiktoken (полезно в тестах/отчётах)."""
    return _get_encoder() is not None
