from __future__ import annotations


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


def test_dashboard_renders_for_authenticated_user(
    client,
    api_user,
    same_origin_headers,
) -> None:
    _login_web_user(client, same_origin_headers)

    response = client.get("/dashboard")

    assert response.status_code == 200
    assert "Здравствуйте, api.user@example.com" in response.text
    assert "Личный кабинет" in response.text


def test_balance_page_renders_for_authenticated_user(
    client,
    api_user,
    same_origin_headers,
) -> None:
    _login_web_user(client, same_origin_headers)

    response = client.get("/balance-ui")

    assert response.status_code == 200
    assert "Управление балансом" in response.text
    assert "Текущий баланс" in response.text


def test_top_up_via_web_form_updates_balance_and_shows_success(
    client,
    api_user,
    same_origin_headers,
) -> None:
    _login_web_user(client, same_origin_headers)

    response = client.post(
        "/balance-ui/top-up",
        data={"amount": "25.00"},
        headers=same_origin_headers,
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Баланс успешно пополнен." in response.text

    api_balance_response = client.get("/balance")
    assert api_balance_response.status_code == 200
    assert str(api_balance_response.json()["balance_credits"]) in {"125", "125.00"}


def test_top_up_with_invalid_amount_shows_validation_error(
    client,
    api_user,
    same_origin_headers,
) -> None:
    _login_web_user(client, same_origin_headers)

    response = client.post(
        "/balance-ui/top-up",
        data={"amount": "-1"},
        headers=same_origin_headers,
        follow_redirects=True,
    )

    assert response.status_code == 400
    assert "Введите корректную положительную сумму пополнения." in response.text


def test_history_page_renders_server_side(
    client,
    api_user,
    same_origin_headers,
) -> None:
    _login_web_user(client, same_origin_headers)

    client.post(
        "/balance-ui/top-up",
        data={"amount": "10.00"},
        headers=same_origin_headers,
        follow_redirects=False,
    )

    response = client.get("/history-ui")

    assert response.status_code == 200
    assert "Операции и обработки" in response.text
    assert "Транзакции" in response.text
    assert "Обработки" in response.text