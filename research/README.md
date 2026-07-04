# research — оффлайн-бенчмарк чанкеров и RAG

Меряет качество retrieval/RAG на корпусе техдоков. **Не деплоится** и не входит в
рантайм сервиса: импортирует `chunking/` и `rag/` из основного пакета (та же
реализация, что и в продукте), но живёт отдельно и запускается вручную.

## Установка (один раз)

```bash
pip install -r research/requirements.txt
```

`sentence-transformers` тянет torch — ставится только там, где реально гоняешь
`--provider local`. Для Voyage/OpenAI он не нужен.

## Ключи (впиши один раз)

```bash
cp research/.env.example research/.env
#   → открой research/.env и вставь ключи (файл в .gitignore)
```

| env | зачем | обязателен? |
|---|---|---|
| `APP_DATALAB_API_KEY` | парсинг PDF → json+bbox (`parse_corpus`) | если нет сохранённого json |
| `APP_LLM_API_KEY` + `APP_LLM_BASE_URL` + `APP_LLM_MODEL` | LLM-генерация QA (OpenRouter) | да, для `generate_qa` |
| `APP_VOYAGE_API_KEY` / `APP_OPENAI_API_KEY` | эмбеддинги через API | нет — по умолчанию `--provider local` без ключа |

Перед прогоном подгрузи переменные в шелл:

```bash
set -a; source research/.env; set +a
```

## Пайплайн недели 1

```bash
# 1. Реестр корпуса (положи 10–20 техдоков в research/data/corpus/raw/)
python -m research.scripts.build_corpus --src research/data/corpus/raw

# 2. Datalab → IR (research/data/ir/<doc_id>.json). bbox только отсюда.
python -m research.scripts.parse_corpus            # нужен APP_DATALAB_API_KEY

# 3. LLM (OpenRouter) генерит QA + разметку блока-источника
python -m research.scripts.generate_qa --per-doc 8 # нужен APP_LLM_* 
#    ⚠️ затем ВРУЧНУЮ проверить ≥100 пар (выставить "validated": true в qa.jsonl)

# 4. Прогон бейзлайнов → таблица метрик (локальные эмбеддинги, без ключа)
python -m research.eval.run_retrieval \
    --chunker fixed_size,recursive,markdown_split --provider local
#    (--provider voyage — если хочешь каноничные для продукта цифры)

# offline smoke без модели и ключей (проверка, что пайплайн жив):
python -m research.eval.run_retrieval --chunker markdown_split --provider hash
```

Baseline-цифры из шага 4 записываем в `research/reports/RESULTS.md` — от них
отталкиваемся в неделях 2–6.

## Разделение труда (сеть/ключи только на твоей машине)

Шаги 2–4 ходят в сеть/API — их запускаешь **ты локально**. IR-json (шаг 2) и
`qa.jsonl` (шаг 3) кладутся в репозиторий (в `.gitignore`, но я вижу файлы) —
после этого я могу свериться с реальным json, доточить `datalab_adapter` под него
и офлайн прогнать чанкеры/тесты.

## Структура

```
research/
  scripts/     build_corpus, parse_corpus, generate_qa
  eval/        datasets, metrics (recall@k/MRR/nDCG), run_retrieval
  data/        corpus/ ir/ qa/ embeddings/   (в .gitignore, кроме .gitkeep)
  reports/     RESULTS.md + графики (нед.6)
```

Кэш эмбеддингов лежит в `research/data/embeddings/` — повторные прогоны не
тратят API-квоту.
