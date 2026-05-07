from __future__ import annotations

import re


def _login_web_user(client, same_origin_headers) -> None:
    response = client.post(
        "/login",
        data={
            "email": "api.user@example.com",
            "password": "test-password",
        },
        headers=same_origin_headers,
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_predict_page_renders_for_authenticated_user(
    client,
    api_user,
    api_model,
    same_origin_headers,
) -> None:
    _login_web_user(client, same_origin_headers)

    response = client.get("/predict-ui")

    assert response.status_code == 200
    assert "Новая обработка документа" in response.text
    assert api_model.name in response.text


def test_predict_submit_without_documents_shows_error(
    client,
    api_user,
    api_model,
    same_origin_headers,
) -> None:
    _login_web_user(client, same_origin_headers)

    response = client.post(
        "/predict-ui",
        data={
            "model_name": api_model.name,
            "target_schema": "default_schema",
        },
        headers=same_origin_headers,
        follow_redirects=True,
    )

    assert response.status_code == 400
    assert "Нужно загрузить хотя бы один документ." in response.text


def test_predict_submit_redirects_to_task_detail_page(
    client,
    api_user,
    api_model,
    publish_task_spy,
    same_origin_headers,
) -> None:
    _login_web_user(client, same_origin_headers)

    response = client.post(
        "/predict-ui",
        data={
            "model_name": api_model.name,
            "target_schema": "default_schema",
        },
        files=[
            (
                "documents",
                ("test.pdf", b"%PDF-1.4 test payload", "application/pdf"),
            )
        ],
        headers=same_origin_headers,
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith("/tasks-ui/")

    assert len(publish_task_spy) == 1


def test_tasks_page_renders_and_filters_queued_tasks(
    client,
    api_user,
    api_model,
    publish_task_spy,
    same_origin_headers,
) -> None:
    _login_web_user(client, same_origin_headers)

    submit_response = client.post(
        "/predict-ui",
        data={
            "model_name": api_model.name,
            "target_schema": "default_schema",
        },
        files=[
            (
                "documents",
                ("queued-task.pdf", b"%PDF-1.4 queued task", "application/pdf"),
            )
        ],
        headers=same_origin_headers,
        follow_redirects=False,
    )
    assert submit_response.status_code == 303

    response = client.get("/tasks-ui?status=queued&limit=50&offset=0")

    assert response.status_code == 200
    assert "История обработок" in response.text
    assert "ID обработки" in response.text
    assert "queued-task.pdf" in response.text
    assert "преобразование" in response.text
    assert "queued" in response.text


def test_task_detail_page_renders_after_submit(
    client,
    api_user,
    api_model,
    publish_task_spy,
    same_origin_headers,
) -> None:
    _login_web_user(client, same_origin_headers)

    submit_response = client.post(
        "/predict-ui",
        data={
            "model_name": api_model.name,
            "target_schema": "default_schema",
        },
        files=[
            (
                "documents",
                ("detail-view.pdf", b"%PDF-1.4 detail task", "application/pdf"),
            )
        ],
        headers=same_origin_headers,
        follow_redirects=False,
    )
    assert submit_response.status_code == 303

    task_location = submit_response.headers["location"]

    response = client.get(task_location)

    assert response.status_code == 200
    assert "Преобразование" in response.text
    assert "detail-view.pdf" in response.text
    assert api_model.name in response.text

    assert "Обработка документа" in response.text

    assert "Результат преобразования" in response.text
    assert "Markdown" in response.text
    assert "Артефакты" in response.text
    assert "JSON результата" in response.text


def test_task_filter_with_invalid_status_shows_error_on_page(
    client,
    api_user,
    same_origin_headers,
) -> None:
    _login_web_user(client, same_origin_headers)

    response = client.get("/tasks-ui?status=not-a-valid-status&limit=20&offset=0")

    assert response.status_code == 200
    assert "Некорректный фильтр статуса." in response.text
    assert "created, queued, validating, processing, completed, failed" in response.text


def test_predict_page_contains_balance_and_cost_widgets(
    client,
    api_user,
    api_model,
    same_origin_headers,
) -> None:
    _login_web_user(client, same_origin_headers)

    response = client.get("/predict-ui")

    assert response.status_code == 200
    assert "Проверка баланса" in response.text
    assert api_model.name in response.text
    assert re.search(r"100(?:\.00)?", response.text) is not None