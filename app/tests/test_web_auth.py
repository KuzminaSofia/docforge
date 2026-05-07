from __future__ import annotations

from technical_document_ml_service.core.security import get_auth_cookie_name


def test_home_page_renders(client) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "DocForge" in response.text
    assert "Личный кабинет для обработки технической документации" in response.text


def test_dashboard_redirects_for_guest(client) -> None:
    response = client.get("/dashboard", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_login_page_renders_for_guest(client) -> None:
    response = client.get("/login")

    assert response.status_code == 200
    assert "<h1>Вход</h1>" in response.text


def test_register_page_renders_for_guest(client) -> None:
    response = client.get("/register")

    assert response.status_code == 200
    assert "<h1>Регистрация</h1>" in response.text


def test_web_login_success_sets_cookie_and_redirects(
    client,
    api_user,
    same_origin_headers,
) -> None:
    payload = {
        "email": "api.user@example.com",
        "password": "test-password",
    }

    response = client.post(
        "/login",
        data=payload,
        headers=same_origin_headers,
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"

    auth_cookie_name = get_auth_cookie_name()
    assert auth_cookie_name in client.cookies


def test_web_login_without_same_origin_is_forbidden(client, api_user) -> None:
    payload = {
        "email": "api.user@example.com",
        "password": "test-password",
    }

    response = client.post(
        "/login",
        data=payload,
        follow_redirects=False,
    )

    assert response.status_code == 403


def test_web_login_with_invalid_password_shows_error(
    client,
    api_user,
    same_origin_headers,
) -> None:
    payload = {
        "email": "api.user@example.com",
        "password": "wrong-password",
    }

    response = client.post(
        "/login",
        data=payload,
        headers=same_origin_headers,
    )

    assert response.status_code == 401
    assert "Неверный email или пароль." in response.text


def test_web_register_success_sets_cookie_and_redirects(
    client,
    same_origin_headers,
) -> None:
    payload = {
        "email": "web.new.user@example.com",
        "password": "strongpass123",
    }

    response = client.post(
        "/register",
        data=payload,
        headers=same_origin_headers,
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"

    auth_cookie_name = get_auth_cookie_name()
    assert auth_cookie_name in client.cookies


def test_web_logout_clears_cookie(
    client,
    api_user,
    same_origin_headers,
) -> None:
    login_response = client.post(
        "/login",
        data={
            "email": "api.user@example.com",
            "password": "test-password",
        },
        headers=same_origin_headers,
        follow_redirects=False,
    )
    assert login_response.status_code == 303

    auth_cookie_name = get_auth_cookie_name()
    assert auth_cookie_name in client.cookies

    logout_response = client.post(
        "/logout",
        headers=same_origin_headers,
        follow_redirects=False,
    )

    assert logout_response.status_code == 303
    assert logout_response.headers["location"] == "/"
    assert auth_cookie_name not in client.cookies