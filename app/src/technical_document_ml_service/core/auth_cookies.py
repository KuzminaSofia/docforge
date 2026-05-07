from __future__ import annotations

from starlette.responses import Response

from technical_document_ml_service.core.security import (
    get_auth_cookie_name,
    is_auth_cookie_secure,
)


def set_auth_cookie(
    response: Response,
    access_token: str,
    expires_in_seconds: int,
) -> None:
    """установить HttpOnly cookie с JWT access token"""
    response.set_cookie(
        key=get_auth_cookie_name(),
        value=access_token,
        max_age=expires_in_seconds,
        expires=expires_in_seconds,
        path="/",
        httponly=True,
        samesite="lax",
        secure=is_auth_cookie_secure(),
    )


def delete_auth_cookie(response: Response) -> None:
    """удалить HttpOnly cookie с JWT access token"""
    response.delete_cookie(
        key=get_auth_cookie_name(),
        path="/",
        httponly=True,
        samesite="lax",
        secure=is_auth_cookie_secure(),
    )
