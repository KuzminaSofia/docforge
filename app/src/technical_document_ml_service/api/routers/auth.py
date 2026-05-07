from __future__ import annotations

from fastapi import APIRouter, Response, status

from technical_document_ml_service.api.deps import ReadSessionDep, SessionDep
from technical_document_ml_service.api.schemas.auth import (
    AuthResponse,
    LoginRequest,
    LogoutResponse,
    RegisterRequest,
    TokenResponse,
)
from technical_document_ml_service.api.schemas.users import UserResponse
from technical_document_ml_service.core.auth_cookies import delete_auth_cookie, set_auth_cookie
from technical_document_ml_service.core.security import build_access_token
from technical_document_ml_service.services.auth_service import (
    authenticate_user,
    register_user,
)


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(payload: RegisterRequest, session: SessionDep) -> AuthResponse:
    """зарегистрировать нового пользователя"""
    user = register_user(
        session,
        email=payload.email,
        password=payload.password,
    )

    return AuthResponse(
        message="Пользователь успешно зарегистрирован.",
        user=UserResponse.from_domain(user),
    )


@router.post("/login", response_model=AuthResponse)
def login(
    payload: LoginRequest,
    response: Response,
    session: ReadSessionDep,
) -> AuthResponse:
    """
    аутентифицировать пользователя по email и паролю

    Для удобства Web UI endpoint также устанавливает JWT cookie.
    При этом контракт ответа остается прежним.
    """
    user = authenticate_user(
        session,
        email=payload.email,
        password=payload.password,
    )

    access_token, expires_in_seconds = build_access_token(
        user_id=user.id,
        email=user.email,
    )
    set_auth_cookie(response, access_token, expires_in_seconds)

    return AuthResponse(
        message="Аутентификация прошла успешно.",
        user=UserResponse.from_domain(user),
    )


@router.post("/token", response_model=TokenResponse)
def issue_access_token(
    payload: LoginRequest,
    response: Response,
    session: ReadSessionDep,
) -> TokenResponse:
    """
    аутентифицировать пользователя и выдать JWT access token

    endpoint полезен для клиентов, которым нужен токен в теле ответа.
    Также устанавливает auth-cookie.
    """
    user = authenticate_user(
        session,
        email=payload.email,
        password=payload.password,
    )

    access_token, expires_in_seconds = build_access_token(
        user_id=user.id,
        email=user.email,
    )
    set_auth_cookie(response, access_token, expires_in_seconds)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in_seconds=expires_in_seconds,
        user=UserResponse.from_domain(user),
    )


@router.post("/logout", response_model=LogoutResponse)
def logout(response: Response) -> LogoutResponse:
    """
    очистить JWT cookie текущего пользователя

    Endpoint намеренно не требует обязательной авторизации:
    logout должен быть идемпотентным и успешно очищать cookie,
    даже если пользователь уже разлогинен или токен истек.
    """
    delete_auth_cookie(response)
    return LogoutResponse(message="Вы успешно вышли из системы.")