"""Прогон бейзлайн-чанкеров через retrieval → таблица метрик.

Пайплайн: IR-документы → чанкер (по имени) → эмбеддинги чанков →
in-memory cosine retrieval по вопросам → recall@k / MRR / nDCG@k.

Retrieval здесь in-memory (numpy), без pgvector — бенчмарк не зависит от БД.
Релевантность: чанк релевантен вопросу, если он из того же документа и его
`block_ids` пересекаются с `source_block_ids` gold-разметки.

Провайдер эмбеддингов:
  --provider local    (sentence-transformers multilingual-e5-large, 1024-dim,
                       БЕЗ API-ключа — рекомендуется для baseline-цифр без затрат)
  --provider voyage   (нужен APP_VOYAGE_API_KEY; каноничный для продукта)
  --provider openai   (нужен APP_OPENAI_API_KEY)
  --provider hash     (детерминированный локальный БЕЗ модели — только smoke-тест
                       пайплайна, цифры нерепрезентативны)

Использование:
    python -m research.eval.run_retrieval --chunker fixed_size,recursive,markdown_split --provider local
    python -m research.eval.run_retrieval --chunker markdown_split --provider hash
"""

from __future__ import annotations

import argparse
import hashlib

import research  # noqa: F401  — bootstrap sys.path

from technical_document_ml_service.chunking.chunkers import get_chunker
from technical_document_ml_service.rag.embeddings import (
    EmbeddingConfig,
    get_embedding_provider,
)

from research.eval.datasets import load_ir, load_qa
from research.eval.metrics import aggregate


# --- локальный детерминированный эмбеддер для offline smoke -------------------
class _HashEmbedder:
    """Хэш-мешок токенов → нормированный вектор. Только для проверки плумбинга."""

    def __init__(self, dim: int = 512) -> None:
        self.dim = dim

    def _vec(self, text: str):
        import numpy as np

        v = np.zeros(self.dim, dtype="float32")
        for tok in text.lower().split():
            h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
            v[h % self.dim] += 1.0
        norm = float(np.linalg.norm(v))
        return v / norm if norm > 0 else v

    def embed_documents(self, texts):
        import numpy as np

        return np.array([self._vec(t) for t in texts], dtype="float32")

    def embed_query(self, text):
        return self._vec(text)


def _build_provider(name: str):
    if name == "hash":
        return _HashEmbedder()
    if name == "voyage":
        return get_embedding_provider(EmbeddingConfig.voyage())
    if name == "openai":
        return get_embedding_provider(EmbeddingConfig.openai())
    if name == "local":
        return get_embedding_provider(EmbeddingConfig.local())
    raise SystemExit(f"неизвестный provider: {name}")


def _cosine_rank(query_vec, doc_matrix):
    """Индексы чанков по убыванию косинуса к запросу."""
    import numpy as np

    q = np.asarray(query_vec, dtype="float32")
    m = np.asarray(doc_matrix, dtype="float32")
    qn = np.linalg.norm(q) or 1.0
    mn = np.linalg.norm(m, axis=1)
    mn[mn == 0] = 1.0
    sims = (m @ q) / (mn * qn)
    return np.argsort(-sims)


def evaluate_chunker(chunker_name: str, docs, qa_pairs, provider, ks):
    import numpy as np

    chunker = get_chunker(chunker_name)
    all_chunks = []
    for doc in docs.values():
        all_chunks.extend(chunker.chunk(doc))
    if not all_chunks:
        return {}, 0, 0

    texts = [c.text for c in all_chunks]
    matrix = np.asarray(provider.embed_documents(texts), dtype="float32")

    rankings = []
    for qa in qa_pairs:
        gold = set(qa.source_block_ids)
        relevant = {
            c.id
            for c in all_chunks
            if c.doc_id == qa.doc_id and gold.intersection(c.block_ids)
        }
        if not relevant:
            continue  # gold-блок не покрыт этим чанкером — пропускаем вопрос
        order = _cosine_rank(provider.embed_query(qa.question), matrix)
        ranked_ids = [all_chunks[i].id for i in order]
        rankings.append((ranked_ids, relevant))

    return aggregate(rankings, ks), len(all_chunks), len(rankings)


def _print_table(results: dict[str, dict], ks) -> None:
    cols = [f"recall@{k}" for k in ks] + ["mrr"] + [f"ndcg@{k}" for k in ks]
    header = f"{'chunker':<18} {'chunks':>7} {'queries':>8}  " + "  ".join(
        f"{c:>9}" for c in cols
    )
    print(header)
    print("-" * len(header))
    for name, (metrics, n_chunks, n_q) in results.items():
        cells = "  ".join(f"{metrics.get(c, 0.0):>9.4f}" for c in cols)
        print(f"{name:<18} {n_chunks:>7} {n_q:>8}  {cells}")


def main() -> int:
    parser = argparse.ArgumentParser(description="retrieval-метрики по бейзлайнам")
    parser.add_argument(
        "--chunker",
        default="fixed_size,recursive,markdown_split",
        help="csv имён чанкеров",
    )
    parser.add_argument(
        "--provider", default="local", choices=["local", "voyage", "openai", "hash"]
    )
    parser.add_argument("--k", default="1,5,10", help="csv значений k")
    parser.add_argument("--validated-only", action="store_true")
    args = parser.parse_args()

    ks = [int(x) for x in args.k.split(",")]
    docs = load_ir()
    qa_pairs = load_qa(validated_only=args.validated_only)
    if not docs:
        print("нет IR-документов (research/data/ir/). Сначала parse_corpus.")
        return 1
    if not qa_pairs:
        print("нет QA-пар (research/data/qa/qa.jsonl). Сначала generate_qa.")
        return 1

    provider = _build_provider(args.provider)
    print(
        f"документов: {len(docs)}, QA-пар: {len(qa_pairs)}, provider: {args.provider}\n"
    )

    results = {}
    for name in [c.strip() for c in args.chunker.split(",") if c.strip()]:
        metrics, n_chunks, n_q = evaluate_chunker(name, docs, qa_pairs, provider, ks)
        results[name] = (metrics, n_chunks, n_q)

    _print_table(results, ks)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
