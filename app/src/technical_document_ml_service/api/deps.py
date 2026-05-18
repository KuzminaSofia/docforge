from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBasic,
    HTTPBasicCredentials,
    HTTPBearer,
)
from sqlalchemy.orm import Session

from technical_document_ml_service.core.security import (
    decode_access_token,
    get_auth_cookie_name,
)
from technical_document_ml_service.db.session import SessionLocal, get_db_session, get_plain_session, get_read_session
from technical_document_ml_service.domain.entities import User
from technical_document_ml_service.domain.exceptions import AuthenticationError
from technical_document_ml_service.services.auth_service import authenticate_user
from technical_document_ml_service.services.user_service import get_user_by_email


http_basic = HTTPBasic(auto_error=False)
http_bearer = HTTPBearer(auto_error=False)

SessionDep = Annotated[Session, Depends(get_db_session)]
ReadSessionDep = Annotated[Session, Depends(get_read_session)]
PlainSessionDep = Annotated[Session, Depends(get_plain_session)]


def _authenticate_from_credentials(
    credentials: HTTPBasicCredentials | None,
    session: Session,
) -> User:
    """выполнить аутентификацию пользователя по Basic Auth"""
    if credentials is None:
        raise AuthenticationError("Не переданы учетные данные.")

    return authenticate_user(
        session,
        email=credentials.username,
        password=credentials.password,
    )


def _authenticate_from_jwt_token(token: str, session: Session) -> User:
    """выполнить аутентификацию пользователя по JWT"""
    payload = decode_access_token(token)

    email = payload.get("sub")
    token_user_id = payload.get("user_id")

    if not isinstance(email, str) or not email:
        raise AuthenticationError("Токен не содержит email пользователя.")

    if token_user_id is not None and not isinstance(token_user_id, str):
        raise AuthenticationError("Токен содержит некорректный идентификатор пользователя.")

    user = get_user_by_email(session, email=email)
    if user is None:
        raise AuthenticationError("Пользователь из токена не найден.")

    if token_user_id is not None and str(user.id) != token_user_id:
        raise AuthenticationError("Токен содержит некорректные данные пользователя.")

    if not user.is_active:
        raise AuthenticationError("Пользователь деактивирован.")

    return user


def _extract_jwt_token(
    request: Request,
    bearer_credentials: HTTPAuthorizationCredentials | None,
) -> str | None:
    """извлечь JWT из Bearer Authorization или cookie"""
    if bearer_credentials is not None:
        if bearer_credentials.scheme.lower() != "bearer":
            raise AuthenticationError("Неподдерживаемая схема авторизации.")
        return bearer_credentials.credentials

    cookie_name = get_auth_cookie_name()
    cookie_token = request.cookies.get(cookie_name)
    if cookie_token:
        return cookie_token

    return None


def authenticate_request(
    *,
    request: Request,
    session: Session,
    basic_credentials: HTTPBasicCredentials | None,
    bearer_credentials: HTTPAuthorizationCredentials | None,
) -> User:
    """
    получить текущего пользователя по одной из схем:
    1. Basic Auth
    2. Bearer token
    3. JWT cookie
    """
    if basic_credentials is not None:
        return _authenticate_from_credentials(basic_credentials, session)

    token = _extract_jwt_token(request, bearer_credentials)
    if token:
        return _authenticate_from_jwt_token(token, session)

    raise AuthenticationError("Не переданы учетные данные.")


def get_current_user(
    request: Request,
    session: SessionDep,
    basic_credentials: Annotated[HTTPBasicCredentials | None, Depends(http_basic)],
    bearer_credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(http_bearer),
    ],
) -> User:
    """получить текущего пользователя через write-session"""
    return authenticate_request(
        request=request,
        session=session,
        basic_credentials=basic_credentials,
        bearer_credentials=bearer_credentials,
    )


def get_current_read_user(
    request: Request,
    session: ReadSessionDep,
    basic_credentials: Annotated[HTTPBasicCredentials | None, Depends(http_basic)],
    bearer_credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(http_bearer),
    ],
) -> User:
    """получить текущего пользователя через read-session"""
    return authenticate_request(
        request=request,
        session=session,
        basic_credentials=basic_credentials,
        bearer_credentials=bearer_credentials,
    )


CurrentUserDep = Annotated[User, Depends(get_current_user)]
CurrentReadUserDep = Annotated[User, Depends(get_current_read_user)]


def get_user_id_for_sse(
    request: Request,
    basic_credentials: Annotated[HTTPBasicCredentials | None, Depends(http_basic)],
    bearer_credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(http_bearer),
    ],
) -> UUID:
    """аутентификация для SSE: открывает сессию только для auth, сразу закрывает, возвращает user_id"""
    session = SessionLocal()
    try:
        user = authenticate_request(
            request=request,
            session=session,
            basic_credentials=basic_credentials,
            bearer_credentials=bearer_credentials,
        )
        return user.id
    finally:
        session.rollback()
        session.close()


UserIdForSSEDep = Annotated[UUID, Depends(get_user_id_for_sse)]