from __future__ import annotations

"""
сценарные system-тесты для задания 7

данный файл предназначен:
- для проверки системы как единого целого
- для покрытия критичных пользовательских сценариев
- для подтверждения корректности бизнес-логики на уровне всего приложения

данные тесты проходят по полному пользовательскому пути и дополнительно проверяют бизнес-логику:
- изменение баланса
- создание задач
- появление результата
- запись истории
- отсутсвие побочных эффектов при ошибках
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from technical_document_ml_service.db.models import (
    MLRequestHistoryORM,
    MLTaskORM,
    PredictionResultORM,
    TransactionORM,
    UserORM,
)
from technical_document_ml_service.db.session import SessionLocal
from technical_document_ml_service.services.prediction_processing_service import (
    process_document_prediction_task,
)


def _pdf_files() -> list[tuple[str, tuple[str, bytes, str]]]:
    return [
        (
            "document",
            ("sample.pdf", b"%PDF-1.4 test content", "application/pdf"),
        )
    ]


def test_full_user_journey_success(
    client,
    api_model,
    basic_auth_header_factory,
    publish_task_spy,
) -> None:
    """
    проверяет основной успешный сценарий пользователя:
    1 пользователь регистрируется
    2 выполняет авторизацию
    3 получает начальных баланс
    4 пополняет баланс
    5 отправляет ML-задачу на обработку
    6 задача обрабатывается воркерным сцерарием
    7 пользователь получает результат
    8 пользователь видит корректную историю транзакций и предсказаний

    тест подтверждает:
    - система поддерживает полный пользовательский путь без разрывов
    - успешная ML-обработка приводит к списанию стоимости модели
    - результат обработки сохраняется и доступен пользователю
    - история операций согласована с выполненными дейсвиями
    """
    email = "system.flow.user@example.com"
    password = "strongpass123"

    register_response = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": password,
        },
    )
    assert register_response.status_code == 201

    login_response = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": password,
        },
    )
    assert login_response.status_code == 200

    auth_headers = basic_auth_header_factory(email, password)

    initial_balance_response = client.get("/balance", headers=auth_headers)
    assert initial_balance_response.status_code == 200
    assert Decimal(str(initial_balance_response.json()["balance_credits"])) == Decimal("0.00")

    top_up_response = client.post(
        "/balance/top-up",
        json={"amount": "25.00"},
        headers=auth_headers,
    )
    assert top_up_response.status_code == 200
    assert Decimal(str(top_up_response.json()["balance_credits"])) == Decimal("25.00")

    predict_response = client.post(
        "/predict",
        data={
            "model_name": api_model.name,
            "target_schema": "passport_fields",
        },
        files=_pdf_files(),
        headers=auth_headers,
    )
    assert predict_response.status_code == 202

    predict_body = predict_response.json()
    task_id = predict_body["task_id"]

    assert predict_body["status"] == "queued"
    assert len(publish_task_spy) == 1

    with SessionLocal() as session:
        processing_result = process_document_prediction_task(
            session,
            task_id=task_id,
        )

    assert processing_result.was_processed is True
    assert processing_result.status.value == "completed"
    assert processing_result.result_id is not None

    task_result_response = client.get(
        f"/tasks/{task_id}/result",
        headers=auth_headers,
    )
    assert task_result_response.status_code == 200

    task_result_body = task_result_response.json()
    assert task_result_body["task"]["id"] == task_id
    assert task_result_body["task"]["status"] == "completed"
    assert task_result_body["has_result"] is True
    assert task_result_body["result"] is not None

    final_balance_response = client.get("/balance", headers=auth_headers)
    assert final_balance_response.status_code == 200
    assert Decimal(str(final_balance_response.json()["balance_credits"])) == Decimal("15.00")

    transactions_history_response = client.get(
        "/history/transactions",
        headers=auth_headers,
    )
    assert transactions_history_response.status_code == 200

    transactions_items = transactions_history_response.json()["items"]
    assert len(transactions_items) == 2

    amounts_by_type = {
        item["transaction_type"]: Decimal(str(item["amount"]))
        for item in transactions_items
    }
    assert amounts_by_type["credit"] == Decimal("25.00")
    assert amounts_by_type["debit"] == Decimal("10.00")

    predictions_history_response = client.get(
        "/history/predictions",
        headers=auth_headers,
    )
    assert predictions_history_response.status_code == 200

    predictions_items = predictions_history_response.json()["items"]
    assert len(predictions_items) == 1
    assert predictions_items[0]["task_id"] == task_id
    assert predictions_items[0]["status"] == "completed"
    assert predictions_items[0]["result_id"] is not None


def test_user_can_login_twice_in_a_row(
    client,
    api_user,
    auth_headers,
) -> None:
    """
    проверяет сценарий повторной авторизации пользователя

    1 пользователь логинится первый раз
    2 пользователь логинится второй раз с теми же данными
    3 после повторной авторизации может обратиться к защищенному API

    тест подтверждает:
    - повторная авторизация не ломает состояния системы
    - валидные учетные данные стабильно принимаются
    - защищенный эндпоинт остается доступен после повторного входа
    """
    payload = {
        "email": "api.user@example.com",
        "password": "test-password",
    }

    first_login_response = client.post("/auth/login", json=payload)
    assert first_login_response.status_code == 200
    assert first_login_response.json()["user"]["email"] == "api.user@example.com"

    second_login_response = client.post("/auth/login", json=payload)
    assert second_login_response.status_code == 200
    assert second_login_response.json()["user"]["email"] == "api.user@example.com"

    balance_response = client.get("/balance", headers=auth_headers)
    assert balance_response.status_code == 200
    assert Decimal(str(balance_response.json()["balance_credits"])) == Decimal("100.00")


def test_predict_with_insufficient_balance_preserves_user_state(
    client,
    low_balance_user,
    api_model,
    low_balance_auth_headers,
    publish_task_spy,
) -> None:
    """
    проверяет отказ в запуске ML-задачи при недостаточном балансе

    1 пользователь с недостаточным балансом отправляет predict-запрос
    2 сисетма отклоняет запрос
    3 после отказа проверяется состояние пользователя и системы

    тест подтверждает:
    - задача не ставится в очередь
    - баланс не изменяется
    - транзакции списания не создаются
    - история предсказаний не пополняется ложной записью
    - отсутсвие средств корректно обрабатывается как бизнес-ошибка
    """
    initial_balance_response = client.get("/balance", headers=low_balance_auth_headers)
    assert initial_balance_response.status_code == 200
    assert Decimal(str(initial_balance_response.json()["balance_credits"])) == Decimal("5.00")

    predict_response = client.post(
        "/predict",
        data={
            "model_name": api_model.name,
            "target_schema": "passport_fields",
        },
        files=_pdf_files(),
        headers=low_balance_auth_headers,
    )
    assert predict_response.status_code == 409
    assert predict_response.json()["error"]["code"] == "insufficient_balance"

    assert len(publish_task_spy) == 0

    final_balance_response = client.get("/balance", headers=low_balance_auth_headers)
    assert final_balance_response.status_code == 200
    assert Decimal(str(final_balance_response.json()["balance_credits"])) == Decimal("5.00")

    transactions_history_response = client.get(
        "/history/transactions",
        headers=low_balance_auth_headers,
    )
    assert transactions_history_response.status_code == 200
    assert transactions_history_response.json()["items"] == []

    predictions_history_response = client.get(
        "/history/predictions",
        headers=low_balance_auth_headers,
    )
    assert predictions_history_response.status_code == 200
    assert predictions_history_response.json()["items"] == []

    tasks_response = client.get("/tasks", headers=low_balance_auth_headers)
    assert tasks_response.status_code == 200
    assert tasks_response.json()["items"] == []


class _CrashingBackend:
    def process(self, request):
        raise RuntimeError("backend crashed in test")


def test_failed_prediction_does_not_debit_balance(
    client,
    api_user,
    api_model,
    auth_headers,
    publish_task_spy,
    monkeypatch,
) -> None:
    """
    проверяет что ошибка backend-обработки (ml-модели) не приводит к списанию средств

    1 пользователь успешно отправляет задачу
    2 на этапе processing backend аварийно завершается
    3 система переводит задачу в статус failed
    4 после ошибки проверяется состояние баланса и хранилища данных

    тест подтверждает:
    - ошибка processing корректно фиксируется в задаче
    - баланс пользователя не уменьшается
    - транзакция списания не создается
    - результат обработки не сохраняется
    - история успешных предсказаний не создается по ошибочной задаче
    """
    predict_response = client.post(
        "/predict",
        data={
            "model_name": api_model.name,
            "target_schema": "passport_fields",
        },
        files=_pdf_files(),
        headers=auth_headers,
    )
    assert predict_response.status_code == 202

    task_id = predict_response.json()["task_id"]

    monkeypatch.setattr(
        "technical_document_ml_service.services.prediction_processing_service.select_prediction_backend",
        lambda requested_backend_name, backend_config: SimpleNamespace(
            resolved_backend_name="crashing-backend",
            backend=_CrashingBackend(),
        ),
    )

    with pytest.raises(RuntimeError, match="backend crashed in test"):
        with SessionLocal() as session:
            process_document_prediction_task(
                session,
                task_id=task_id,
            )

    with SessionLocal() as session:
        task = session.get(MLTaskORM, task_id)
        assert task is not None
        assert task.status == "failed"
        assert task.error_message == "backend crashed in test"
        assert task.spent_credits == Decimal("0.00")

        user = session.get(UserORM, api_user.id)
        assert user is not None
        assert user.balance_credits == Decimal("100.00")

        prediction_results_count = session.scalar(
            select(func.count()).select_from(PredictionResultORM)
        )
        transactions_count = session.scalar(
            select(func.count()).select_from(TransactionORM)
        )
        history_count = session.scalar(
            select(func.count()).select_from(MLRequestHistoryORM)
        )

        assert prediction_results_count == 0
        assert transactions_count == 0
        assert history_count == 0

    task_result_response = client.get(
        f"/tasks/{task_id}/result",
        headers=auth_headers,
    )
    assert task_result_response.status_code == 200

    task_result_body = task_result_response.json()
    assert task_result_body["task"]["id"] == task_id
    assert task_result_body["task"]["status"] == "failed"
    assert task_result_body["result"] is None
    assert task_result_body["has_result"] is False

    final_balance_response = client.get("/balance", headers=auth_headers)
    assert final_balance_response.status_code == 200
    assert Decimal(str(final_balance_response.json()["balance_credits"])) == Decimal("100.00")