from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from technical_document_ml_service.domain.exceptions import (
    AuthenticationError,
    AuthorizationError,
    DomainError,
    FileSizeLimitError,
    InsufficientBalanceError,
    InvalidAmountError,
    ModelUnavailableError,
    NotFoundError,
    TaskExecutionError,
    UserAlreadyExistsError,
)


def _error_payload(
    *,
    code: str,
    message: str,
    details: Any | None = None,
) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
        }
    }


def register_exception_handlers(app: FastAPI) -> None:
    """зарегистрировать единые обработчики исключений API"""

    @app.exception_handler(UserAlreadyExistsError)
    async def handle_user_exists(_: Request, exc: UserAlreadyExistsError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=_error_payload(
                code="user_already_exists",
                message=str(exc),
            ),
        )

    @app.exception_handler(NotFoundError)
    async def handle_not_found(_: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=_error_payload(
                code="not_found",
                message=str(exc),
            ),
        )

    @app.exception_handler(AuthenticationError)
    async def handle_authentication(_: Request, exc: AuthenticationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": "Basic"},
            content=_error_payload(
                code="authentication_failed",
                message=str(exc),
            ),
        )

    @app.exception_handler(AuthorizationError)
    async def handle_authorization(_: Request, exc: AuthorizationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=_error_payload(
                code="forbidden",
                message=str(exc),
            ),
        )

    @app.exception_handler(InsufficientBalanceError)
    async def handle_balance(_: Request, exc: InsufficientBalanceError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=_error_payload(
                code="insufficient_balance",
                message=str(exc),
            ),
        )

    @app.exception_handler(InvalidAmountError)
    async def handle_invalid_amount(_: Request, exc: InvalidAmountError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=_error_payload(
                code="invalid_amount",
                message=str(exc),
            ),
        )

    @app.exception_handler(ModelUnavailableError)
    async def handle_model_unavailable(_: Request, exc: ModelUnavailableError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=_error_payload(
                code="model_unavailable",
                message=str(exc),
            ),
        )

    @app.exception_handler(FileSizeLimitError)
    async def handle_file_size_limit(_: Request, exc: FileSizeLimitError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            content=_error_payload(
                code="file_size_limit_exceeded",
                message=str(exc),
            ),
        )

    @app.exception_handler(TaskExecutionError)
    async def handle_task_execution(_: Request, exc: TaskExecutionError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=_error_payload(
                code="task_execution_error",
                message=str(exc),
            ),
        )

    @app.exception_handler(DomainError)
    async def handle_domain_error(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=_error_payload(
                code="domain_error",
                message=str(exc),
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_error_payload(
                code="validation_error",
                message="Ошибка валидации входных данных.",
                details=exc.errors(),
            ),
        )