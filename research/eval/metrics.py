"""Retrieval-метрики: recall@k, MRR, nDCG@k.

Модель релевантности бинарная: ранжированный список — это id извлечённых чанков,
`relevant` — множество id чанков, которые считаются попаданием (содержат gold-блок
QA-пары). integrity / boundary_f1 добавим в неделях 2/4.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence


def recall_at_k(ranked: Sequence[str], relevant: Iterable[str], k: int) -> float:
    """1.0, если хотя бы один релевантный чанк попал в top-k, иначе 0.0.

    (При одном gold-источнике на вопрос recall@k эквивалентен hit@k — доле
    вопросов с попаданием; усредняется по вопросам снаружи.)
    """
    relevant = set(relevant)
    if not relevant:
        return 0.0
    return 1.0 if any(item in relevant for item in ranked[:k]) else 0.0


def reciprocal_rank(ranked: Sequence[str], relevant: Iterable[str]) -> float:
    """1/позиция первого релевантного (1-based); 0, если не найден."""
    relevant = set(relevant)
    for i, item in enumerate(ranked, start=1):
        if item in relevant:
            return 1.0 / i
    return 0.0


def ndcg_at_k(ranked: Sequence[str], relevant: Iterable[str], k: int) -> float:
    """nDCG@k с бинарной релевантностью."""
    relevant = set(relevant)
    if not relevant:
        return 0.0
    dcg = 0.0
    for i, item in enumerate(ranked[:k], start=1):
        if item in relevant:
            dcg += 1.0 / math.log2(i + 1)
    ideal_hits = min(len(relevant), k)
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, ideal_hits + 1))
    return dcg / idcg if idcg > 0 else 0.0


def aggregate(
    per_query_rankings: Sequence[tuple[Sequence[str], Iterable[str]]],
    ks: Sequence[int] = (1, 5, 10),
) -> dict[str, float]:
    """Средние метрики по всем запросам.

    `per_query_rankings` — список (ranked_ids, relevant_ids) на каждый вопрос.
    Возвращает recall@k для каждого k, MRR, nDCG@k для каждого k.
    """
    n = len(per_query_rankings)
    if n == 0:
        return {}
    out: dict[str, float] = {}
    for k in ks:
        out[f"recall@{k}"] = (
            sum(recall_at_k(r, rel, k) for r, rel in per_query_rankings) / n
        )
        out[f"ndcg@{k}"] = (
            sum(ndcg_at_k(r, rel, k) for r, rel in per_query_rankings) / n
        )
    out["mrr"] = sum(reciprocal_rank(r, rel) for r, rel in per_query_rankings) / n
    return out
