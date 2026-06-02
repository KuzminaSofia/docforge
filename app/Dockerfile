FROM python:3.11-slim AS base
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt
ENV PYTHONPATH=/app/src

# migrate: init-контейнер — запускает alembic upgrade head + seed, затем завершается
FROM base AS migrate
COPY src /app/src
COPY alembic /app/alembic
COPY alembic.ini /app/alembic.ini
CMD ["python", "-m", "technical_document_ml_service.db.migrate"]

# development: добавляет тестовые зависимости и тесты для docker compose run pytest
FROM base AS development
COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY src /app/src
COPY tests /app/tests
CMD ["uvicorn", "technical_document_ml_service.main:app", "--host", "0.0.0.0", "--port", "8000"]

# production: только prod-зависимости, без тестов
FROM base AS production
COPY src /app/src
CMD ["uvicorn", "technical_document_ml_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
